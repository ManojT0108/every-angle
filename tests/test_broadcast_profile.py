"""Broadcast-profile sampling and caption prompt contract tests."""

from pathlib import Path

from pipeline import sample
from pipeline.captioner import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_BROADCAST,
    ClaudeCaptioner,
    make_captioner,
)


def _artifact(*, profile: str | None) -> dict:
    artifact = {
        "video_id": "match-test",
        "duration": 20.0,
        "windows": [{"id": "w-001", "t_start": 2.0, "t_end": 8.0}],
    }
    if profile is not None:
        artifact["profile"] = profile
    return artifact


def _write_stub_frame(
    source: Path,
    t: float,
    size: tuple[int, int],
    destination: Path,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"fake jpg")


def test_broadcast_sampling_skips_tracking_and_uses_full_frames(
    tmp_path, monkeypatch
):
    calls = []

    def fail_track(*args, **kwargs):
        raise AssertionError("broadcast sampling must not track the ball")

    def extract_full(source, t, size, destination):
        calls.append((source, t, size, destination))
        _write_stub_frame(source, t, size, destination)

    monkeypatch.setattr(sample, "probe_size", lambda source: (1920, 1080))
    monkeypatch.setattr(sample, "track", fail_track)
    monkeypatch.setattr(sample, "extract_full", extract_full)

    artifact = sample.extract_frames(
        tmp_path / "broadcast.mp4",
        _artifact(profile="broadcast"),
        tmp_path / "frames",
        run_id="r-test",
    )

    assert len(calls) == sample.DEFAULT_BROADCAST_FRAMES
    assert [call[1] for call in calls] == [
        2.0,
        4.0,
        6.0,
        8.0,
        10.0,
        12.0,
        14.0,
        16.0,
    ]
    assert [Path(path).name for path in artifact["windows"][0]["frames"]] == [
        f"frame-{i:03d}.jpg" for i in range(1, 9)
    ]
    assert artifact["windows"][0]["profile"] == "broadcast"
    assert artifact["windows"][0]["ball_tracked"] is None
    assert artifact["profile"] == "broadcast"
    assert artifact["frames_per_window"] == sample.DEFAULT_BROADCAST_FRAMES
    assert "tight_frames_per_window" not in artifact
    assert "wide_frames_per_window" not in artifact


def test_broadcast_sampling_clamps_last_frame_inside_file(tmp_path, monkeypatch):
    times: list[float] = []

    def fail_track(*args, **kwargs):
        raise AssertionError("broadcast sampling must not track the ball")

    def extract_full(source, t, size, destination):
        times.append(t)
        _write_stub_frame(source, t, size, destination)

    monkeypatch.setattr(sample, "probe_size", lambda source: (1920, 1080))
    monkeypatch.setattr(sample, "track", fail_track)
    monkeypatch.setattr(sample, "extract_full", extract_full)

    # Window ends within AFTERMATH_SECONDS of EOF: reach (t_end+8=26) exceeds the
    # 20s duration, so the last frame must be clamped strictly inside the file.
    artifact = {
        "video_id": "match-test",
        "duration": 20.0,
        "profile": "broadcast",
        "windows": [{"id": "w-001", "t_start": 12.0, "t_end": 18.0}],
    }
    sample.extract_frames(
        tmp_path / "broadcast.mp4", artifact, tmp_path / "frames", run_id="r-test"
    )

    assert len(times) == sample.DEFAULT_BROADCAST_FRAMES
    assert times[0] == 12.0
    assert max(times) <= 20.0 - 0.1


def test_fixed_sampling_still_tracks_and_uses_tight_and_wide_names(
    tmp_path, monkeypatch
):
    track_calls = []

    def track(source, start, duration):
        track_calls.append((source, start, duration))
        return [960.0] * 100, [540.0] * 100, [True] * 100

    def extract_tight(source, t, ball, size, destination):
        _write_stub_frame(source, t, size, destination)

    monkeypatch.setattr(sample, "probe_size", lambda source: (1920, 1080))
    monkeypatch.setattr(sample, "track", track)
    monkeypatch.setattr(sample, "extract_tight", extract_tight)
    monkeypatch.setattr(sample, "extract_wide", _write_stub_frame)

    artifact = sample.extract_frames(
        tmp_path / "fixed.mp4",
        _artifact(profile=None),
        tmp_path / "frames",
        run_id="r-test",
    )

    assert len(track_calls) == 1
    assert [Path(path).name for path in artifact["windows"][0]["frames"]] == [
        *[f"tight-{i:03d}.jpg" for i in range(1, 6)],
        *[f"wide-{i:03d}.jpg" for i in range(1, 4)],
    ]
    assert artifact["tight_frames_per_window"] == sample.DEFAULT_TIGHT_FRAMES
    assert artifact["wide_frames_per_window"] == sample.DEFAULT_WIDE_FRAMES
    assert "profile" not in artifact
    assert "frames_per_window" not in artifact


def test_claude_captioner_selects_prompt_for_profile():
    fixed = ClaudeCaptioner()
    broadcast = ClaudeCaptioner(profile="broadcast")

    assert fixed.system_prompt is SYSTEM_PROMPT
    assert fixed.prompt_version == "p3-celebration"
    assert broadcast.system_prompt is SYSTEM_PROMPT_BROADCAST
    assert broadcast.prompt_version == "p3-broadcast-celebration"


def test_make_captioner_propagates_broadcast_profile():
    captioner = make_captioner("claude", profile="broadcast")

    assert isinstance(captioner, ClaudeCaptioner)
    assert captioner.profile == "broadcast"
    assert captioner.system_prompt is SYSTEM_PROMPT_BROADCAST
    assert captioner.prompt_version == "p3-broadcast-celebration"
