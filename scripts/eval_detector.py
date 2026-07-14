"""Score candidate windows against dataset ground truth (EVALUATION ONLY).

The BAS annotations are NEVER pipeline input — they exist solely to answer
"did our AI-proposed moments actually find the real events?". This script is
the testing gate for the detector; the pipeline must never import it.

Usage:
  python scripts/eval_detector.py data/match-001/windows.json \
      data/match-001/bas/117093_12_class_events.json --half 1 --labels GOAL SHOT
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_events(path: Path, half: str, labels: set[str]) -> list[tuple[str, float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    events: list[tuple[str, float]] = []
    for action in payload.get("actions", []):
        game_time = str(action.get("gameTime", ""))
        if not game_time.startswith(f"{half} -"):
            continue
        label = str(action.get("label", ""))
        if labels and label not in labels:
            continue
        # `position` is milliseconds from the start of the half — more precise
        # than the mm:ss game clock.
        events.append((label, float(action["position"]) / 1000.0))
    return sorted(events, key=lambda e: e[1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("windows", type=Path)
    parser.add_argument("events", type=Path)
    parser.add_argument("--half", default="1")
    parser.add_argument("--labels", nargs="*", default=["GOAL"])
    args = parser.parse_args()

    windows = json.loads(args.windows.read_text(encoding="utf-8"))["windows"]
    events = load_events(args.events, args.half, set(args.labels))

    print(f"windows: {len(windows)}   ground-truth events: {len(events)}\n")
    hits = 0
    for label, t in events:
        covering = [
            w for w in windows if w["t_start"] <= t <= w["t_end"]
        ]
        if covering:
            hits += 1
            w = covering[0]
            cues = ",".join(
                k for k in ("audio_peak", "scene_cut", "motion_peak") if w.get(k)
            )
            print(
                f"  HIT   {label:6s} @{t:8.1f}s  -> {w['id']} "
                f"[{w['t_start']:.1f}-{w['t_end']:.1f}] cues={cues}"
            )
        else:
            nearest = min(
                windows,
                key=lambda w: min(abs(w["t_start"] - t), abs(w["t_end"] - t)),
                default=None,
            )
            gap = (
                min(abs(nearest["t_start"] - t), abs(nearest["t_end"] - t))
                if nearest
                else float("inf")
            )
            print(f"  MISS  {label:6s} @{t:8.1f}s  (nearest window {gap:.1f}s away)")

    recall = hits / len(events) if events else 0.0
    covered = sum(w["t_end"] - w["t_start"] for w in windows)
    print(
        f"\nrecall: {hits}/{len(events)} = {recall:.0%}   "
        f"footage under review: {covered / 60:.1f} min"
    )


if __name__ == "__main__":
    main()
