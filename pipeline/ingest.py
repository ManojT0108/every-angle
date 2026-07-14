"""Detect inexpensive candidate windows from a match video.

Audio is decoded to short PCM chunks so RMS peaks can be found without a
Python audio dependency. Scene cuts are detected by ffmpeg's ``scene``
filter, and motion density comes from frame differences in one downscaled
grayscale stream. These signals are only gates for later captioning; they are
not event labels.
"""

from __future__ import annotations

import argparse
import array
import json
import math
import re
import statistics
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


# Bump whenever detector thresholds, cue combination, or scoring change in a
# way that alters output for identical parameters — it is part of the run
# provenance hash, so two runs that could differ must never hash the same.
DETECTOR_VERSION = "d3-percentile"

DEFAULT_SCENE_THRESHOLD = 0.35
DEFAULT_AUDIO_SAMPLE_RATE = 16_000
DEFAULT_AUDIO_WINDOW_SECONDS = 0.5
DEFAULT_AUDIO_MIN_GAP_SECONDS = 4.0
DEFAULT_AUDIO_MIN_RMS = 0.03
DEFAULT_AUDIO_MEDIAN_MULTIPLIER = 1.5
DEFAULT_PRE_ROLL = 10.0           # the event PRECEDES its cue: a crowd roar peaks after the
DEFAULT_POST_ROLL = 12.0          # ball crosses the line; motion peaks on the celebration
DEFAULT_MERGE_GAP = 8.0           # cues around a goal sit 4-6s apart; a 3s gap shattered
                                  # them into weak fragments that all fell below the cap
DEFAULT_MOTION_FRAME_RATE = 3.0
DEFAULT_MOTION_WIDTH = 160
DEFAULT_MOTION_HEIGHT = 90
DEFAULT_MOTION_INTERVAL_SECONDS = 1.0
DEFAULT_MOTION_MIN_GAP_SECONDS = 3.0
DEFAULT_MOTION_MEDIAN_MULTIPLIER = 1.5
DEFAULT_MOTION_MIN_MAGNITUDE = 0.002
DEFAULT_MAX_WINDOWS = 60          # absolute ceiling (cost control)
WINDOWS_PER_MINUTE = 0.9          # ~40 windows across a 45-min half
CUES_FOR_FULL_DENSITY = 8         # a sustained burst, not a lone spike
DEFAULT_MAX_WINDOW_SECONDS = 30.0 # a merged burst may be 90s long; the window must not be


# ---------------------------------------------------------------------------
# Two footage regimes, and they are genuinely different problems.
#
# FIXED (a camera on a pole): the crowd is a handful of parents, so audio is
#   flat; the camera never cuts, so scene cuts do not exist. MOTION is the only
#   cue that carries information, and events are crisp and isolated.
#
# BROADCAST (a directed feed): the crowd roars all night, the director cuts
#   constantly, and the camera pans — so ALL THREE cues fire continuously and
#   cue *presence* discriminates nothing. What marks a goal is a SUSTAINED
#   BURST: roar, celebration, replays, a minute of continuous noise. Events are
#   long, and the goal sits in the middle of the burst rather than at either end.
#
# One set of constants cannot serve both, and pretending otherwise means tuning
# for one and silently breaking the other. So the profile is explicit — and
# detected from the footage, not asked of the user.
# ---------------------------------------------------------------------------

PROFILES: dict[str, dict] = {
    # These are the parameters that were MEASURED at 2/2 goal recall with 25% of
    # the footage under review, and code-reviewed. They are not a guess, and they
    # are not to be "improved" to win a different dataset — that is how the goal
    # recall was quietly halved twice while chasing the broadcast case.
    "fixed": {
        "pre_roll": 5.0,
        "post_roll": 10.0,
        "merge_gap": 3.0,
        "max_window_seconds": 1e9,   # no tiling: fixed-camera events are isolated
        "density_weight": 0.0,
        "scoring": "cue_sum",        # cue diversity + summed strength
    },
    "broadcast": {
        "pre_roll": 10.0,
        "post_roll": 12.0,
        "merge_gap": 8.0,
        "max_window_seconds": 30.0,
        "density_weight": 0.35,      # a goal is a burst; a near-miss is one shout
        "scoring": "percentile",     # cue PRESENCE is meaningless here; rank by rarity
    },
}

