"""Ball tracker: finds the ball in a wide fixed-camera shot.

Finding a football in a wide shot is hard for a reason: the ball is a ~6px white
blob, and the frame is FULL of white things — one team's kit, every pitch line,
the goal frame, the netting, fences, tents. No single cue works.

So we require four things at once:
  white   — bright and not grass-green
  moving  — a frame difference kills every static line, post and fence
  tiny    — a player's white shirt is an order of magnitude larger in area
  on-pitch— inside the grass mask, which kills the background clutter

Then we track: predict from last position + velocity, and only accept a
detection inside a gate around that prediction. That stops the tracker from
teleporting onto a white shirt across the pitch. When the ball is genuinely
lost (occluded in a ruck), we coast on the prediction, then fall back to the
motion-cluster estimate rather than inventing a position.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

W, H = 2048, 540                 # analysis res: ball ~3px, a player's shirt ~10px
FPS = 25.0

MOTION_THRESH = 26               # 0-255 gray delta
MIN_BLOB, MAX_BLOB = 2, 26       # px area at analysis res. A shirt is 60-150.
# A struck ball tops out around 35 m/s. On a ~105m pitch spanning ~1800 analysis
# px, that is ~24 px/frame at 25fps. Anything faster is not a ball — it is the
# tracker teleporting. Keep the gate near the physical limit.
GATE_PX = 45
MAX_GATE_GROWTH = 6              # px of extra gate per missed frame (bounded)
LOST_AFTER = 12                  # frames of no detection before we stop trusting the track
MIN_ISOLATION = 0.80             # ring around the blob must be mostly grass
# Re-acquisition must stay near where we last saw the ball, or the tracker jumps
# to a SPARE BALL on the touchline — perfect isolation (it is, after all, a
# football on grass), never moves, and never gives the real ball back. That is
# exactly how the first run lost the second goal.
#
# But the radius cannot be FIXED either: while we are lost the ball keeps moving,
# so the search must widen with time — just never far enough to cross the pitch.
REACQUIRE_RADIUS = 260           # starting search radius, analysis px
REACQUIRE_GROWTH = 12            # widen per frame still lost
REACQUIRE_MAX = 620              # hard ceiling: ~1/3 of the pitch, never the touchline
REACQUIRE_MIN_ISOLATION = 0.90   # re-acquisition needs a BALL, not a plausible blob
CERTAIN_BALL_ISOLATION = 0.95    # good enough to jump anywhere on the pitch for


def _frames(src: Path, start: float, dur: float):
    """Stream RGB frames at analysis resolution."""
    proc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
         "-vf", f"fps={FPS},scale={W}:{H}", "-f", "rawvideo",
         "-pix_fmt", "rgb24", "pipe:1"],
        stdout=subprocess.PIPE)
    fsz = W * H * 3
    try:
        while True:
            buf = proc.stdout.read(fsz)
            if len(buf) < fsz:
                break
            yield np.frombuffer(buf, np.uint8).reshape(H, W, 3).astype(np.int16)
    finally:
        proc.stdout.close()
        proc.wait()


def _blobs(mask: np.ndarray) -> list[tuple[float, float, int]]:
    """Greedy clustering of candidate pixels -> (x, y, area). No scipy needed."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return []
    pts = np.stack([xs, ys], 1).astype(np.float32)
    used = np.zeros(len(pts), bool)
    out = []
    for i in range(len(pts)):
        if used[i]:
            continue
        d = np.abs(pts - pts[i]).max(1)
        grp = (d <= 3) & ~used            # 8-connected-ish, cheap
        used |= grp
        members = pts[grp]
        out.append((float(members[:, 0].mean()),
                    float(members[:, 1].mean()),
                    int(grp.sum())))
    return out


def _isolation(grass: np.ndarray, cx: float, cy: float, rad: int = 7) -> float:
    """Fraction of a ring around the blob that is plain grass.

    THE key discriminator. A ball sitting on the pitch is ringed by green. A
    player's shirt — or a huddle of subs warming up on the touchline, which is
    what the naive tracker locked onto — is ringed by more bodies, kit and
    shadow. Ball ~1.0; player ~0.3.
    """
    x, y = int(round(cx)), int(round(cy))
    x0, x1 = max(0, x - rad), min(W, x + rad + 1)
    y0, y1 = max(0, y - rad), min(H, y + rad + 1)
    patch = grass[y0:y1, x0:x1]
    if patch.size == 0:
        return 0.0
    inner = grass[max(0, y - 2):y + 3, max(0, x - 2):x + 3]
    ring_green = int(patch.sum()) - int(inner.sum())
    ring_total = patch.size - inner.size
    return ring_green / ring_total if ring_total > 0 else 0.0


def probe_size(src: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(src)],
        capture_output=True, check=True).stdout.decode().strip()
    w, h = out.split(",")[:2]
    return int(w), int(h)


