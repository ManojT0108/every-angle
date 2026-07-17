"""Pre-cut match moments to uniform browser-friendly clips."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from .camera import filter_chain, needs_virtual_camera


def _has_audio_stream(source: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(source),
        ],
        capture_output=True,
        check=False,
    )
    return bool(result.stdout.strip())


def cut_event(source: Path, event: dict[str, Any], clips_dir: Path) -> Path:
    """Encode one verified event as H.264 video with an AAC stereo track."""

    event_id = str(event.get("id", ""))
    if not event_id or Path(event_id).name != event_id:
        raise ValueError(f"event id must be path-safe: {event_id!r}")
    start = float(event["t_start"])
    end = float(event["t_end"])
    duration = end - start
    if start < 0 or duration <= 0:
        raise ValueError(f"invalid event range for {event_id}: {start}–{end}")
    clips_dir.mkdir(parents=True, exist_ok=True)
    destination = clips_dir / f"{event_id}.mp4"
    has_audio = _has_audio_stream(source)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(source),
    ]
    if not has_audio:
        command.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
            ]
        )
    # A fixed wide camera gets a VIRTUAL CAMERA that tracks the ball. Letterboxing
    # a 4096x1080 panorama into 16:9 yields a thin strip of pitch with the players
    # as specks — technically a clip, but nothing anyone would watch. A broadcast
    # feed is already framed by a director and is passed through untouched.
    if needs_virtual_camera(source):
        video_filter = filter_chain(source, start, end)
    else:
        video_filter = (
            "scale=1280:720:force_original_aspect_ratio=decrease,"
            "pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
        )
    command.extend(
        [
            "-t",
            f"{duration:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0" if has_audio else "1:a:0",
            "-vf",
            video_filter,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            "-shortest",
            "-y",
            str(destination),
        ]
    )
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode != 0:
        message = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"clip encoding failed for {event_id}: {message}")
    return destination


def latest_claude_run_id(proposals: dict[str, Any]) -> str | None:
    """Return the newest Claude proposal run in an artifact."""

    runs = proposals.get("runs", [])
    if not isinstance(runs, list):
        raise ValueError("Invalid proposals runs")
    candidates = [
        (str(run.get("created_at", "")), index, str(run.get("run_id", "")))
        for index, run in enumerate(runs)
        if isinstance(run, dict)
        and isinstance(run.get("captioner"), dict)
        and run["captioner"].get("name") == "claude"
        and run.get("run_id")
    ]
    return max(candidates)[2] if candidates else None


def proposal_clip_id(proposal_id: str) -> str:
    """Return the stable, path-safe id used for a proposal-only clip."""

    if not proposal_id:
        raise ValueError("proposal id must not be empty")
    digest = hashlib.sha256(proposal_id.encode("utf-8")).hexdigest()[:16]
    return f"proposal-{digest}"


def resolve_proposal_clip(
    data_dir: Path,
    proposal_id: str,
    decision: Any,
) -> Path | None:
    """Resolve an event clip first, then a proposal-only clip."""

    clips_dir = data_dir / "clips"
    event_id = decision.get("event_id") if isinstance(decision, dict) else None
    if (
        isinstance(event_id, str)
        and event_id
        and Path(event_id).name == event_id
    ):
        event_clip = clips_dir / f"{event_id}.mp4"
        if event_clip.is_file():
            return event_clip
    proposal_clip = clips_dir / f"{proposal_clip_id(proposal_id)}.mp4"
    return proposal_clip if proposal_clip.is_file() else None


def precut_proposal_clips(
    source: Path | None,
    proposals_path: Path,
    decisions_path: Path,
    *,
    data_dir: Path | None = None,
) -> list[Path]:
    """Cut missing notable proposal clips for the latest Claude run."""

    if source is None or not source.is_file():
        return []
    data_dir = data_dir or proposals_path.parent
    proposals = _read_json_object(proposals_path)
    decisions = (
        _read_json_object(decisions_path) if decisions_path.is_file() else {}
    )
    run_id = latest_claude_run_id(proposals)
    if run_id is None:
        return []
    rows = proposals.get("proposals", [])
    if not isinstance(rows, list):
        raise ValueError("Invalid proposals artifact")

    destinations: list[Path] = []
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.get("run_id") != run_id
            or row.get("type") == "none"
        ):
            continue
        proposal_id = str(row.get("id", ""))
        decision = decisions.get(proposal_id, {})
        if resolve_proposal_clip(data_dir, proposal_id, decision) is not None:
            continue
        event = {
            "id": proposal_clip_id(proposal_id),
            "t_start": row["t_start"],
            "t_end": row["t_end"],
        }
        destinations.append(cut_event(source, event, data_dir / "clips"))
    return destinations


def precut_verified_events(
    source: Path,
    manifest_path: Path,
    *,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """Cut every manifest event and update its relative ``clip`` path."""

    data_dir = data_dir or manifest_path.parent
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    events = payload.get("events", [])
    clips_dir = data_dir / "clips"
    for event in events:
        destination = cut_event(source, event, clips_dir)
        event["clip"] = destination.relative_to(data_dir).as_posix()
    _write_json_atomic(manifest_path, payload)
    return payload


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid JSON object: {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Source MP4 path")
    artifact = parser.add_mutually_exclusive_group(required=True)
    artifact.add_argument("--manifest", type=Path, help="Verified manifest.json")
    artifact.add_argument("--proposals", type=Path, help="Proposals artifact")
    parser.add_argument("--decisions", type=Path, help="Decisions artifact")
    parser.add_argument(
        "--output-dir", type=Path, default=None, help="data/<video-id> directory"
    )
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"input does not exist: {args.input}")
    artifact_path = args.manifest or args.proposals
    assert artifact_path is not None
    data_dir = args.output_dir or artifact_path.parent
    if args.proposals is not None:
        decisions_path = args.decisions or args.proposals.with_name("decisions.json")
        destinations = precut_proposal_clips(
            args.input,
            args.proposals,
            decisions_path,
            data_dir=data_dir,
        )
        print(f"encoded {len(destinations)} proposal clips in {data_dir / 'clips'}")
    else:
        assert args.manifest is not None
        payload = precut_verified_events(args.input, args.manifest, data_dir=data_dir)
        print(
            f"encoded {len(payload.get('events', []))} verified clips in "
            f"{data_dir / 'clips'}"
        )


if __name__ == "__main__":
    main()