# A directed feed cuts. A camera on a pole does not. This single number
# separates them cleanly — no user input required.
BROADCAST_CUTS_PER_MINUTE = 0.5


def detect_profile(scene_cuts: list[float], duration: float) -> str:
    """Which regime is this footage? Decided by the footage, not by the user."""
    if duration <= 0:
        return "fixed"
    rate = len(scene_cuts) / (duration / 60.0)
    return "broadcast" if rate >= BROADCAST_CUTS_PER_MINUTE else "fixed"


@dataclass(frozen=True)
class AudioPeak:
    """A local audio RMS maximum."""

    time: float
    rms: float


@dataclass(frozen=True)
class MotionPeak:
    """A local maximum in downscaled frame-difference magnitude."""

    time: float
    magnitude: float


@dataclass(frozen=True)
class CandidateWindow:
    """A time range worth sampling and captioning."""

    id: str
    t_start: float
    t_end: float
    audio_peak: bool
    scene_cut: bool
    motion_peak: bool
    score: float


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=check, capture_output=True)


def probe_duration(source: Path) -> float:
    """Return the media duration in seconds using ffprobe."""

    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source),
        ]
    )
    try:
        return max(0.0, float(result.stdout.decode().strip()))
    except (TypeError, ValueError):
        return 0.0


