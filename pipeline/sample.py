"""Extract the frames a vision model actually needs to judge a candidate window.

Naive sampling FAILS on wide fixed-camera football, and it fails silently. The
first real run captioned both goals as "nothing happened", for two reasons:

  1. The whole 100m pitch squeezed into 960px makes players ~5px tall. Nothing
     is legible — not the ball, not a shot, not a keeper.
  2. Evenly-spaced samples across the window missed the goal entirely, because
     the motion peak fires on the CELEBRATION, so the goal sits near the window
     start.

So we sample two kinds of frame:

  TIGHT — cropped around the tracked BALL, so the model can see the actual play.
  WIDE  — the whole pitch, AFTER the window, so the model can see the
          consequences. At this camera distance you usually cannot see the ball
          cross the line; what you can see is every player walking back to the
          centre circle for a kickoff, which is what a goal actually looks like
          from the stand.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .track import probe_size, track

DEFAULT_TIGHT_FRAMES = 5
DEFAULT_WIDE_FRAMES = 3
DEFAULT_BROADCAST_FRAMES = 8
AFTERMATH_SECONDS = 8.0      # look PAST the window: the restart is the evidence
MAX_SIGHTING_GAP_FRAMES = 25 # a sighting >1s from the sample time tells us nothing useful
TIGHT_CROP_W, TIGHT_CROP_H = 1400, 788      # 16:9 window around the ball
WIDE_HEIGHT_FRACTION = 0.65                 # drop empty foreground turf from wide shots


def _tight_times(window: dict[str, Any], n: int) -> list[float]:
    """Spread across the FIRST 75% of the window: the event is early (the motion
    peak that created the window fires on the aftermath)."""
    start, end = float(window["t_start"]), float(window["t_end"])
    span = max(0.1, (end - start) * 0.75)
    if n == 1:
        return [start + span / 2]
    return [round(start + span * i / (n - 1), 3) for i in range(n)]


def _wide_times(window: dict[str, Any], n: int, duration: float) -> list[float]:
    """From late in the window into the aftermath — where the restart happens."""
    start, end = float(window["t_start"]), float(window["t_end"])
    lo = start + (end - start) * 0.8
    hi = min(duration - 0.1, end + AFTERMATH_SECONDS)
    if hi <= lo or n == 1:
        return [min(duration - 0.1, end)]
    return [round(lo + (hi - lo) * i / (n - 1), 3) for i in range(n)]


def _run_ffmpeg(cmd: list[str], what: str) -> None:
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"{what} failed: {result.stderr.decode(errors='replace').strip()}")


def extract_tight(source: Path, t: float, ball: tuple[float, float],
                  size: tuple[int, int], destination: Path) -> None:
    """Crop around the ball so the play is legible."""
    src_w, src_h = size
    cw, ch = min(TIGHT_CROP_W, src_w), min(TIGHT_CROP_H, src_h)
    x = max(0.0, min(float(src_w - cw), ball[0] - cw / 2))
    y = max(0.0, min(float(src_h - ch), ball[1] - ch / 2))
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, t):.3f}",
         "-i", str(source), "-frames:v", "1",
         "-vf", f"crop={cw}:{ch}:{x:.0f}:{y:.0f},scale=960:-2,format=yuvj420p",
         "-q:v", "2", "-y", str(destination)],
        f"tight frame at {t:.2f}s",
    )


def extract_wide(source: Path, t: float, size: tuple[int, int], destination: Path) -> None:
    """Whole pitch, so the model can read the consequences (restart, celebration)."""
    src_w, src_h = size
    ch = int(src_h * WIDE_HEIGHT_FRACTION)
    y = int(src_h * 0.06)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, t):.3f}",
         "-i", str(source), "-frames:v", "1",
         "-vf", f"crop={src_w}:{ch}:0:{y},scale=1280:-2,format=yuvj420p",
         "-q:v", "2", "-y", str(destination)],
        f"wide frame at {t:.2f}s",
    )


def extract_full(source: Path, t: float, size: tuple[int, int], destination: Path) -> None:
    """Extract an aspect-preserving full frame from directed broadcast footage."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, t):.3f}",
         "-i", str(source), "-frames:v", "1",
         "-vf", "scale=1280:-2,format=yuvj420p",
         "-q:v", "2", "-y", str(destination)],
        f"full frame at {t:.2f}s",
    )


