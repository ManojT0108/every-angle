"""Coverage and taxonomy guards for end-of-match celebrations."""

from dataclasses import astuple
from pathlib import Path
from typing import get_args

from api.main import EVENT_TYPES as API_EVENT_TYPES
from pipeline.captioner import (
    EVENT_TYPES,
    PROPOSAL_TYPES,
    RESULT_SCHEMA,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_BROADCAST,
    ClaudeCaptioner,
)
from pipeline.ingest import (
    MAX_TAIL_WINDOWS,
    AudioPeak,
    CandidateWindow,
    build_candidate_windows,
    ensure_tail_coverage,
)


def _window(window_id: int, start: float, end: float) -> CandidateWindow:
    return CandidateWindow(
        id=f"w-{window_id:03d}",
        t_start=start,
        t_end=end,
        audio_peak=True,
        scene_cut=False,
        motion_peak=False,
        score=1.0,
    )


def test_match_002_tail_covers_trophy_ceremony_at_6480():
    windows = build_candidate_windows(
        6658.577,
        [AudioPeak(time=6315.0, rms=0.2)],
        [],
    )

    tails = [window for window in windows if window.tail]
    assert len(tails) == MAX_TAIL_WINDOWS
    assert any(window.t_start <= 6480 <= window.t_end for window in tails)


def test_short_video_tail_tiles_are_valid_and_unique():
    windows = build_candidate_windows(100.0, [], [])
    tails = [window for window in windows if window.tail]
    spans = [(window.t_start, window.t_end) for window in tails]

    assert tails
    assert len(spans) == len(set(spans))
    assert all(0 <= start < end <= 100.0 for start, end in spans)


def test_fragmented_tail_coverage_never_exceeds_fixed_tile_cap():
    kept = [
        _window(index, 821.0 + (index - 1) * 15.0, 826.0 + (index - 1) * 15.0)
        for index in range(1, 13)
    ]

    windows = ensure_tail_coverage(kept, 1000.0)
    tails = [window for window in windows if window.tail]

    assert len(tails) == MAX_TAIL_WINDOWS
    assert all(window.score == 0.0 for window in tails)
    assert all(
        not window.audio_peak and not window.scene_cut and not window.motion_peak
        for window in tails
    )


def test_cue_projection_and_ids_are_unchanged_when_tail_precedes_a_cue():
    windows = build_candidate_windows(
        6658.577,
        [AudioPeak(time=6500.0, rms=0.2)],
        [],
    )
    cue_windows = [window for window in windows if not window.tail]

    projection = [astuple(window)[:7] for window in cue_windows]
    assert projection == [
        ("w-001", 6495.0, 6510.0, True, False, False, 1.2),
    ]
    assert any(
        window.tail and window.t_start < cue_windows[0].t_start for window in windows
    )
    assert all(
        int(window.id.removeprefix("w-")) > len(cue_windows)
        for window in windows
        if window.tail
    )


def test_celebration_schema_prompt_and_versions():
    assert EVENT_TYPES[-1] == "celebration"
    assert "celebration" in PROPOSAL_TYPES
    assert "celebration" in RESULT_SCHEMA["properties"]["type"]["enum"]
    assert RESULT_SCHEMA["properties"]["team"]["type"] == ["string", "null"]
    assert RESULT_SCHEMA["properties"]["player"]["type"] == ["string", "null"]
    assert {"team", "player"}.issubset(RESULT_SCHEMA["required"])

    for prompt in (SYSTEM_PROMPT, SYSTEM_PROMPT_BROADCAST):
        assert (
            'Reserve "celebration" exclusively for match-ending or ceremonial scenes'
            in prompt
        )
        assert 'between "goal" and "celebration", choose "goal"' in prompt
        assert "directly attributes that identity to the goal" in prompt

    assert ClaudeCaptioner().prompt_version == "p4-goal-identity"
    assert (
        ClaudeCaptioner(profile="broadcast").prompt_version
        == "p4-broadcast-goal-identity"
    )


def test_api_and_web_taxonomies_include_celebration():
    assert "celebration" in get_args(API_EVENT_TYPES)

    web_contract = (
        Path(__file__).parents[1] / "web" / "src" / "lib" / "api.ts"
    ).read_text(encoding="utf-8")
    assert '| "celebration"' in web_contract
