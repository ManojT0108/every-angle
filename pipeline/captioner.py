"""Captioner interfaces used by the proposal stage.

The mock keeps M0 runnable without credentials. ClaudeCaptioner intentionally
only establishes the configuration seam; the real vision request is an M1
implementation once the API key and prompt have been approved.
"""

from __future__ import annotations

import base64
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


EVENT_TYPES = ("goal", "save", "penalty", "card", "counterattack", "celebration")
# A proposal may also come back as "none": the model looked and found nothing
# notable. That is a GOOD outcome — most candidate windows are ordinary play,
# and forcing every window into an exciting label is how you get a lying demo.
PROPOSAL_TYPES = (*EVENT_TYPES, "none")
CONFIDENCE_LEVELS = ("high", "medium", "low")


@dataclass(frozen=True)
class CaptionResult:
    caption: str
    type: str = "counterattack"
    confidence: str = "low"


class Captioner(ABC):
    """Small drop-in interface for frame captioning providers."""

    name = "unknown"
    model = "unknown"
    prompt_version = "p1"

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "name": self.name,
            "model": self.model,
            "prompt_version": self.prompt_version,
        }

    @abstractmethod
    def caption(self, frames: Sequence[Path], window: dict[str, Any]) -> CaptionResult:
        """Caption sampled frames for one candidate window."""


class MockCaptioner(Captioner):
    """Deterministic canned captioner for offline M0 runs."""

    name = "mock"
    model = "mock-captioner"
    prompt_version = "p1"

    def caption(self, frames: Sequence[Path], window: dict[str, Any]) -> CaptionResult:
        cues: list[str] = []
        if window.get("audio_peak"):
            cues.append("audio cue")
        if window.get("scene_cut"):
            cues.append("scene change")
        cue_text = f" ({' + '.join(cues)})" if cues else ""
        return CaptionResult(
            caption=f"Potential football moment{cue_text}; review the play in this window.",
            type="counterattack",
            confidence="low",
        )


SYSTEM_PROMPT = """You are labelling candidate moments from a football (soccer) match for a \
highlights tool. The frames are consecutive samples from ONE short window of a fixed wide-angle \
camera; players are small.

Your job is to say what — if anything — notable happens in this window.

Rules:
- Describe ONLY what you can see. Never invent player names, team names, scores, or minutes: the \
  camera is too far away to read them, and downstream commentary is generated from your caption.
- Most windows are NOT notable. Ordinary passing, players jogging, a throw-in, a restart, or a \
  stoppage should be reported as type "none" with low confidence. Do not force an exciting label.
- You will be given TIGHT frames (zoomed on the ball, so you can see the play) and then WIDE \
  frames of the whole pitch (so you can see what happened next). Read them in order.
- The camera is far away, so you often CANNOT see the ball cross the line. Judge a goal by its \
  consequences, exactly as a human watching from the stand would: an attack on the box, then all \
  players walking back and lining up for a **restart from the centre circle**, is strong evidence \
  a goal was scored — a shot that misses or is saved is followed by a goal kick, a corner, or \
  play simply continuing. If you see the attack and then a centre-circle restart, label it "goal".
- Label "goal" whenever the frames show evidence of a specific recent goal: the strike, a replay \
  of it, a changed scoreline graphic, the immediate goal celebration, or players returning for a \
  centre-circle restart. Reserve "celebration" exclusively for match-ending or ceremonial scenes: \
  full-time celebrations, a lap of honour, players mobbing at the final whistle, a trophy lift, or \
  a medal ceremony — celebration not attributable to a specific in-window goal. When in doubt \
  between "goal" and "celebration", choose "goal".
- Write the caption the way someone would SEARCH for the moment later, e.g. "low shot from the \
  edge of the box beats the keeper at the near post" — not "players are moving"."""

SYSTEM_PROMPT_BROADCAST = """You are labelling candidate moments from a football (soccer) match \
for a highlights tool. The frames are consecutive samples from one short window of a directed \
television broadcast, which may include close-ups, wide shots, replays, and camera cuts.

Your job is to say what — if anything — notable happens in this window.

Rules:
- Describe ONLY what you can see. Never invent player names, team names, scores, or minutes, even \
  if an on-screen graphic is only partly legible; downstream commentary is generated from your \
  caption.
- Most windows are NOT notable. Ordinary passing, players jogging, a throw-in, a restart, or a \
  stoppage should be reported as type "none" with low confidence. Do not force an exciting label.
- Read the frames in order. A directed broadcast can often show the ball, a shot, the net, player \
  celebrations, and on-screen graphics, but camera cuts and replays may change viewpoint or time.
- Base the label on visible evidence across the sequence. A replay or celebration can support an \
  event label, but do not infer an event from a camera cut or crowd shot alone.
- Label "goal" whenever the frames show evidence of a specific recent goal: the strike, a replay \
  of it, a changed scoreline graphic, the immediate goal celebration, or players returning for a \
  centre-circle restart. Reserve "celebration" exclusively for match-ending or ceremonial scenes: \
  full-time celebrations, a lap of honour, players mobbing at the final whistle, a trophy lift, or \
  a medal ceremony — celebration not attributable to a specific in-window goal. When in doubt \
  between "goal" and "celebration", choose "goal".
- Write the caption the way someone would SEARCH for the moment later, e.g. "low shot from the \
  edge of the box beats the keeper at the near post" — not "players are moving"."""

