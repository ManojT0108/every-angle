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