def _iter_audio_rms(
    source: Path,
    *,
    sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE,
    window_seconds: float = DEFAULT_AUDIO_WINDOW_SECONDS,
) -> Iterable[tuple[float, float]]:
    """Yield ``(center_time, normalized_rms)`` values from the first audio stream."""

    process = subprocess.Popen(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "s16le",
            "pipe:1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    samples_per_window = max(1, int(sample_rate * window_seconds))
    pending = array.array("h")
    sample_offset = 0
    try:
        while True:
            chunk = process.stdout.read(64 * 1024)
            if not chunk:
                break
            pcm = array.array("h")
            usable = len(chunk) - (len(chunk) % 2)
            if usable:
                pcm.frombytes(chunk[:usable])
                pending.extend(pcm)
            while len(pending) >= samples_per_window:
                frame = pending[:samples_per_window]
                del pending[:samples_per_window]
                mean_square = sum(sample * sample for sample in frame) / len(frame)
                center = (sample_offset + len(frame) / 2) / sample_rate
                yield center, math.sqrt(mean_square) / 32768.0
                sample_offset += len(frame)
        if len(pending) >= samples_per_window // 2:
            mean_square = sum(sample * sample for sample in pending) / len(pending)
            center = (sample_offset + len(pending) / 2) / sample_rate
            yield center, math.sqrt(mean_square) / 32768.0
    finally:
        process.stdout.close()
        stderr = process.stderr.read() if process.stderr is not None else b""
        return_code = process.wait()
        if return_code != 0 and stderr:
            # A video without an audio stream is a valid input for this stage.
            # Only surface other ffmpeg failures.
            message = stderr.decode(errors="replace").lower()
            if (
                "does not contain any stream" not in message
                and "audio stream" not in message
            ):
                raise RuntimeError(
                    f"ffmpeg audio decode failed: {stderr.decode(errors='replace').strip()}"
                )


def detect_audio_peaks(
    source: Path,
    *,
    sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE,
    window_seconds: float = DEFAULT_AUDIO_WINDOW_SECONDS,
    min_gap_seconds: float = DEFAULT_AUDIO_MIN_GAP_SECONDS,
    min_rms: float = DEFAULT_AUDIO_MIN_RMS,
    median_multiplier: float = DEFAULT_AUDIO_MEDIAN_MULTIPLIER,
) -> list[AudioPeak]:
    """Find loud local RMS peaks relative to the video's own noise floor."""

    levels = list(
        _iter_audio_rms(source, sample_rate=sample_rate, window_seconds=window_seconds)
    )
    if len(levels) < 3:
        return []
    rms_values = [rms for _, rms in levels]
    median = statistics.median(rms_values)
    upper_quartile = statistics.quantiles(rms_values, n=4, method="inclusive")[2]
    threshold = max(min_rms, upper_quartile, median * median_multiplier)
    peaks: list[AudioPeak] = []
    last_time = -float("inf")
    for index in range(1, len(levels) - 1):
        time, rms = levels[index]
        if rms < threshold or rms < levels[index - 1][1] or rms < levels[index + 1][1]:
            continue
        if time - last_time < min_gap_seconds:
            if peaks and rms > peaks[-1].rms:
                peaks[-1] = AudioPeak(time=time, rms=rms)
                last_time = time
            continue
        peaks.append(AudioPeak(time=time, rms=rms))
        last_time = time
    return peaks


def _iter_motion_density(
    source: Path,
    *,
    frame_rate: float = DEFAULT_MOTION_FRAME_RATE,
    width: int = DEFAULT_MOTION_WIDTH,
    height: int = DEFAULT_MOTION_HEIGHT,
    interval_seconds: float = DEFAULT_MOTION_INTERVAL_SECONDS,
) -> Iterable[tuple[float, float]]:
    """Yield per-interval frame-difference magnitude from one video decode."""

    if frame_rate <= 0 or width <= 0 or height <= 0 or interval_seconds <= 0:
        raise ValueError("motion detector dimensions, rate, and interval must be positive")
    process = subprocess.Popen(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-vf",
            (
                f"fps={frame_rate},scale={width}:{height}:flags=fast_bilinear,"
                "format=gray"
            ),
            "-an",
            "-sn",
            "-dn",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "pipe:1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    frame_size = width * height
    pending = bytearray()
    previous: bytes | None = None
    frame_index = 0
    interval_index: int | None = None
    interval_total = 0.0
    interval_count = 0
    try:
        while True:
            chunk = process.stdout.read(frame_size * 8)
            if not chunk:
                break
            pending.extend(chunk)
            while len(pending) >= frame_size:
                frame = bytes(pending[:frame_size])
                del pending[:frame_size]
                if previous is not None:
                    timestamp = frame_index / frame_rate
                    magnitude = sum(
                        abs(current - prior)
                        for current, prior in zip(frame, previous)
                    ) / (frame_size * 255.0)
                    current_interval = int(timestamp / interval_seconds)
                    if (
                        interval_index is not None
                        and current_interval != interval_index
                    ):
                        center = (interval_index + 0.5) * interval_seconds
                        yield center, interval_total / interval_count
                        interval_total = 0.0
                        interval_count = 0
                    interval_index = current_interval
                    interval_total += magnitude
                    interval_count += 1
                previous = frame
                frame_index += 1
        if interval_index is not None and interval_count:
            center = (interval_index + 0.5) * interval_seconds
            yield center, interval_total / interval_count
    finally:
        process.stdout.close()
        stderr = process.stderr.read() if process.stderr is not None else b""
        return_code = process.wait()
        if return_code != 0:
            message = stderr.decode(errors="replace").strip()
            raise RuntimeError(f"ffmpeg motion decode failed: {message}")


def detect_motion_peaks(
    source: Path,
    *,
    frame_rate: float = DEFAULT_MOTION_FRAME_RATE,
    width: int = DEFAULT_MOTION_WIDTH,
    height: int = DEFAULT_MOTION_HEIGHT,
    interval_seconds: float = DEFAULT_MOTION_INTERVAL_SECONDS,
    min_gap_seconds: float = DEFAULT_MOTION_MIN_GAP_SECONDS,
    median_multiplier: float = DEFAULT_MOTION_MEDIAN_MULTIPLIER,
    min_magnitude: float = DEFAULT_MOTION_MIN_MAGNITUDE,
) -> list[MotionPeak]:
    """Find local motion maxima relative to the video's own activity baseline."""

    levels = list(
        _iter_motion_density(
            source,
            frame_rate=frame_rate,
            width=width,
            height=height,
            interval_seconds=interval_seconds,
        )
    )
    if len(levels) < 3:
        return []
    magnitudes = [magnitude for _, magnitude in levels]
    median = statistics.median(magnitudes)
    upper_quartile = statistics.quantiles(
        magnitudes, n=4, method="inclusive"
    )[2]
    threshold = max(min_magnitude, upper_quartile, median * median_multiplier)
    peaks: list[MotionPeak] = []
    last_time = -float("inf")
    for index in range(1, len(levels) - 1):
        time, magnitude = levels[index]
        if (
            magnitude < threshold
            or magnitude < levels[index - 1][1]
            or magnitude < levels[index + 1][1]
        ):
            continue
        peak = MotionPeak(time=round(time, 3), magnitude=round(magnitude, 6))
        if time - last_time < min_gap_seconds:
            if peaks and magnitude > peaks[-1].magnitude:
                peaks[-1] = peak
                last_time = time
            continue
        peaks.append(peak)
        last_time = time
    return peaks


_SCENE_TIME_RE = re.compile(r"pts_time:(?P<time>\d+(?:\.\d+)?)")


def detect_scene_cuts(
    source: Path, *, threshold: float = DEFAULT_SCENE_THRESHOLD
) -> list[float]:
    """Return timestamps selected by ffmpeg's scene-change detector."""

    result = _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            str(source),
            "-vf",
            f"select='gt(scene,{threshold})',showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ],
        check=False,
    )
    output = result.stderr.decode(errors="replace")
    return sorted(
        {
            round(float(match.group("time")), 3)
            for match in _SCENE_TIME_RE.finditer(output)
        }
    )


def build_candidate_windows(
    duration: float,
    audio_peaks: Iterable[AudioPeak],
    scene_cuts: Iterable[float],
    motion_peaks: Iterable[MotionPeak] = (),
    *,
    profile: str = "fixed",
    max_windows: int = DEFAULT_MAX_WINDOWS,
) -> list[CandidateWindow]:
    """Combine cue timestamps into capped, sorted candidate windows."""

    p = PROFILES[profile]
    pre_roll = p["pre_roll"]
    post_roll = p["post_roll"]
    merge_gap = p["merge_gap"]
    max_window_seconds = p["max_window_seconds"]
    density_weight = p["density_weight"]
    scoring = p["scoring"]

    if duration <= 0:
        return []
    cues: list[tuple[float, bool, bool, bool, float]] = [
        (peak.time, True, False, False, peak.rms)
        for peak in audio_peaks
        if 0 <= peak.time <= duration
    ]
    cues.extend(
        (time, False, True, False, 1.0)
        for time in scene_cuts
        if 0 <= time <= duration
    )
    cues.extend(
        (peak.time, False, False, True, peak.magnitude)
        for peak in motion_peaks
        if 0 <= peak.time <= duration
    )
    cues.sort(key=lambda cue: cue[0])
    if not cues:
        return [
            CandidateWindow(
                id="w-001",
                t_start=0.0,
                t_end=round(min(duration, pre_roll + post_roll), 3),
                audio_peak=False,
                scene_cut=False,
                motion_peak=False,
                score=0.0,
            )
        ]

    clusters: list[list[tuple[float, bool, bool, bool, float]]] = []
    for cue in cues:
        if not clusters or cue[0] - clusters[-1][-1][0] > merge_gap:
            clusters.append([cue])
        else:
            clusters[-1].append(cue)
    # Rank by how EXCEPTIONAL a window is on each cue, measured against that
    # video's own distribution.
    #
    # The previous score — cue_count + min(0.99999, sum_of_strengths) — worked on
    # a quiet fixed camera and failed silently on broadcast, where every window
    # trips all three cues and the strength term always hits the clamp. All 40
    # windows scored an identical 3.99999, so the cap fell back to timestamp
    # order and the detector simply STOPPED LOOKING two-thirds of the way through
    # the match, missing the only goal.
    #
    # Percentile ranking is scale-free, so it adapts: on a fixed camera the
    # motion cue is the exceptional one; on broadcast the goal is the crowd roar
    # (which ranked #18 of 325 peaks — plainly findable, if you rank at all).
    def _percentiles(values: list[float]) -> dict[float, float]:
        if not values:
            return {}
        order = sorted(values)
        n = len(order) - 1 or 1
        return {v: order.index(v) / n for v in set(order)}

    per_cue: dict[int, dict[float, float]] = {}
    for idx in (1, 2, 3):
        per_cue[idx] = _percentiles(
            [cue[4] for cue in cues if cue[idx]]
        )

    windows: list[CandidateWindow] = []
    for cluster in clusters:
        burst_start = max(0.0, min(cue[0] for cue in cluster) - pre_roll)
        burst_end = min(duration, max(cue[0] for cue in cluster) + post_roll)

        # A goal's cue burst runs ~90s: build-up, strike, roar, celebration,
        # replays. Merging it is right — it IS one event — but a single window
        # cannot represent it. Anchor on the loudest moment and you frame the
        # CELEBRATION; anchor on the first cue and you frame the BUILD-UP 30s
        # early. The goal itself sits in the middle, and both anchors walk past
        # it — which is exactly how the only goal of a Champions League final was
        # missed twice.
        #
        # So tile a long burst with overlapping windows. A burst this sustained is
        # by definition the most interesting thing in the match; it earns the
        # extra coverage, and every tile inherits the burst's score.
        spans: list[tuple[float, float]] = []
        if burst_end - burst_start <= max_window_seconds:
            spans.append((burst_start, burst_end))
        else:
            stride = max_window_seconds * 0.75          # 25% overlap: no blind seams
            t = burst_start
            while t < burst_end:
                spans.append((t, min(duration, t + max_window_seconds)))
                t += stride

        flags = tuple(any(cue[i] for cue in cluster) for i in (1, 2, 3))

        # How exceptional is this window on each cue it actually has?
        strengths = []
        for i in (1, 2, 3):
            vals = [per_cue[i].get(cue[4], 0.0) for cue in cluster if cue[i]]
            strengths.append(max(vals) if vals else 0.0)

        # Best single cue carries the window; corroboration from other cues adds
        # a bonus, but cannot on its own float an unremarkable window to the top.
        exceptional = sum(1 for s in strengths if s >= 0.90)

        # DENSITY matters as much as peak height. A goal is not one spike — it is
        # a sustained burst: the roar, the celebration, the replays, a minute of
        # continuous noise. A near-miss is a single shout. Scoring only the
        # loudest instant treats them the same, and on a Champions League final —
        # where the crowd is loud all night — that is how the only goal ended up
        # ranked just below the cut.
        if scoring == "cue_sum":
            # A quiet fixed camera: cues are rare, so their PRESENCE is
            # informative and their summed magnitude never saturates.
            score = sum(flags) + min(0.99999, sum(cue[4] for cue in cluster))
        else:
            # A broadcast: every window trips every cue, so presence says nothing.
            # Rank by how EXCEPTIONAL the window is against this video's own
            # distribution, and reward a sustained burst over a lone spike.
            density = min(1.0, len(cluster) / CUES_FOR_FULL_DENSITY)
            score = max(strengths) + 0.15 * exceptional + density_weight * density

        for start, end in spans:
            windows.append(
                CandidateWindow(
                    id="",
                    t_start=round(start, 3),
                    t_end=round(max(start, end), 3),
                    audio_peak=flags[0],
                    scene_cut=flags[1],
                    motion_peak=flags[2],
                    score=round(score, 5),
                )
            )
    # Keep the strongest windows. The cap is a RATE, not a constant: 40 windows
    # is one per 68s across 45 minutes but one per 2.8 min across 111 — coarse
    # enough to walk straight past a goal.
    cap = min(max_windows, max(20, round(duration / 60 * WINDOWS_PER_MINUTE)))
    windows.sort(key=lambda window: (-window.score, window.t_start))
    windows = windows[:cap]
    windows.sort(key=lambda window: window.t_start)
    return [
        CandidateWindow(
            id=f"w-{index:03d}",
            **{key: value for key, value in asdict(window).items() if key != "id"},
        )
        for index, window in enumerate(windows, 1)
    ]


def detector_config(*, scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
                    profile: str = "fixed") -> dict:
    """Every knob that can change detector output.

    Hashed into each proposal run's provenance, so an omitted knob would let two
    genuinely different runs share a hash. `tests/test_detector_provenance.py`
    fails if a tunable is added without landing here.
    """

    return {
        "detector_version": DETECTOR_VERSION,
        "profile": profile,
        **{f"profile_{k}": v for k, v in PROFILES[profile].items()},
        "audio_sample_rate": DEFAULT_AUDIO_SAMPLE_RATE,
        "audio_window_seconds": DEFAULT_AUDIO_WINDOW_SECONDS,
        "audio_min_gap_seconds": DEFAULT_AUDIO_MIN_GAP_SECONDS,
        "audio_min_rms": DEFAULT_AUDIO_MIN_RMS,
        "audio_median_multiplier": DEFAULT_AUDIO_MEDIAN_MULTIPLIER,
        "scene_threshold": scene_threshold,
        "motion_frame_rate": DEFAULT_MOTION_FRAME_RATE,
        "motion_width": DEFAULT_MOTION_WIDTH,
        "motion_height": DEFAULT_MOTION_HEIGHT,
        "motion_interval_seconds": DEFAULT_MOTION_INTERVAL_SECONDS,
        "motion_min_gap_seconds": DEFAULT_MOTION_MIN_GAP_SECONDS,
        "motion_median_multiplier": DEFAULT_MOTION_MEDIAN_MULTIPLIER,
        "motion_min_magnitude": DEFAULT_MOTION_MIN_MAGNITUDE,
        "max_windows": DEFAULT_MAX_WINDOWS,
    }


def detect_windows(
    source: Path, *, scene_threshold: float = DEFAULT_SCENE_THRESHOLD
) -> dict:
    """Run all cue detectors and return the serializable windows artifact."""

    duration = probe_duration(source)
    audio_peaks = detect_audio_peaks(source)
    scene_cuts = detect_scene_cuts(source, threshold=scene_threshold)
    motion_peaks = detect_motion_peaks(source)
    profile = detect_profile(scene_cuts, duration)
    windows = build_candidate_windows(
        duration, audio_peaks, scene_cuts, motion_peaks, profile=profile
    )
    return {
        "video_id": source.stem,
        "source": str(source),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "duration": round(duration, 3),
        "profile": profile,
        "detector_config": detector_config(scene_threshold=scene_threshold, profile=profile),
        "audio_peaks": [asdict(peak) for peak in audio_peaks],
        "scene_cuts": scene_cuts,
        "motion_peaks": [asdict(peak) for peak in motion_peaks],
        "windows": [asdict(window) for window in windows],
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Source MP4 path")
    parser.add_argument("--video-id", default=None)
    parser.add_argument(
        "--output", type=Path, required=True, help="Windows JSON output path"
    )
    parser.add_argument(
        "--scene-threshold", type=float, default=DEFAULT_SCENE_THRESHOLD
    )
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"input does not exist: {args.input}")
    artifact = detect_windows(args.input, scene_threshold=args.scene_threshold)
    artifact["video_id"] = args.video_id or artifact["video_id"]
    _write_json(args.output, artifact)
    print(
        f"wrote {len(artifact['windows'])} candidate windows to {args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