# Per-million-token prices, for spend tracking. Keep in sync with the model.
PRICES = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": [*EVENT_TYPES, "none"]},
        "confidence": {"type": "string", "enum": list(CONFIDENCE_LEVELS)},
        "caption": {"type": "string"},
    },
    "required": ["type", "confidence", "caption"],
    "additionalProperties": False,
}


class ClaudeCaptioner(Captioner):
    """Anthropic vision captioner: sampled frames -> event type + searchable caption.

    This is the step that turns "something moved at t=1412s" into "a low finish at
    the near post" — i.e. the thing that is actually searchable, verifiable, and
    worth putting in a reel. Tracks spend so a run cannot silently blow a budget.
    """

    name = "claude"
    prompt_version = "p3-celebration"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "claude-sonnet-5",
        budget_usd: float | None = None,
        max_tokens: int = 400,
        profile: str = "fixed",
    ) -> None:
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.budget_usd = budget_usd
        self.max_tokens = max_tokens
        self.profile = profile
        self.prompt_version = (
            "p3-broadcast-celebration"
            if profile == "broadcast"
            else "p3-celebration"
        )
        self.spent_usd = 0.0
        self.calls = 0
        self._client = None

    @property
    def system_prompt(self) -> str:
        if self.profile == "broadcast":
            return SYSTEM_PROMPT_BROADCAST
        return SYSTEM_PROMPT

    def _cost(self, usage: Any) -> float:
        rate_in, rate_out = PRICES.get(self.model, (5.0, 25.0))
        return (
            usage.input_tokens * rate_in / 1e6
            + usage.output_tokens * rate_out / 1e6
        )

    # Worst-case input tokens for one image at our sizes. Deliberately generous:
    # a budget cap that can be exceeded is not a cap.
    MAX_TOKENS_PER_IMAGE = 5000

    def _worst_case_cost(self, n_frames: int) -> float:
        rate_in, rate_out = PRICES.get(self.model, (5.0, 25.0))
        est_in = n_frames * self.MAX_TOKENS_PER_IMAGE + 2000     # + prompt overhead
        return est_in * rate_in / 1e6 + self.max_tokens * rate_out / 1e6

    def caption(self, frames: Sequence[Path], window: dict[str, Any]) -> CaptionResult:
        if not self.api_key:
            raise RuntimeError("ClaudeCaptioner requires ANTHROPIC_API_KEY")
        if not frames:
            return CaptionResult(caption="No frames sampled.", type="none", confidence="low")
        if self.budget_usd is not None:
            # RESERVE the worst case before sending. Checking only what we have
            # already spent lets a single call sail past the cap — which is
            # exactly the failure a "hard budget" is supposed to prevent.
            projected = self.spent_usd + self._worst_case_cost(len(frames))
            if projected > self.budget_usd:
                raise RuntimeError(
                    f"budget stop: spent ${self.spent_usd:.2f} of ${self.budget_usd:.2f} "
                    f"after {self.calls} windows; the next window could reach "
                    f"${projected:.2f}. Raise --budget-usd to continue."
                )

        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key)

        content: list[dict[str, Any]] = []
        for path in frames:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64.standard_b64encode(path.read_bytes()).decode(),
                    },
                }
            )
        cues = [
            name
            for name, flag in (
                ("crowd/audio spike", window.get("audio_peak")),
                ("scene cut", window.get("scene_cut")),
                ("burst of motion", window.get("motion_peak")),
            )
            if flag
        ]
        content.append(
            {
                "type": "text",
                "text": (
                    f"{len(frames)} frames sampled in order across a "
                    f"{float(window['t_end']) - float(window['t_start']):.0f}s window.\n"
                    f"Why this window was flagged: {', '.join(cues) or 'unspecified'}.\n"
                    "What happens here?"
                ),
            }
        )

        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.system_prompt,
            output_config={"format": {"type": "json_schema", "schema": RESULT_SCHEMA}},
            messages=[{"role": "user", "content": content}],
        )
        self.calls += 1
        self.spent_usd += self._cost(response.usage)

        if response.stop_reason == "refusal":
            return CaptionResult(caption="Model declined to describe this window.",
                                 type="none", confidence="low")
        # A malformed or truncated response must not destroy a paid run: degrade
        # this ONE window to "none" and let the human see it in Verify.
        try:
            payload = json.loads(next(b.text for b in response.content if b.type == "text"))
            return CaptionResult(
                caption=payload["caption"],
                type=payload["type"],
                confidence=payload["confidence"],
            )
        except (StopIteration, json.JSONDecodeError, KeyError) as exc:
            return CaptionResult(
                caption=f"Unreadable model response ({type(exc).__name__}); needs human review.",
                type="none",
                confidence="low",
            )


def make_captioner(
    name: str,
    *,
    budget_usd: float | None = None,
    profile: str = "fixed",
) -> Captioner:
    """Build a captioner by the CLI-facing name."""

    if name == "mock":
        return MockCaptioner()
    if name == "claude":
        return ClaudeCaptioner(budget_usd=budget_usd, profile=profile)
    raise ValueError(f"unknown captioner {name!r}; choose mock or claude")