def extract_frames(
    source: Path,
    windows_artifact: dict[str, Any],
    output_dir: Path,
    *,
    run_id: str,
    tight_frames: int = DEFAULT_TIGHT_FRAMES,
    wide_frames: int = DEFAULT_WIDE_FRAMES,
) -> dict[str, Any]:
    """Extract ball-tracked tight frames + wide aftermath frames per window."""

    profile = str(windows_artifact.get("profile", "fixed"))
    if profile == "broadcast":
        size = probe_size(source)
        duration = float(windows_artifact.get("duration") or 0.0)
        output_dir.mkdir(parents=True, exist_ok=True)

        sampled: list[dict[str, Any]] = []
        for window in windows_artifact.get("windows", []):
            window_id = str(window["id"])
            t_start, t_end = float(window["t_start"]), float(window["t_end"])
            # Cap the last sample strictly inside the file. Sampling at exactly
            # `duration` makes ffmpeg exit cleanly WITHOUT writing a frame (the
            # same trap _wide_times() guards against), which would make
            # samples.json overclaim the frame count. Fall back when duration is
            # absent so a missing top-level duration cannot collapse the window.
            reach = t_end + AFTERMATH_SECONDS
            end = min(duration - 0.1, reach) if duration else reach
            times = [
                round(
                    t_start + (end - t_start) * i / (DEFAULT_BROADCAST_FRAMES - 1),
                    3,
                )
                for i in range(DEFAULT_BROADCAST_FRAMES)
            ]

            paths: list[str] = []
            for i, t in enumerate(times, 1):
                rel = Path(run_id) / window_id / f"frame-{i:03d}.jpg"
                extract_full(source, t, size, output_dir / rel)
                paths.append(rel.as_posix())

            sampled.append({
                "window_id": window_id,
                "t_start": t_start,
                "t_end": t_end,
                "frames": paths,
                "profile": "broadcast",
                "ball_tracked": None,
            })
            print(
                f"  {window_id}: {len(times)} full broadcast frames "
                "(ball tracking skipped)",
                file=sys.stderr,
            )

        return {
            "video_id": windows_artifact.get("video_id", source.stem),
            "run_id": run_id,
            "source": str(source),
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "profile": "broadcast",
            "frames_per_window": DEFAULT_BROADCAST_FRAMES,
            "windows": sampled,
        }

    if tight_frames < 1 or wide_frames < 0:
        raise ValueError("need at least one tight frame and non-negative wide frames")
    size = probe_size(source)
    duration = float(windows_artifact.get("duration") or 0.0)
    output_dir.mkdir(parents=True, exist_ok=True)

    sampled: list[dict[str, Any]] = []
    for window in windows_artifact.get("windows", []):
        window_id = str(window["id"])
        t_start, t_end = float(window["t_start"]), float(window["t_end"])
        tights = _tight_times(window, tight_frames)
        wides = _wide_times(window, wide_frames, duration or t_end + AFTERMATH_SECONDS)

        # Track the ball once across the window (+ a little slack for the crops).
        span_end = min(duration or t_end, t_end + 1.0)
        xs, ys, seen = track(source, t_start, max(0.5, span_end - t_start))

        # Crop only around frames where the ball was ACTUALLY SEEN, and only when
        # the sighting is CLOSE IN TIME. A coasted guess — or a sighting eight
        # seconds away — points the crop at empty grass, and the model then
        # dutifully reports "nothing happened" for a goal. When we don't know
        # where the ball is, say so: fall back to an honest whole-pitch frame
        # rather than a confident-looking crop of turf.
        seen_idx = [i for i, ok in enumerate(seen) if ok]

        def ball_at(t: float) -> tuple[float, float] | None:
            if not seen_idx or not xs:
                return None
            want = int((t - t_start) * 25)
            best = min(seen_idx, key=lambda i: abs(i - want))
            if abs(best - want) > MAX_SIGHTING_GAP_FRAMES:
                return None
            return (xs[best], ys[best])

        paths: list[str] = []
        blind = 0
        for i, t in enumerate(tights, 1):
            ball = ball_at(t)
            rel = Path(run_id) / window_id / f"tight-{i:03d}.jpg"
            if ball is None:
                blind += 1
                extract_wide(source, t, size, output_dir / rel)
            else:
                extract_tight(source, t, ball, size, output_dir / rel)
            paths.append(rel.as_posix())
        for i, t in enumerate(wides, 1):
            rel = Path(run_id) / window_id / f"wide-{i:03d}.jpg"
            extract_wide(source, t, size, output_dir / rel)
            paths.append(rel.as_posix())

        sampled.append({
            "window_id": window_id,
            "t_start": t_start,
            "t_end": t_end,
            "frames": paths,
            "ball_tracked": (sum(seen) / len(seen)) if seen else 0.0,
            "tight_frames_without_ball": blind,
        })
        note = f", {blind} fell back to wide (no nearby sighting)" if blind else ""
        print(
            f"  {window_id}: {len(tights)} tight + {len(wides)} wide  "
            f"(ball tracked {sampled[-1]['ball_tracked']:.0%}{note})",
            file=sys.stderr,
        )

    return {
        "video_id": windows_artifact.get("video_id", source.stem),
        "run_id": run_id,
        "source": str(source),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "tight_frames_per_window": tight_frames,
        "wide_frames_per_window": wide_frames,
        "windows": sampled,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="SOURCE MP4 (use the highest resolution available — the tight "
                             "crops come out of it)")
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tight-frames", type=int, default=DEFAULT_TIGHT_FRAMES)
    parser.add_argument("--wide-frames", type=int, default=DEFAULT_WIDE_FRAMES)
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"input does not exist: {args.input}")
    if not args.windows.is_file():
        parser.error(f"windows artifact does not exist: {args.windows}")

    windows_artifact = json.loads(args.windows.read_text(encoding="utf-8"))
    artifact = extract_frames(
        args.input, windows_artifact, args.output_dir,
        run_id=args.run_id,
        tight_frames=args.tight_frames,
        wide_frames=args.wide_frames,
    )
    output = args.output or args.output_dir.parent / "samples.json"
    _write_json(output, artifact)
    print(f"sampled {len(artifact['windows'])} windows into {args.output_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
