"""Contract tests for proposal generation (pipeline.propose)."""

import json
import subprocess

import pytest

from pipeline.captioner import CaptionResult, MockCaptioner
from pipeline.propose import build_proposals, validate_evidence_ownership


@pytest.fixture()
def tiny_video(tmp_path):
    """A 2-second synthetic clip so sha256 and frame paths are real."""
    path = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=320x180:rate=10",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(path),
        ],
        check=True,
    )
    return path


def _windows_artifact(source):
    return {
        "video_id": "vid-1",
        "source": str(source),
        "detector_config": {"scene_threshold": 0.35},
        "windows": [
            {
                "id": "w-001",
                "t_start": 0.0,
                "t_end": 1.0,
                "audio_peak": True,
                "scene_cut": False,
            },
            {
                "id": "w-002",
                "t_start": 1.0,
                "t_end": 2.0,
                "audio_peak": False,
                "scene_cut": True,
            },
        ],
    }


def _seed_frames(frames_dir, run_id, window_ids, n=2):
    for wid in window_ids:
        d = frames_dir / run_id / wid
        d.mkdir(parents=True)
        for i in range(1, n + 1):
            (d / f"frame-{i:03d}.jpg").write_bytes(b"\xff\xd8fakejpg")


def test_contract_round_trip(tmp_path, tiny_video):
    data_dir = tmp_path / "data"
    frames = data_dir / "frames"
    _seed_frames(frames, "r-test-1", ["w-001", "w-002"])
    artifact = build_proposals(
        _windows_artifact(tiny_video),
        source=tiny_video,
        output_dir=data_dir,
        frames_dir=frames,
        captioner=MockCaptioner(),
        run_id="r-test-1",
    )
    # Run provenance per plan (r2 finding 2)
    (run,) = artifact["runs"]
    assert run["source_sha256"] and len(run["source_sha256"]) == 64
    assert run["detector_config_hash"]
    assert run["captioner"] == {
        "name": "mock",
        "model": "mock-captioner",
        "prompt_version": "p1",
    }
    # Run-scoped globally-unique ids (r3 finding 1)
    ids = [p["id"] for p in artifact["proposals"]]
    assert ids == ["r-test-1-p-001", "r-test-1-p-002"]
    # Run-scoped evidence paths (r4 finding 1)
    for p in artifact["proposals"]:
        for f in p["evidence"]["frames"]:
            assert f.startswith(f"frames/{p['id']}/")
    # Round-trips through disk
    on_disk = json.loads((data_dir / "proposals.json").read_text())
    assert on_disk == artifact


def test_second_run_appends_without_collision(tmp_path, tiny_video):
    data_dir = tmp_path / "data"
    frames = data_dir / "frames"
    for run_id in ("r-a", "r-b"):
        _seed_frames(frames, run_id, ["w-001", "w-002"])
        artifact = build_proposals(
            _windows_artifact(tiny_video),
            source=tiny_video,
            output_dir=data_dir,
            frames_dir=frames,
            captioner=MockCaptioner(),
            run_id=run_id,
        )
    assert len(artifact["runs"]) == 2
    assert len(artifact["proposals"]) == 4
    assert len({p["id"] for p in artifact["proposals"]}) == 4


def test_structured_goal_identity_is_persisted(tmp_path, tiny_video, monkeypatch):
    data_dir = tmp_path / "data"
    frames = data_dir / "frames"
    _seed_frames(frames, "r-identity", ["w-001", "w-002"])
    captioner = MockCaptioner()
    monkeypatch.setattr(
        captioner,
        "caption",
        lambda *_: CaptionResult(
            caption="A directly attributed goal",
            type="goal",
            confidence="high",
            team="Blue FC",
            player="Alex Striker",
        ),
    )

    artifact = build_proposals(
        _windows_artifact(tiny_video),
        source=tiny_video,
        output_dir=data_dir,
        frames_dir=frames,
        captioner=captioner,
        run_id="r-identity",
    )

    assert {(row["team"], row["player"]) for row in artifact["proposals"]} == {
        ("Blue FC", "Alex Striker")
    }


def test_duplicate_run_id_rejected(tmp_path, tiny_video):
    data_dir = tmp_path / "data"
    frames = data_dir / "frames"
    _seed_frames(frames, "r-dup", ["w-001", "w-002"])
    build_proposals(
        _windows_artifact(tiny_video),
        source=tiny_video,
        output_dir=data_dir,
        frames_dir=frames,
        captioner=MockCaptioner(),
        run_id="r-dup",
    )
    with pytest.raises(ValueError, match="run_id already exists"):
        build_proposals(
            _windows_artifact(tiny_video),
            source=tiny_video,
            output_dir=data_dir,
            frames_dir=frames,
            captioner=MockCaptioner(),
            run_id="r-dup",
        )


def test_evidence_ownership_rejects_cross_proposal_paths(tmp_path):
    frames = tmp_path / "frames" / "r-1-p-001"
    frames.mkdir(parents=True)
    (frames / "frame-001.jpg").write_bytes(b"x")
    good = {
        "id": "r-1-p-001",
        "evidence": {"frames": ["frames/r-1-p-001/frame-001.jpg"]},
    }
    thief = {
        "id": "r-2-p-001",
        "evidence": {"frames": ["frames/r-1-p-001/frame-001.jpg"]},
    }
    validate_evidence_ownership([good], tmp_path)
    with pytest.raises(ValueError, match="belongs to"):
        validate_evidence_ownership([thief], tmp_path)


def test_evidence_ownership_rejects_escaping_paths(tmp_path):
    bad = {"id": "r-1-p-001", "evidence": {"frames": ["/etc/passwd"]}}
    with pytest.raises(ValueError):
        validate_evidence_ownership([bad], tmp_path)
