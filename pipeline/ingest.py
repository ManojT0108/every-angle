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
DETECTOR_VERSION = "d2-motion"

DEFAULT_SCENE_THRESHOLD = 0.35
DEFAULT_AUDIO_SAMPLE_RATE = 16_000
DEFAULT_AUDIO_WINDOW_SECONDS = 0.5
DEFAULT_AUDIO_MIN_GAP_SECONDS = 4.0
DEFAULT_AUDIO_MIN_RMS = 0.03
DEFAULT_AUDIO_MEDIAN_MULTIPLIER = 1.5
DEFAULT_PRE_ROLL = 5.0
DEFAULT_POST_ROLL = 10.0
DEFAULT_MERGE_GAP = 3.0
DEFAULT_MOTION_FRAME_RATE = 3.0
DEFAULT_MOTION_WIDTH = 160
DEFAULT_MOTION_HEIGHT = 90
DEFAULT_MOTION_INTERVAL_SECONDS = 1.0
DEFAULT_MOTION_MIN_GAP_SECONDS = 3.0
DEFAULT_MOTION_MEDIAN_MULTIPLIER = 1.5
DEFAULT_MOTION_MIN_MAGNITUDE = 0.002
DEFAULT_MAX_WINDOWS = 40


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
    pre_roll: float = DEFAULT_PRE_ROLL,
    post_roll: float = DEFAULT_POST_ROLL,
    merge_gap: float = DEFAULT_MERGE_GAP,
    max_windows: int = DEFAULT_MAX_WINDOWS,
) -> list[CandidateWindow]:
    """Combine cue timestamps into capped, sorted candidate windows."""

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
    windows: list[CandidateWindow] = []
    for cluster in clusters:
        start = max(0.0, min(cue[0] for cue in cluster) - pre_roll)
        end = min(duration, max(cue[0] for cue in cluster) + post_roll)
        cue_type_count = sum(
            (
                any(cue[1] for cue in cluster),
                any(cue[2] for cue in cluster),
                any(cue[3] for cue in cluster),
            )
        )
        aggregate_strength = sum(cue[4] for cue in cluster)
        windows.append(
            CandidateWindow(
                id="",
                t_start=round(start, 3),
                t_end=round(max(start, end), 3),
                audio_peak=any(cue[1] for cue in cluster),
                scene_cut=any(cue[2] for cue in cluster),
                motion_peak=any(cue[3] for cue in cluster),
                score=round(cue_type_count + min(0.99999, aggregate_strength), 5),
            )
        )
    # Retain the strongest cues when a long video produces more than the cap.
    windows.sort(key=lambda window: (-window.score, window.t_start))
    windows = windows[:max_windows]
    windows.sort(key=lambda window: window.t_start)
    return [
        CandidateWindow(
            id=f"w-{index:03d}",
            **{key: value for key, value in asdict(window).items() if key != "id"},
        )
        for index, window in enumerate(windows, 1)
    ]


def detector_config(*, scene_threshold: float = DEFAULT_SCENE_THRESHOLD) -> dict:
    """Every knob that can change detector output.

    Hashed into each proposal run's provenance, so an omitted knob would let two
    genuinely different runs share a hash. `tests/test_detector_provenance.py`
    fails if a tunable is added without landing here.
    """

    return {
        "detector_version": DETECTOR_VERSION,
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
        "pre_roll": DEFAULT_PRE_ROLL,
        "post_roll": DEFAULT_POST_ROLL,
        "merge_gap": DEFAULT_MERGE_GAP,
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
    windows = build_candidate_windows(
        duration, audio_peaks, scene_cuts, motion_peaks
    )
    return {
        "video_id": source.stem,
        "source": str(source),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "duration": round(duration, 3),
        "detector_config": detector_config(scene_threshold=scene_threshold),
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
