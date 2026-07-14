"""Pre-cut verified manifest events to uniform browser-friendly clips."""

from __future__ import annotations

import argparse
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Source MP4 path")
    parser.add_argument(
        "--manifest", type=Path, required=True, help="Verified manifest.json"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None, help="data/<video-id> directory"
    )
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"input does not exist: {args.input}")
    data_dir = args.output_dir or args.manifest.parent
    payload = precut_verified_events(args.input, args.manifest, data_dir=data_dir)
    print(
        f"encoded {len(payload.get('events', []))} verified clips in {data_dir / 'clips'}"
    )


if __name__ == "__main__":
    main()
