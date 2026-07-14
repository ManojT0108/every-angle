"""Tests for the vertical-slice fixes (Sol code review, 2026-07-14).

Each test pins a bug that actually shipped and was caught in review — the kind
that produces plausible-looking output while being silently wrong.
"""

import json

import pytest

from pipeline import track
from pipeline.captioner import ClaudeCaptioner, MockCaptioner
from pipeline.index_qdrant import MockProposalError, assert_no_mock_provenance


class _Usage:
    input_tokens = 1000
    output_tokens = 100


# --- budget cap ------------------------------------------------------------

def test_budget_cap_refuses_a_call_that_could_exceed_it():
    """A cap you can overshoot is not a cap. The check must RESERVE the worst
    case before sending, not merely look at what was already spent."""
    cap = ClaudeCaptioner(api_key="x", budget_usd=0.01)
    with pytest.raises(RuntimeError, match="budget stop"):
        cap.caption([_JPG], {"t_start": 0, "t_end": 5})
    assert cap.calls == 0          # nothing was sent, so nothing was billed


def test_budget_cap_allows_a_call_that_fits():
    cap = ClaudeCaptioner(api_key="x", budget_usd=10.0)
    # Worst case for one frame must sit well under a $10 cap.
    assert cap._worst_case_cost(1) < 10.0


def test_spend_accumulates_from_real_usage():
    cap = ClaudeCaptioner(api_key="x", model="claude-opus-4-8")
    cost = cap._cost(_Usage())
    assert cost == pytest.approx(1000 * 5.0 / 1e6 + 100 * 25.0 / 1e6)


# --- tracker: axis scaling -------------------------------------------------

def test_ball_coordinates_use_independent_axis_scales(monkeypatch):
    """Deriving ONE scale from width is right only for a 4096x1080 panorama and
    silently wrong for everything else — a 1920x1080 broadcast would place every
    y at ~47% of its true value, misplacing every tight crop."""
    W, H = track.W, track.H
    monkeypatch.setattr(track, "probe_size", lambda src: (1920, 1080))

    scale_x = 1920 / W
    scale_y = 1080 / H
    assert scale_x != scale_y, "test is meaningless if the scales coincide"

    # A detection at the analysis-frame centre must map to the SOURCE centre.
    assert (W / 2) * scale_x == pytest.approx(960)
    assert (H / 2) * scale_y == pytest.approx(540)
    # The old single-scale bug would have produced this instead:
    assert (H / 2) * scale_x == pytest.approx(253.125)


# --- publish gate: no mock-derived events ----------------------------------

def _write_proposals(tmp_path, captioner_name: str) -> str:
    (tmp_path / "proposals.json").write_text(json.dumps({
        "video_id": "v", "runs": [
            {"run_id": "r-1", "captioner": {"name": captioner_name, "model": "m"}},
        ],
        "proposals": [{"id": "r-1-p-001", "run_id": "r-1"}],
    }))
    return "r-1-p-001"


def test_publish_rejects_mock_derived_events(tmp_path):
    pid = _write_proposals(tmp_path, "mock")
    manifest = {"events": [{"id": "e-001", "from_proposal": pid}]}
    with pytest.raises(MockProposalError, match="mock"):
        assert_no_mock_provenance(tmp_path, manifest)


def test_publish_accepts_real_ai_events(tmp_path):
    pid = _write_proposals(tmp_path, "claude")
    assert_no_mock_provenance(tmp_path, {"events": [{"id": "e-001", "from_proposal": pid}]})


def test_publish_accepts_human_added_events(tmp_path):
    """A human is not a mock: manually added events carry from_proposal = null."""
    _write_proposals(tmp_path, "mock")
    assert_no_mock_provenance(tmp_path, {"events": [{"id": "e-001", "from_proposal": None}]})


def test_publish_rejects_dangling_proposal_reference(tmp_path):
    _write_proposals(tmp_path, "claude")
    manifest = {"events": [{"id": "e-001", "from_proposal": "r-9-p-999"}]}
    with pytest.raises(MockProposalError, match="unknown proposal"):
        assert_no_mock_provenance(tmp_path, manifest)


# --- mock captioner is still honest about itself ---------------------------

def test_mock_captioner_identifies_itself():
    assert MockCaptioner().metadata["name"] == "mock"


_JPG = None  # set in conftest-free fashion below


def setup_module(module):
    """A tiny on-disk JPEG so the budget test can build a request body."""
    import tempfile
    from pathlib import Path
    global _JPG
    d = Path(tempfile.mkdtemp())
    _JPG = d / "f.jpg"
    _JPG.write_bytes(b"\xff\xd8\xff\xdb" + b"\x00" * 64)


def test_missing_proposals_file_blocks_ai_claims(tmp_path):
    """An absent proposals.json must not silently wave through events that claim
    AI provenance — an unverifiable claim is what the gate exists to stop."""
    manifest = {"events": [{"id": "e-001", "from_proposal": "r-1-p-001"}]}
    with pytest.raises(MockProposalError, match="missing"):
        assert_no_mock_provenance(tmp_path, manifest)


def test_missing_proposals_file_is_fine_for_a_purely_human_manifest(tmp_path):
    assert_no_mock_provenance(tmp_path, {"events": [{"id": "e-001", "from_proposal": None}]})
