"""Captioner interfaces used by the proposal stage.

The mock keeps M0 runnable without credentials. ClaudeCaptioner intentionally
only establishes the configuration seam; the real vision request is an M1
implementation once the API key and prompt have been approved.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


EVENT_TYPES = ("goal", "save", "penalty", "card", "counterattack")
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


class ClaudeCaptioner(Captioner):
    """Configuration skeleton for the planned Anthropic vision captioner."""

    name = "claude"
    prompt_version = "p1"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "claude-opus-4-8",
    ) -> None:
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model

    def caption(self, frames: Sequence[Path], window: dict[str, Any]) -> CaptionResult:
        if not self.api_key:
            raise RuntimeError("ClaudeCaptioner requires ANTHROPIC_API_KEY")
        raise NotImplementedError(
            "Claude vision request is reserved for M1; use --captioner mock for M0"
        )


def make_captioner(name: str) -> Captioner:
    """Build a captioner by the CLI-facing name."""

    if name == "mock":
        return MockCaptioner()
    if name == "claude":
        return ClaudeCaptioner()
    raise ValueError(f"unknown captioner {name!r}; choose mock or claude")
