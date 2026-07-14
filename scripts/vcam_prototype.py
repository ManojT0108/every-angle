"""PROTOTYPE — NOT REVIEWED, NOT WIRED INTO THE PIPELINE.

Virtual broadcast camera: crop a moving 16:9 window out of the fixed panorama
so the output looks like an operator followed the play. Nothing physical moves.

Why v1 stuttered, and what fixes it:
  1. sendcmd HOLDS a value until the next command, so 5 Hz commands made the
     camera teleport 5x/sec. Now we emit one command per video frame.
  2. The raw motion centroid jumps as players scatter. Now: median filter to
     reject spikes, then a long moving average.
  3. A real operator can't snap instantly. Now: eased follow with a max pan
     speed, so the camera glides toward the action.
  4. A real operator doesn't twitch at every micro-movement. Now: a deadzone —
     if the action is near frame centre, don't move at all.
  5. Vertical wobble is the worst kind. Now: full-height crop, y is FIXED.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ball_track

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "data/match-001/source/117093_panorama_1st_half.mp4"
OUT = REPO / "data/match-001/preview"
OUT.mkdir(parents=True, exist_ok=True)

SRC_W, SRC_H = 4096, 1080
# The panorama is barrel-distorted: the pitch is a CURVED band, sitting high in
# frame near the goals and low at the centre circle. A fixed y is therefore
# wrong everywhere except one spot. We measure the band per column (see
# pitch_centreline) and let the crop follow that curve as it pans — no jitter,
# because the curve is a smooth function of an already-smoothed camera x.
CROP_W, CROP_H = 1280, 720      # 3.2x zoom. Short enough to have 360px of vertical travel —
HEADROOM = 150                  # a 900-tall crop can only move 180px, far less than the fisheye curve
VIDEO_FPS = 25.0                # emit one crop command per real frame
SAMPLE_FPS = 10.0               # motion analysis rate
GRID_W, GRID_H = 128, 34

MAX_PAN_PX_PER_S = 420.0        # camera speed limit, in source pixels
DEADZONE_PX = 45.0              # tighter: we now know where the ball actually is
FOLLOW = 0.10                   # easing per frame toward target


SHARPNESS = 8       # power-weighting: pulls the target to the DENSE cluster, not the mean


def motion_targets(start: float, dur: float) -> list[float]:
    """Raw x of the densest motion cluster, sampled at SAMPLE_FPS.

    A plain centroid FAILS here: averaging 22 players (keeper at one end,
    attack at the other) points the camera at midfield while the goal happens
    elsewhere. Raising column energy to a power before taking the centroid is a
    soft arg-max — it locks onto the cluster of players around the ball and
    largely ignores the lone defender jogging at the far end.
    """
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}",
         "-t", f"{dur:.3f}", "-i", str(SRC),
         "-vf", f"fps={SAMPLE_FPS},scale={GRID_W}:{GRID_H},format=gray",
         "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"],
        capture_output=True, check=True)
    raw, fsz = proc.stdout, GRID_W * GRID_H
    frames = [raw[i * fsz:(i + 1) * fsz] for i in range(len(raw) // fsz)]
    out: list[float] = []
    for a, b in zip(frames, frames[1:]):
        cols = [0.0] * GRID_W
        for i in range(fsz):
            d = a[i] - b[i]
            cols[i % GRID_W] += d if d > 0 else -d
        # Spatially blur the profile so one twitchy pixel column can't win,
        # then power-weight so the densest region dominates the centroid.
        blur = [
            sum(cols[max(0, j - 2):min(GRID_W, j + 3)]) / 5.0
            for j in range(GRID_W)
        ]
        peak = max(blur) or 1.0
        w = [(c / peak) ** SHARPNESS for c in blur]
        tot = sum(w)
        out.append(
            (sum(j * v for j, v in enumerate(w)) / tot / GRID_W * SRC_W)
            if tot else SRC_W / 2
        )
    return out


def pitch_top() -> list[float]:
    """Per column, the y of the FAR TOUCHLINE — the top edge of the grass.

    This is the fisheye curve that matters. Play happens in the band just below
    the far touchline; the grass below that is empty foreground. Framing down
    from this edge is what a real broadcast camera does, and it automatically
    rides the barrel distortion (the pitch sits ~100px higher at the ends than
    at the centre circle). Measured once from a mid-match frame.
    """
    w, h = 256, 135
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "1200",
         "-i", str(SRC), "-frames:v", "1",
         "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "pipe:1"],
        capture_output=True, check=True)
    buf = proc.stdout
    tops: list[float] = []
    limits: list[float] = []
    for x in range(w):
        top = h * 0.25                                    # fallback
        run = 0
        for y in range(h):
            i = (y * w + x) * 3
            r, g, b = buf[i], buf[i + 1], buf[i + 2]
            if g > 60 and g > r + 12 and g > b + 12:      # grass, not sky/track/black
                run += 1
                if run >= 3:                              # 3 rows deep = really the pitch
                    top = y - 2
                    break
            else:
                run = 0
        tops.append(top / h * SRC_H)
        # The fisheye leaves BLACK wedges in the corners. Find the first row of
        # real image in this column so the crop can never include them.
        limit = 0
        for y in range(h):
            i = (y * w + x) * 3
            if buf[i] + buf[i + 1] + buf[i + 2] > 60:     # not the black border
                limit = y
                break
        limits.append(limit / h * SRC_H)
    return (
        moving_average(tops, k=25),                       # the pitch curve
        moving_average(limits, k=9),                      # the black-border floor
    )


def median_filter(xs: list[float], k: int = 5) -> list[float]:
    """Reject single-sample spikes (a stray player, a shadow) before smoothing."""
    out = []
    for i in range(len(xs)):
        lo, hi = max(0, i - k // 2), min(len(xs), i + k // 2 + 1)
        out.append(sorted(xs[lo:hi])[(hi - lo) // 2])
    return out


def moving_average(xs: list[float], k: int) -> list[float]:
    out = []
    for i in range(len(xs)):
        lo, hi = max(0, i - k // 2), min(len(xs), i + k // 2 + 1)
        out.append(sum(xs[lo:hi]) / (hi - lo))
    return out


def resample(xs: list[float], src_fps: float, dst_fps: float, n: int) -> list[float]:
    """Linear-interpolate the target path up to the video frame rate."""
    out = []
    for i in range(n):
        pos = i / dst_fps * src_fps
        lo = min(int(pos), len(xs) - 1)
        hi = min(lo + 1, len(xs) - 1)
        frac = pos - lo
        out.append(xs[lo] * (1 - frac) + xs[hi] * frac)
    return out


def camera_path(targets: list[float]) -> list[float]:
    """Simulate an operator: ease toward the action, speed-limited, with a deadzone."""
    max_step = MAX_PAN_PX_PER_S / VIDEO_FPS
    cam = targets[0]
    path = []
    for t in targets:
        err = t - cam
        if abs(err) > DEADZONE_PX:                       # inside deadzone: hold still
            step = max(-max_step, min(max_step, err * FOLLOW))
            cam += step
        path.append(max(0.0, min(float(SRC_W - CROP_W), cam - CROP_W / 2)))
    return path


def cut(name: str, start: float, end: float) -> None:
    dur = end - start
    n_frames = int(dur * VIDEO_FPS) + 2

    # TARGET = the ball itself. Motion energy was only ever a proxy for it, and
    # a bad one: it averages 22 players, so it points at midfield while the goal
    # happens at one end. We fall back to the motion cluster only where the ball
    # is genuinely lost (occluded in a ruck), so the camera never freezes.
    ball_x, _ball_y, seen = ball_track.track(start, dur)
    motion = resample(
        moving_average(median_filter(motion_targets(start, dur)), k=int(SAMPLE_FPS * 2)),
        SAMPLE_FPS, VIDEO_FPS, len(ball_x),
    )
    targets = [
        bx if ok else mx for bx, ok, mx in zip(ball_x, seen, motion)
    ]
    # Smooth in the video-frame domain (25 Hz): ~1.2s of look-around, so a
    # deflection or a bobble doesn't yank the camera.
    smoothed = moving_average(median_filter(targets, k=9), k=int(VIDEO_FPS * 1.2))
    path = camera_path(resample(smoothed, VIDEO_FPS, VIDEO_FPS, n_frames))
    print(f"  ball tracked in {sum(seen)}/{len(seen)} frames ({sum(seen)/len(seen):.0%})")

    # Vertical framing rides the fisheye curve: start just above the far
    # touchline at whatever x we're pointed at.
    band, border = pitch_top()
    lines = []
    for i, x in enumerate(path):
        # Sample the curves at the crop's WIDEST point, not its centre: the black
        # wedge bites the corners, so the worst column decides the floor.
        cols = [
            int(v / SRC_W * len(band))
            for v in (x + 8, x + CROP_W / 2, x + CROP_W - 8)
        ]
        cols = [min(len(band) - 1, max(0, c)) for c in cols]
        top_y = band[cols[1]]
        floor = max(border[c] for c in cols)              # deepest black in this crop
        y = max(floor, min(float(SRC_H - CROP_H), top_y - HEADROOM))
        t = i / VIDEO_FPS
        lines.append(f"{t:.3f} crop x {x:.0f};")
        lines.append(f"{t:.3f} crop y {y:.0f};")
    cmds = OUT / f"{name}.cmds"
    cmds.write_text("\n".join(lines) + "\n")

    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(SRC),
         "-vf", (f"sendcmd=f='{cmds}',crop={CROP_W}:{CROP_H}:x=0:y=0,"
                 "scale=1280:720"),
         "-c:v", "libx264", "-crf", "22", "-preset", "veryfast",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart",
         str(OUT / f"{name}_vcam.mp4")], check=True)

    travel = max(path) - min(path)
    print(f"{name}: {dur:.1f}s, {len(path)} frames, camera travelled {travel:.0f}px")


if __name__ == "__main__":
    # The detector's windows START ~1s before each goal, because the motion peak
    # fires on the CELEBRATION, not the shot — so a raw window clip is all
    # aftermath. A goal clip needs the build-up: roll back well before the ball
    # goes in. (Real fix for the product: per-event-type pre/post roll.)
    for name, goal_t in (("goal1", 1412.5), ("goal2", 2375.1)):
        cut(name, goal_t - 12.0, goal_t + 8.0)
