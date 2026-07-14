"""Revision-selection and draft-isolation tests for app.contracts (plan D12)."""

import json

from app.contracts import load_data_contracts


def _video(tmp_path, *, draft_events, published_events=None, revision=None):
    vid = tmp_path / "match-x"
    vid.mkdir()
    (vid / "manifest.json").write_text(json.dumps({"events": draft_events}))
    if revision is not None:
        rev_dir = vid / "staging" / f"rev-{revision}"
        rev_dir.mkdir(parents=True)
        (rev_dir / "manifest.json").write_text(
            json.dumps({"events": published_events or []})
        )
        (vid / "CURRENT_REV").write_text(f"{revision}\n")
    return vid


def test_search_and_reel_see_only_the_promoted_revision(tmp_path):
    draft = [{"id": "e-draft", "caption": "UNPUBLISHED edit"}]
    published = [{"id": "e-001", "caption": "published goal", "clip": "clips/e-001.mp4"}]
    vid = _video(tmp_path, draft_events=draft, published_events=published, revision=3)

    contracts = load_data_contracts(tmp_path, "match-x")

    assert contracts["current_revision"] == 3
    assert contracts["collection"] == "moments_rev_3"
    assert contracts["published_dir"] == str(vid / "staging" / "rev-3")
    # What Search/Reel consume: the promoted revision only.
    assert contracts["published_manifest"]["events"] == published
    # The draft stays available — but only under the Verify-facing key.
    assert contracts["manifest"]["events"] == draft


def test_no_promoted_revision_means_nothing_published(tmp_path):
    _video(tmp_path, draft_events=[{"id": "e-draft"}])  # no CURRENT_REV

    contracts = load_data_contracts(tmp_path, "match-x")

    assert contracts["current_revision"] is None
    assert contracts["published_dir"] is None
    assert contracts["published_manifest"] == {"events": []}
    assert contracts["manifest"]["events"] == [{"id": "e-draft"}]


def test_garbage_revision_pointer_is_ignored(tmp_path):
    vid = _video(tmp_path, draft_events=[])
    (vid / "CURRENT_REV").write_text("not-a-number\n")

    contracts = load_data_contracts(tmp_path, "match-x")

    assert contracts["current_revision"] is None
    assert contracts["published_manifest"] == {"events": []}
