"""Build the tracked, redistributable demo bundles for Every Angle.

The match-001 build preserves its pending Review fixture. The match-002 build
copies only the explicitly authorized processed artifacts; source footage and
other working data never enter deploy/bundle.

Run: ./.venv/bin/python scripts/build_deploy_bundle.py
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

MATCH_001_SRC = Path("data/match-001")
MATCH_001_DST = Path("deploy/bundle/match-001")
MATCH_002_SRC = Path("data/match-002")
MATCH_002_DST = Path("deploy/bundle/match-002")
# Demo review fixture: a standalone goal-ish moment (2590s) with a proposal clip.
PENDING_PROPOSAL = "r-20260714T182221Z-v2-p-039"
EVENT_ID = re.compile(r"e-\d+")


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _artifact_path(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"Unsafe artifact path: {relative}")
    return root.joinpath(*path.parts)


def _copy_relative(source_root: Path, destination_root: Path, relative: str) -> None:
    source = _artifact_path(source_root, relative)
    if not source.is_file():
        raise FileNotFoundError(source)
    destination = _artifact_path(destination_root, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _latest_claude_run_id(proposals: dict[str, Any]) -> str | None:
    runs = proposals.get("runs")
    if not isinstance(runs, list):
        raise ValueError("match-002 proposals runs must be a list")
    candidates = [
        (str(run.get("created_at", "")), index, str(run.get("run_id", "")))
        for index, run in enumerate(runs)
        if isinstance(run, dict)
        and isinstance(run.get("captioner"), dict)
        and run["captioner"].get("name") == "claude"
        and run.get("run_id")
    ]
    return max(candidates)[2] if candidates else None


def build_match_001(source: Path, destination: Path) -> dict[str, Any]:
    """Rebuild the existing CC-BY baseline without changing its fixture."""

    if destination.exists():
        shutil.rmtree(destination)
    (destination / "staging" / "rev-1" / "clips").mkdir(parents=True)
    (destination / "clips").mkdir(parents=True)

    for name in ("CURRENT_REV", "windows.json", "proposals.json"):
        shutil.copy2(source / name, destination / name)

    decisions = _read_object(source / "decisions.json")
    decisions.pop(PENDING_PROPOSAL, None)
    (destination / "decisions.json").write_text(json.dumps(decisions, indent=2) + "\n")

    manifest = _read_object(source / "staging/rev-1/manifest.json")
    (destination / "staging/rev-1/manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )

    kept_event_ids = [str(event["id"]) for event in manifest["events"]]
    for event_id in kept_event_ids:
        clip = source / "clips" / f"{event_id}.mp4"
        shutil.copy2(clip, destination / "clips" / clip.name)
        shutil.copy2(clip, destination / "staging/rev-1/clips" / clip.name)

    pending_clip_id = (
        "proposal-" + hashlib.sha256(PENDING_PROPOSAL.encode()).hexdigest()[:16]
    )
    pending_clip = source / "clips" / f"{pending_clip_id}.mp4"
    shutil.copy2(pending_clip, destination / "clips" / pending_clip.name)

    proposals = _read_object(source / "proposals.json")
    latest_run = proposals["runs"][-1]["run_id"]
    frame_paths: set[str] = set()
    for proposal in proposals["proposals"]:
        if proposal["run_id"] != latest_run or proposal.get("type") == "none":
            continue
        for frame in (proposal.get("evidence") or {}).get("frames", []):
            frame_paths.add(frame)
    for relative in frame_paths:
        source_frame = source / relative
        if source_frame.is_file():
            destination_frame = destination / relative
            destination_frame.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_frame, destination_frame)

    return {
        "accepted_events": kept_event_ids,
        "accepted_decisions": [
            key
            for key, value in decisions.items()
            if isinstance(value, dict) and value.get("status") == "accepted"
        ],
        "rejected_decisions": [
            key
            for key, value in decisions.items()
            if isinstance(value, dict) and value.get("status") == "rejected"
        ],
        "pending_clip": pending_clip.name,
        "frame_count": len(frame_paths),
    }


def build_match_002(source: Path, destination: Path) -> dict[str, Any]:
    """Build the authorized broadcast bundle from a strict artifact allowlist."""

    revision_text = (source / "CURRENT_REV").read_text().strip()
    try:
        revision = int(revision_text)
    except ValueError as exc:
        raise ValueError("match-002 CURRENT_REV must be an integer") from exc
    if revision < 1:
        raise ValueError("match-002 CURRENT_REV must be positive")

    proposals = _read_object(source / "proposals.json")
    decisions = _read_object(source / "decisions.json")
    rows = proposals.get("proposals")
    if not isinstance(rows, list):
        raise ValueError("match-002 proposals must contain a proposal list")
    latest_run = _latest_claude_run_id(proposals)
    if latest_run is None:
        raise ValueError("match-002 proposals must contain a Claude run")
    latest_rows = [
        row for row in rows if isinstance(row, dict) and row.get("run_id") == latest_run
    ]

    manifest_relative = f"staging/rev-{revision}/manifest.json"
    manifest = _read_object(_artifact_path(source, manifest_relative))
    manifest_events = manifest.get("events")
    if not isinstance(manifest_events, list):
        raise ValueError("match-002 manifest must contain an event list")

    event_ids: set[str] = set()
    for proposal in latest_rows:
        if proposal.get("type") == "none":
            continue
        proposal_id = str(proposal.get("id", ""))
        decision = decisions.get(proposal_id)
        if not isinstance(decision, dict) or decision.get("status") not in {
            "accepted",
            "rejected",
        }:
            continue
        event_id = str(decision.get("event_id", ""))
        if not EVENT_ID.fullmatch(event_id):
            raise ValueError(f"Invalid event id for {proposal_id}: {event_id}")
        event_ids.add(event_id)

    first_frames: set[str] = set()
    for proposal in latest_rows:
        evidence = proposal.get("evidence")
        frames = evidence.get("frames") if isinstance(evidence, dict) else None
        if not isinstance(frames, list) or not frames or not isinstance(frames[0], str):
            raise ValueError(
                f"Latest proposal {proposal.get('id')} has no poster frame"
            )
        first_frames.add(frames[0])

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for name in ("CURRENT_REV", "windows.json", "decisions.json"):
        _copy_relative(source, destination, name)
    deployed_proposals = json.loads(json.dumps(proposals))
    for proposal in deployed_proposals["proposals"]:
        if not isinstance(proposal, dict) or proposal.get("run_id") != latest_run:
            continue
        evidence = proposal.get("evidence")
        frames = evidence.get("frames") if isinstance(evidence, dict) else None
        if isinstance(frames, list):
            evidence["frames"] = frames[:1]
    (destination / "proposals.json").write_text(
        json.dumps(deployed_proposals, indent=2) + "\n"
    )
    _copy_relative(source, destination, manifest_relative)
    for event_id in sorted(event_ids):
        _copy_relative(source, destination, f"clips/{event_id}.mp4")
    for relative in sorted(first_frames):
        _copy_relative(source, destination, relative)

    return {
        "revision": revision,
        "event_count": len(manifest_events),
        "clip_count": len(event_ids),
        "frame_count": len(first_frames),
        "latest_run": latest_run,
    }


def _write_notes(match_001: dict[str, Any], match_002: dict[str, Any]) -> None:
    Path("deploy/bundle/NOTES.md").write_text(
        "# Deploy bundle notes\n\n"
        "## match-001 (SoccerTrack v2, CC BY 4.0)\n\n"
        f"- Accepted events (searchable baseline): {match_001['accepted_events']}\n"
        f"- Accepted decisions: {match_001['accepted_decisions']}\n"
        f"- Rejected decisions: {match_001['rejected_decisions']}\n"
        f"- PENDING review fixture: {PENDING_PROPOSAL} "
        f"(goal-ish @2590s, clip {match_001['pending_clip']})\n"
        f"- Evidence frames copied: {match_001['frame_count']}\n\n"
        "## match-002 (Broadcast feed, user-provided)\n\n"
        f"- Published revision: {match_002['revision']}\n"
        f"- Accepted events (searchable baseline): {match_002['event_count']}\n"
        f"- Accepted/rejected notable clips copied: {match_002['clip_count']}\n"
        f"- Latest-run Review posters copied: {match_002['frame_count']}\n"
        "- No source footage, samples, generated reels, or old staging revisions.\n"
    )


def main() -> None:
    match_001 = build_match_001(MATCH_001_SRC, MATCH_001_DST)
    match_002 = build_match_002(MATCH_002_SRC, MATCH_002_DST)
    _write_notes(match_001, match_002)
    print(
        "bundles built: "
        f"match-001 {len(match_001['accepted_events'])} events + pending fixture; "
        f"match-002 rev {match_002['revision']}, {match_002['event_count']} events, "
        f"{match_002['clip_count']} clips, {match_002['frame_count']} posters"
    )


if __name__ == "__main__":
    main()
