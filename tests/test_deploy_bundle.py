"""Focused checks for the strict match-002 deployment allowlist."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.build_deploy_bundle import build_match_002


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_match_002_uses_current_revision_and_only_first_posters(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "bundle"
    (source / "CURRENT_REV").parent.mkdir(parents=True)
    (source / "CURRENT_REV").write_text("3\n", encoding="utf-8")
    _write_json(source / "windows.json", {"video_id": "match-002", "windows": []})
    _write_json(
        source / "proposals.json",
        {
            "runs": [
                {
                    "run_id": "r-latest",
                    "created_at": "2026-07-16T01:00:00Z",
                    "captioner": {"name": "claude"},
                }
            ],
            "proposals": [
                {
                    "id": "p-notable",
                    "run_id": "r-latest",
                    "type": "goal",
                    "evidence": {
                        "frames": [
                            "frames/p-notable/frame-001.jpg",
                            "frames/p-notable/frame-002.jpg",
                        ]
                    },
                },
                {
                    "id": "p-ordinary",
                    "run_id": "r-latest",
                    "type": "none",
                    "evidence": {
                        "frames": [
                            "frames/p-ordinary/frame-001.jpg",
                            "frames/p-ordinary/frame-002.jpg",
                        ]
                    },
                },
            ],
        },
    )
    _write_json(
        source / "decisions.json",
        {"p-notable": {"status": "accepted", "event_id": "e-001"}},
    )
    _write_json(
        source / "staging/rev-3/manifest.json",
        {"video_id": "match-002", "events": [{"id": "e-001"}]},
    )
    (source / "clips").mkdir()
    (source / "clips/e-001.mp4").write_bytes(b"clip")
    for proposal_id in ("p-notable", "p-ordinary"):
        frame_dir = source / "frames" / proposal_id
        frame_dir.mkdir(parents=True)
        (frame_dir / "frame-001.jpg").write_bytes(b"poster")
        (frame_dir / "frame-002.jpg").write_bytes(b"excluded")
    (source / "source").mkdir()
    (source / "source/broadcast.mp4").write_bytes(b"must not ship")

    summary = build_match_002(source, destination)

    assert summary == {
        "revision": 3,
        "event_count": 1,
        "clip_count": 1,
        "frame_count": 2,
        "latest_run": "r-latest",
    }
    assert (destination / "staging/rev-3/manifest.json").is_file()
    assert (destination / "clips/e-001.mp4").is_file()
    assert not (destination / "source/broadcast.mp4").exists()
    assert not list(destination.rglob("frame-002.jpg"))

    deployed = json.loads((destination / "proposals.json").read_text())
    assert [row["evidence"]["frames"] for row in deployed["proposals"]] == [
        ["frames/p-notable/frame-001.jpg"],
        ["frames/p-ordinary/frame-001.jpg"],
    ]
