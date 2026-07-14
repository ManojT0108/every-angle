"""Virtual broadcast camera: crop a moving 16:9 window out of a fixed wide shot.

A fixed camera sees the whole pitch, so a naive 16:9 clip is a letterboxed strip
with the players as specks. Nothing about that looks like football.

Instead we pan INSIDE the still frame: track the ball, crop a window around it,
and move that window like an operator would — eased, speed-limited, and with a
deadzone so it holds still when play is centred. Nothing physical moves; we are
simply choosing which pixels of a 4K frame to show. This is what Veo, Pixellot
and Spiideo sell to amateur clubs.

Only applies to WIDE fixed sources. A broadcast feed is already framed by a human
director; re-cropping it would be vandalism (see `needs_virtual_camera`).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .track import probe_size, track

VIDEO_FPS = 25.0
CROP_ASPECT = 16 / 9

MAX_PAN_PX_PER_S = 420.0     # a camera operator cannot snap instantly
DEADZONE_PX = 45.0           # don't twitch when the ball is already centred
FOLLOW = 0.10                # easing toward the target, per frame
SMOOTH_S = 1.2               # look-around window, seconds
HEADROOM_FRAC = 0.14         # sit the play band mid-frame, stand visible above

# A fixed camera framing a whole pitch is far wider than 16:9. A broadcast feed
# is not. This is how we tell them apart without asking the user.
WIDE_ASPECT_THRESHOLD = 2.4


def needs_virtual_camera(source: Path) -> bool:
    """True for a wide fixed panorama; False for an already-directed broadcast."""
    w, h = probe_size(source)
    return (w / h) >= WIDE_ASPECT_THRESHOLD


def pitch_curve(source: Path) -> tuple[list[float], list[float]]:
    """Per column: (top of the grass, first row of real image).

    A wide panorama is barrel-distorted — the pitch is a CURVED band, sitting
    ~200px higher near the goals than at the centre circle — so a fixed vertical
    crop is wrong everywhere but one spot. We measure the far touchline rather
    than assuming a lens model, which means this also works on a flat, undistorted
    fixed camera: the curve simply comes out flat.

    The second list is the black-corner floor: the fisheye leaves black wedges,
    and the crop must never include them.
    """
    src_w, src_h = probe_size(source)
    w, h = 256, 135
    raw = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "60",
         "-i", str(source), "-frames:v", "1", "-vf", f"scale={w}:{h}",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
        capture_output=True, check=True).stdout

    tops: list[float] = []
    floors: list[float] = []
    for x in range(w):
        top, run = h * 0.25, 0
        for y in range(h):
            i = (y * w + x) * 3
            r, g, b = raw[i], raw[i + 1], raw[i + 2]
            if g > 60 and g > r + 12 and g > b + 12:      # grass, not sky/track/black
                run += 1
                if run >= 3:
                    top = y - 2
                    break
            else:
                run = 0
        tops.append(top / h * src_h)

        floor = 0
        for y in range(h):
            i = (y * w + x) * 3
            if raw[i] + raw[i + 1] + raw[i + 2] > 60:     # first non-black row
                floor = y
                break
        floors.append(floor / h * src_h)

    return _mean(tops, 25), _mean(floors, 9)


def _median(xs: list[float], k: int) -> list[float]:
    out = []
    for i in range(len(xs)):
        lo, hi = max(0, i - k // 2), min(len(xs), i + k // 2 + 1)
        out.append(sorted(xs[lo:hi])[(hi - lo) // 2])
    return out


def _mean(xs: list[float], k: int) -> list[float]:
    out = []
    for i in range(len(xs)):
        lo, hi = max(0, i - k // 2), min(len(xs), i + k // 2 + 1)
        out.append(sum(xs[lo:hi]) / (hi - lo))
    return out


def _camera_path(targets: list[float], crop_w: float, src_w: int) -> list[float]:
    """An operator's pan: eased, speed-limited, with a deadzone."""
    max_step = MAX_PAN_PX_PER_S / VIDEO_FPS
    cam = targets[0] if targets else src_w / 2
    path: list[float] = []
    for t in targets:
        err = t - cam
        if abs(err) > DEADZONE_PX:
            cam += max(-max_step, min(max_step, err * FOLLOW))
        path.append(max(0.0, min(float(src_w - crop_w), cam - crop_w / 2)))
    return path


def plan_shot(source: Path, t_start: float, t_end: float) -> tuple[Path, int, int, int]:
    """Track the ball across [t_start, t_end] and write an ffmpeg sendcmd timeline.

    Returns (cmds_file, crop_w, crop_h). sendcmd HOLDS a value until the next
    command, so we must emit one per VIDEO frame — commands at a lower rate make
    the camera teleport rather than pan, which reads as a violent stutter.
    """
    src_w, src_h = probe_size(source)
    # The crop must be SHORT enough to actually move: a 0.9*H window has almost
    # no vertical travel, far less than the fisheye curve demands.
    crop_h = int(src_h * 0.66) // 2 * 2
    crop_w = int(crop_h * CROP_ASPECT) // 2 * 2
    crop_w = min(crop_w, src_w)

    dur = max(0.5, t_end - t_start)
    xs, ys, seen = track(source, t_start, dur)

    # Only steer by frames where the ball was ACTUALLY seen. A coasted guess
    # points the camera at empty grass.
    seen_idx = [i for i, ok in enumerate(seen) if ok]
    if seen_idx:
        targets = []
        for i in range(len(xs)):
            nearest = min(seen_idx, key=lambda j: abs(j - i))
            targets.append(xs[nearest])
    else:
        targets = [src_w / 2] * max(1, len(xs))

    smoothed = _mean(_median(targets, 9), int(VIDEO_FPS * SMOOTH_S))
    path = _camera_path(smoothed, crop_w, src_w)

    # Vertical framing RIDES the fisheye curve at whatever x we are pointed at.
    # It never wobbles, because the curve is a smooth function of an already
    # smoothed camera path — not a per-frame measurement.
    tops, floors = pitch_curve(source)
    headroom = crop_h * 0.30           # play sits mid-frame, far stand above

    lines: list[str] = []
    for i, x in enumerate(path):
        cols = [
            min(len(tops) - 1, max(0, int(v / src_w * len(tops))))
            for v in (x + 8, x + crop_w / 2, x + crop_w - 8)
        ]
        top_y = tops[cols[1]]
        floor = max(floors[c] for c in cols)       # deepest black in this crop
        y = max(floor, min(float(src_h - crop_h), top_y - headroom))
        t = i / VIDEO_FPS
        lines.append(f"{t:.3f} crop x {x:.0f};")
        lines.append(f"{t:.3f} crop y {y:.0f};")

    cmds = source.parent / f".vcam-{int(t_start)}-{int(t_end)}.cmds"
    cmds.write_text("\n".join(lines) + "\n")
    return cmds, crop_w, crop_h, 0


def filter_chain(source: Path, t_start: float, t_end: float) -> str:
    """The ffmpeg -vf chain that renders a virtual-camera shot at 720p."""
    cmds, crop_w, crop_h, y = plan_shot(source, t_start, t_end)
    return (
        f"sendcmd=f='{cmds}',crop={crop_w}:{crop_h}:x=0:y={y},"
        "scale=1280:720,format=yuv420p"
    )


def probe_duration(source: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(source)],
        capture_output=True, check=True).stdout.decode().strip()
    return float(out or 0.0)
