"""Extract a small, fixed set of JPEG frames inside candidate windows."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MAX_FRAMES = 4


def _frame_times(window: dict[str, Any], max_frames: int) -> list[float]:
    start = float(window["t_start"])
    end = float(window["t_end"])
    duration = max(0.0, end - start)
    if duration == 0:
        return [start]
    fractions = [0.1, 0.4, 0.7, 0.95]
    return [
        round(start + duration * fraction, 3) for fraction in fractions[:max_frames]
    ]


def extract_frame(source: Path, timestamp: float, destination: Path) -> None:
    """Extract one frame, leaving ffmpeg's source seeking outside Python."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{max(0.0, timestamp):.3f}",
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-vf",
        "scale=960:-2,format=yuvj420p",
        "-q:v",
        "2",
        "-y",
        str(destination),
    ]
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        message = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"frame extraction failed at {timestamp:.3f}s: {message}")


def extract_frames(
    source: Path,
    windows_artifact: dict[str, Any],
    output_dir: Path,
    *,
    run_id: str,
    max_frames: int = DEFAULT_MAX_FRAMES,
) -> dict[str, Any]:
    """Extract frames under ``frames/<run_id>/<window-id>/``."""

    if max_frames < 1 or max_frames > DEFAULT_MAX_FRAMES:
        raise ValueError(f"max_frames must be between 1 and {DEFAULT_MAX_FRAMES}")
    output_dir.mkdir(parents=True, exist_ok=True)
    windows = windows_artifact.get("windows", [])
    sampled: list[dict[str, Any]] = []
    for window in windows:
        window_id = str(window["id"])
        frame_paths: list[str] = []
        for index, timestamp in enumerate(_frame_times(window, max_frames), 1):
            relative_path = Path(run_id) / window_id / f"frame-{index:03d}.jpg"
            destination = output_dir / relative_path
            extract_frame(source, timestamp, destination)
            frame_paths.append(relative_path.as_posix())
        sampled.append(
            {
                "window_id": window_id,
                "t_start": window["t_start"],
                "t_end": window["t_end"],
                "frames": frame_paths,
            }
        )
    return {
        "video_id": windows_artifact.get("video_id", source.stem),
        "run_id": run_id,
        "source": str(source),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "max_frames_per_window": max_frames,
        "windows": sampled,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Source MP4 path")
    parser.add_argument(
        "--windows", type=Path, required=True, help="ingest.py windows JSON"
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="frames/ directory"
    )
    parser.add_argument(
        "--output", type=Path, default=None, help="Optional samples JSON path"
    )
    parser.add_argument("--run-id", required=True, help="Run-scoped evidence namespace")
    parser.add_argument("--max-frames", type=int, default=DEFAULT_MAX_FRAMES)
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"input does not exist: {args.input}")
    if not args.windows.is_file():
        parser.error(f"windows artifact does not exist: {args.windows}")
    windows_artifact = json.loads(args.windows.read_text(encoding="utf-8"))
    artifact = extract_frames(
        args.input,
        windows_artifact,
        args.output_dir,
        run_id=args.run_id,
        max_frames=args.max_frames,
    )
    output = args.output or args.output_dir.parent / "samples.json"
    _write_json(output, artifact)
    print(
        f"sampled {len(artifact['windows'])} windows into {args.output_dir}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
