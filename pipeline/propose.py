"""Caption sampled windows and append a run-scoped proposals artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .captioner import CONFIDENCE_LEVELS, PROPOSAL_TYPES, Captioner, make_captioner


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def make_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"r-{timestamp}-{uuid.uuid4().hex[:8]}"


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_run_id(run_id: str) -> None:
    if not run_id or run_id in {".", ".."} or Path(run_id).name != run_id:
        raise ValueError("run_id must be a single path-safe name")


def _sampled_frames(frames_dir: Path, run_id: str, window_id: str) -> list[Path]:
    run_scoped = frames_dir / run_id / window_id
    if run_scoped.is_dir():
        return sorted(path for path in run_scoped.glob("*.jpg") if path.is_file())
    # This fallback keeps propose.py useful with a manually prepared frame
    # directory, while all written evidence remains run/proposal scoped.
    legacy = frames_dir / window_id
    return sorted(path for path in legacy.glob("*.jpg") if path.is_file())


def _copy_evidence(
    source_frames: Iterable[Path],
    *,
    frames_dir: Path,
    proposal_id: str,
) -> list[str]:
    evidence_dir = frames_dir / proposal_id
    evidence_dir.mkdir(parents=True, exist_ok=False)
    evidence_paths: list[str] = []
    for index, source in enumerate(source_frames, 1):
        destination = (
            evidence_dir / f"frame-{index:03d}{source.suffix.lower() or '.jpg'}"
        )
        shutil.copy2(source, destination)
        evidence_paths.append(destination.relative_to(frames_dir.parent).as_posix())
    return evidence_paths


def validate_evidence_ownership(
    proposals: Iterable[dict[str, Any]], data_dir: Path
) -> None:
    """Ensure every evidence file is inside its proposal's own directory."""

    frames_root = (data_dir / "frames").resolve()
    for proposal in proposals:
        proposal_id = str(proposal.get("id", ""))
        expected_dir = (frames_root / proposal_id).resolve()
        frames = proposal.get("evidence", {}).get("frames", [])
        if not isinstance(frames, list):
            raise ValueError(f"evidence.frames must be a list for {proposal_id}")
        for relative in frames:
            if not isinstance(relative, str):
                raise ValueError(
                    f"evidence frame path must be a string for {proposal_id}"
                )
            path = PurePosixPath(relative)
            if path.is_absolute() or len(path.parts) < 3 or path.parts[0] != "frames":
                raise ValueError(
                    f"evidence path is not rooted at frames/{proposal_id}: {relative}"
                )
            if path.parts[1] != proposal_id:
                raise ValueError(
                    f"evidence path for {proposal_id} belongs to {path.parts[1]}: {relative}"
                )
            resolved = (data_dir / Path(*path.parts)).resolve()
            if not resolved.is_relative_to(expected_dir) or not resolved.is_file():
                raise ValueError(
                    f"evidence file is outside or missing for {proposal_id}: {relative}"
                )


