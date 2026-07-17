"""Build the tracked, CC-BY deploy bundle for match-001 (Every Angle demo).

Copies ONLY the redistributable artifacts into deploy/bundle/match-001/, makes one
proposal PENDING (the demo review fixture), and records the kept/rejected/pending ids.
Run: ./.venv/bin/python scripts/build_deploy_bundle.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

SRC = Path("data/match-001")
DST = Path("deploy/bundle/match-001")
# Demo review fixture: a standalone goal-ish moment (2590s) with a proposal clip.
PENDING_PROPOSAL = "r-20260714T182221Z-v2-p-039"


def main() -> None:
    if DST.exists():
        shutil.rmtree(DST)
    (DST / "staging" / "rev-1" / "clips").mkdir(parents=True)
    (DST / "clips").mkdir(parents=True)

    # CURRENT_REV, windows.json, proposals.json
    for name in ("CURRENT_REV", "windows.json", "proposals.json"):
        shutil.copy2(SRC / name, DST / name)

    # decisions.json with the pending fixture UN-decided
    decisions = json.loads((SRC / "decisions.json").read_text())
    decisions.pop(PENDING_PROPOSAL, None)
    (DST / "decisions.json").write_text(json.dumps(decisions, indent=2) + "\n")

    # promoted manifest (the 5 accepted events)
    manifest = json.loads((SRC / "staging/rev-1/manifest.json").read_text())
    (DST / "staging/rev-1/manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    # event clips -> root (playback) AND staging (reel assembly)
    kept_event_ids = [str(e["id"]) for e in manifest["events"]]
    for eid in kept_event_ids:
        clip = SRC / "clips" / f"{eid}.mp4"
        shutil.copy2(clip, DST / "clips" / f"{eid}.mp4")
        shutil.copy2(clip, DST / "staging/rev-1/clips" / f"{eid}.mp4")

    # proposal clip for the pending fixture
    import hashlib

    def proposal_clip_id(pid: str) -> str:
        return "proposal-" + hashlib.sha256(pid.encode()).hexdigest()[:16]

    pend_clip = SRC / "clips" / f"{proposal_clip_id(PENDING_PROPOSAL)}.mp4"
    shutil.copy2(pend_clip, DST / "clips" / pend_clip.name)

    # evidence frames referenced by the notable proposals shown in Review
    proposals = json.loads((SRC / "proposals.json").read_text())
    latest_run = proposals["runs"][-1]["run_id"]
    frame_rel: set[str] = set()
    for p in proposals["proposals"]:
        if p["run_id"] != latest_run or p.get("type") == "none":
            continue
        for f in (p.get("evidence") or {}).get("frames", []):
            frame_rel.add(f)
    for rel in frame_rel:
        src_f = SRC / rel
        if src_f.is_file():
            dst_f = DST / rel
            dst_f.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_f, dst_f)

    notes = DST.parent / "NOTES.md"
    accepted = [k for k, v in decisions.items() if isinstance(v, dict) and v.get("status") == "accepted"]
    rejected = [k for k, v in decisions.items() if isinstance(v, dict) and v.get("status") == "rejected"]
    notes.write_text(
        "# Deploy bundle notes (match-001, CC BY 4.0)\n\n"
        f"- Accepted events (searchable baseline): {kept_event_ids}\n"
        f"- Accepted decisions: {accepted}\n"
        f"- Rejected decisions: {rejected}\n"
        f"- PENDING review fixture: {PENDING_PROPOSAL} (goal-ish @2590s, clip {pend_clip.name})\n"
        f"- Evidence frames copied: {len(frame_rel)}\n"
        "- No source video, no match-002 — CC-BY redistributable only.\n"
    )
    total_clips = len(list(DST.rglob("*.mp4")))
    total_frames = len(list(DST.rglob("*.jpg")))
    print(f"bundle built: {len(kept_event_ids)} events, {total_clips} clips, {total_frames} frames")
    print(f"pending fixture: {PENDING_PROPOSAL}")


if __name__ == "__main__":
    main()
