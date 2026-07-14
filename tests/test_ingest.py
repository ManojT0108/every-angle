"""Unit tests for candidate-window detection (pipeline.ingest)."""

from pipeline.ingest import AudioPeak, MotionPeak, build_candidate_windows


def test_no_cues_yields_single_fallback_window():
    windows = build_candidate_windows(100.0, [], [])
    assert len(windows) == 1
    w = windows[0]
    assert w.id == "w-001"
    assert w.t_start == 0.0
    assert 0 < w.t_end <= 100.0
    assert not w.audio_peak and not w.scene_cut and not w.motion_peak


def test_nearby_cues_merge_into_one_window():
    peaks = [AudioPeak(time=50.0, rms=0.2)]
    cuts = [51.5]  # within merge_gap of the peak
    motion = [MotionPeak(time=52.0, magnitude=0.1)]
    windows = build_candidate_windows(100.0, peaks, cuts, motion)
    assert len(windows) == 1
    w = windows[0]
    assert w.audio_peak and w.scene_cut and w.motion_peak
    assert w.t_start == 45.0  # 50 - pre_roll
    assert w.t_end == 62.0  # 52 + post_roll


def test_distant_cues_stay_separate_and_sorted():
    peaks = [AudioPeak(time=80.0, rms=0.3), AudioPeak(time=10.0, rms=0.2)]
    windows = build_candidate_windows(200.0, peaks, [])
    assert [w.t_start for w in windows] == sorted(w.t_start for w in windows)
    assert len(windows) == 2
    assert [w.id for w in windows] == ["w-001", "w-002"]


def test_window_bounds_clamped_to_video():
    peaks = [AudioPeak(time=1.0, rms=0.5), AudioPeak(time=99.0, rms=0.5)]
    windows = build_candidate_windows(100.0, peaks, [])
    assert windows[0].t_start == 0.0
    assert windows[-1].t_end == 100.0


def test_cap_keeps_strongest_cues():
    peaks = [
        AudioPeak(time=float(10 * i), rms=0.01 * i) for i in range(1, 61)
    ]  # 60 well-separated peaks, increasing strength
    windows = build_candidate_windows(10_000.0, peaks, [], max_windows=40)
    assert len(windows) == 40
    # The weakest cues (earliest times here) must be the ones dropped.
    kept_scores = sorted(w.score for w in windows)
    assert kept_scores[0] >= 0.01 * 21 - 1e-9


def test_zero_duration_yields_nothing():
    assert build_candidate_windows(0.0, [AudioPeak(time=1.0, rms=0.5)], [1.0]) == []


# --- profiles: the two footage regimes are genuinely different problems -----

def test_profile_is_detected_from_the_footage_not_asked_of_the_user():
    """A directed feed cuts constantly; a camera on a pole never cuts. That one
    number separates the regimes with no user input."""
    from pipeline.ingest import detect_profile

    assert detect_profile([], 2700.0) == "fixed"                    # 0 cuts in 45 min
    assert detect_profile([1.0, 2.0], 2700.0) == "fixed"            # negligible
    assert detect_profile([float(i) for i in range(240)], 6660.0) == "broadcast"  # 2.2/min


def test_fixed_profile_keeps_the_verified_parameters():
    """These were MEASURED at 2/2 goal recall with 25% of footage under review.
    If someone 'improves' them to win a different dataset, this fails loudly —
    which is exactly what happened twice while chasing the broadcast case."""
    from pipeline.ingest import PROFILES

    p = PROFILES["fixed"]
    assert p["pre_roll"] == 5.0
    assert p["post_roll"] == 10.0
    assert p["merge_gap"] == 3.0
    assert p["scoring"] == "cue_sum"


def test_broadcast_profile_ranks_by_rarity_not_presence():
    """On broadcast every window trips every cue, so cue PRESENCE discriminates
    nothing — the old scoring saturated and all 40 windows tied, so the cap fell
    back to timestamp order and the detector stopped looking two-thirds of the
    way through the match, walking straight past the only goal."""
    from pipeline.ingest import PROFILES

    assert PROFILES["broadcast"]["scoring"] == "percentile"
    assert PROFILES["broadcast"]["density_weight"] > 0    # a goal is a burst


def test_broadcast_windows_do_not_all_share_one_score():
    """The saturation bug, pinned: identical scores mean the cap degenerates into
    'keep the earliest N', which silently blinds the detector to the rest."""
    from pipeline.ingest import AudioPeak, MotionPeak, build_candidate_windows

    audio = [AudioPeak(time=float(t), rms=0.05 + (t % 7) * 0.01) for t in range(20, 600, 20)]
    motion = [MotionPeak(time=float(t) + 2, magnitude=0.1 + (t % 5) * 0.02)
              for t in range(20, 600, 20)]
    cuts = [float(t) + 1 for t in range(20, 600, 20)]

    windows = build_candidate_windows(660.0, audio, cuts, motion, profile="broadcast")
    scores = {w.score for w in windows}
    assert len(scores) > 1, "all windows tied — the cap would degenerate to timestamp order"