def _load_existing(path: Path, *, video_id: str, asset: str) -> dict[str, Any]:
    if not path.exists():
        return {"video_id": video_id, "asset": asset, "runs": [], "proposals": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("video_id") != video_id:
        raise ValueError(
            f"existing proposals belong to {payload.get('video_id')!r}, not {video_id!r}"
        )
    if not isinstance(payload.get("runs"), list) or not isinstance(
        payload.get("proposals"), list
    ):
        raise ValueError("existing proposals.json does not match the data contract")
    return payload


def build_proposals(
    windows_artifact: dict[str, Any],
    *,
    source: Path,
    output_dir: Path,
    frames_dir: Path,
    captioner: Captioner,
    run_id: str | None = None,
    asset: str | None = None,
) -> dict[str, Any]:
    """Create one run and append its proposals to ``proposals.json``."""

    if not source.is_file():
        raise FileNotFoundError(f"source video does not exist: {source}")
    video_id = str(windows_artifact.get("video_id") or source.stem)
    run_id = run_id or make_run_id()
    _validate_run_id(run_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)
    proposals_path = output_dir / "proposals.json"
    artifact = _load_existing(
        proposals_path,
        video_id=video_id,
        asset=asset or f"docs/assets-manifest.md#{video_id}",
    )
    if any(run.get("run_id") == run_id for run in artifact["runs"]):
        raise ValueError(f"run_id already exists in {proposals_path}: {run_id}")

    run = {
        "run_id": run_id,
        "created_at": utc_now(),
        "source_sha256": sha256_file(source),
        "detector_config_hash": sha256_json(
            windows_artifact.get("detector_config", {})
        ),
        "captioner": captioner.metadata,
    }
    new_proposals: list[dict[str, Any]] = []
    created_dirs: list[Path] = []
    try:
        for index, window in enumerate(windows_artifact.get("windows", []), 1):
            proposal_id = f"{run_id}-p-{index:03d}"
            source_frames = _sampled_frames(frames_dir, run_id, str(window["id"]))
            evidence_dir = frames_dir / proposal_id
            evidence = _copy_evidence(
                source_frames, frames_dir=frames_dir, proposal_id=proposal_id
            )
            created_dirs.append(evidence_dir)
            result = captioner.caption(source_frames, window)
            if result.type not in PROPOSAL_TYPES:
                raise ValueError(
                    f"captioner returned invalid event type: {result.type!r}"
                )
            if result.confidence not in CONFIDENCE_LEVELS:
                raise ValueError(
                    f"captioner returned invalid confidence: {result.confidence!r}"
                )
            new_proposals.append(
                {
                    "id": proposal_id,
                    "run_id": run_id,
                    "t_start": float(window["t_start"]),
                    "t_end": float(window["t_end"]),
                    "type": result.type,
                    "confidence": result.confidence,
                    "caption": result.caption,
                    "evidence": {
                        "frames": evidence,
                        "audio_peak": bool(window.get("audio_peak", False)),
                        "scene_cut": bool(window.get("scene_cut", False)),
                    },
                }
            )
        all_proposals = [*artifact["proposals"], *new_proposals]
        validate_evidence_ownership(all_proposals, output_dir)
        artifact["runs"].append(run)
        artifact["proposals"] = all_proposals
        _write_json_atomic(proposals_path, artifact)
    except Exception:
        for evidence_dir in created_dirs:
            shutil.rmtree(evidence_dir, ignore_errors=True)
        raise
    return artifact


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--windows", type=Path, required=True, help="ingest.py windows JSON"
    )
    parser.add_argument(
        "--source", type=Path, default=None, help="Source MP4, otherwise windows.source"
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="data/<video-id>/ directory"
    )
    parser.add_argument("--frames-dir", type=Path, default=None)
    parser.add_argument("--captioner", choices=("mock", "claude"), default="mock")
    parser.add_argument("--budget-usd", type=float, default=None,
                        help="hard spend cap; the run aborts rather than exceed it")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--asset", default=None)
    args = parser.parse_args()
    windows_artifact = json.loads(args.windows.read_text(encoding="utf-8"))
    source = args.source or Path(windows_artifact["source"])
    frames_dir = args.frames_dir or args.output_dir / "frames"
    captioner = make_captioner(args.captioner, budget_usd=args.budget_usd)
    artifact = build_proposals(
        windows_artifact,
        source=source,
        output_dir=args.output_dir,
        frames_dir=frames_dir,
        captioner=captioner,
        run_id=args.run_id,
        asset=args.asset,
    )
    print(
        f"wrote {len(artifact['proposals'])} proposals across {len(artifact['runs'])} runs "
        f"to {args.output_dir / 'proposals.json'}"
    )
    spent = getattr(captioner, "spent_usd", None)
    if spent is not None:
        print(f"API spend this run: ${spent:.4f} over {captioner.calls} windows")


if __name__ == "__main__":
    main()