def track(src: Path, start: float, dur: float) -> tuple[list[float], list[float], list[bool]]:
    """Return per-frame ball (x, y) in SOURCE px, plus whether it was actually seen."""

    SRC_W, SRC_H = probe_size(src)
    # Independent scales per axis. Deriving ONE scale from width happens to be
    # correct for a 4096x1080 panorama (both axes halve) and is wrong for every
    # other aspect ratio — a 1920x1080 broadcast would place every y at 47% of
    # its true value, putting all the tight crops in the wrong place.
    scale_x = SRC_W / W
    scale_y = SRC_H / H
    prev_gray = None
    pos: np.ndarray | None = None
    vel = np.zeros(2, np.float32)
    missing = 0

    xs: list[float] = []
    ys: list[float] = []
    seen: list[bool] = []

    for frame in _frames(src, start, dur):
        r, g, b = frame[..., 0], frame[..., 1], frame[..., 2]
        gray = frame.mean(2)

        grass = (g > 60) & (g > r + 12) & (g > b + 12)
        # Dilate the grass mask downward/sideways cheaply so a ball ON a line,
        # or right at the pitch edge, still counts as on-pitch.
        pitch = grass
        for sh in (1, 2, 3):
            pitch = pitch | np.roll(grass, sh, 0) | np.roll(grass, -sh, 0) \
                          | np.roll(grass, sh, 1) | np.roll(grass, -sh, 1)

        white = (r > 135) & (g > 135) & (b > 125) & (np.abs(g - r) < 60)

        if prev_gray is None:
            prev_gray = gray
            xs.append(SRC_W / 2)
            ys.append(SRC_H / 2)
            seen.append(False)
            continue

        moving = np.abs(gray - prev_gray) > MOTION_THRESH
        prev_gray = gray

        cand = white & moving & pitch
        blobs = [
            bl for bl in _blobs(cand)
            if MIN_BLOB <= bl[2] <= MAX_BLOB
            and _isolation(grass, bl[0], bl[1]) >= MIN_ISOLATION
        ]

        pred = (pos + vel) if (pos is not None and missing <= LOST_AFTER) else None
        pick = None
        if blobs:
            if pred is None:
                # Acquire, or RE-acquire after a long loss. Isolation identifies a
                # ball (the true ball scored 0.95 against 137 rivals at 0.90) —
                # but ONLY near where we last saw it, or we lock onto a spare ball
                # on the touchline and never come back.
                # RE-ACQUIRING demands more evidence than merely continuing a
                # track. A ball alone on grass is unmistakably isolated; a scrap
                # of a white shirt is only borderline. With the same loose bar,
                # re-acquisition lands on a player and stays there.
                near = [
                    bl for bl in blobs
                    if _isolation(grass, bl[0], bl[1]) >= REACQUIRE_MIN_ISOLATION
                ]
                if pos is not None:
                    # Bounded search that widens with time lost. The unbounded
                    # version teleported across the pitch; a purely bounded one
                    # traps the tracker on whatever it mistakenly locked onto.
                    radius = min(
                        REACQUIRE_MAX,
                        REACQUIRE_RADIUS + REACQUIRE_GROWTH * max(0, missing - LOST_AFTER),
                    )
                    bounded = [
                        bl for bl in near
                        if np.hypot(bl[0] - pos[0], bl[1] - pos[1]) <= radius
                    ]
                    # Escape hatch, deliberately narrow: a blob ANYWHERE may be
                    # taken only if it is near-certainly a ball. A spare ball on
                    # the touchline cannot qualify — it never moves, so it never
                    # survives the motion mask in the first place.
                    if not bounded:
                        bounded = [
                            bl for bl in near
                            if _isolation(grass, bl[0], bl[1]) >= CERTAIN_BALL_ISOLATION
                        ]
                    near = bounded
                if near:
                    pick = max(near, key=lambda bl: _isolation(grass, bl[0], bl[1]))
            else:
                gate = GATE_PX + MAX_GATE_GROWTH * missing
                gated = [
                    bl for bl in blobs
                    if np.hypot(bl[0] - pred[0], bl[1] - pred[1]) <= gate
                ]
                if gated:
                    pick = min(
                        gated,
                        key=lambda bl: np.hypot(bl[0] - pred[0], bl[1] - pred[1]),
                    )

        if pick is not None:
            new = np.array([pick[0], pick[1]], np.float32)
            vel = new - pos if pos is not None else np.zeros(2, np.float32)
            vel = np.clip(vel, -40, 40)
            pos = new
            missing = 0
            seen.append(True)
        else:
            missing += 1
            if pos is not None and missing <= LOST_AFTER:
                pos = pos + vel * 0.5          # coast, decaying
                vel *= 0.85
            seen.append(False)

        if pos is None:
            xs.append(SRC_W / 2)
            ys.append(SRC_H / 2)
        else:
            xs.append(float(pos[0]) * scale_x)
            ys.append(float(pos[1]) * scale_y)

    return xs, ys, seen
