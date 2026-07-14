"""HTTP contract tests for the Every Angle FastAPI backend."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api import main


class _StubEmbedding:
    def embed(self, _: list[str]) -> list[list[float]]:
        return [[0.0] * 384]


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Path]:
    data_root = tmp_path / "data"
    match = data_root / "match-test"
    published = match / "staging" / "rev-1"
    (published / "clips").mkdir(parents=True)
    (match / "frames" / "r-new-p-001").mkdir(parents=True)
    (match / "frames" / "r-new-p-001" / "frame-001.jpg").write_bytes(b"image")
    (published / "clips" / "e-published.mp4").write_bytes(b"dummy clip")

    (match / "windows.json").write_text(
        json.dumps(
            {
                "video_id": "match-test",
                "duration": 90.0,
                "windows": [
                    {
                        "id": "w-001",
                        "t_start": 10.0,
                        "t_end": 20.0,
                        "audio_peak": True,
                        "scene_cut": False,
                        "motion_peak": True,
                        "score": 2.5,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (match / "proposals.json").write_text(
        json.dumps(
            {
                "video_id": "match-test",
                "runs": [
                    {
                        "run_id": "r-old",
                        "created_at": "2026-07-14T01:00:00Z",
                        "captioner": {"name": "claude"},
                    },
                    {
                        "run_id": "r-mock",
                        "created_at": "2026-07-14T02:00:00Z",
                        "captioner": {"name": "mock"},
                    },
                    {
                        "run_id": "r-new",
                        "created_at": "2026-07-14T03:00:00Z",
                        "captioner": {"name": "claude"},
                    },
                ],
                "proposals": [
                    {
                        "id": "r-old-p-001",
                        "run_id": "r-old",
                        "t_start": 1.0,
                        "t_end": 2.0,
                        "type": "save",
                        "confidence": "low",
                        "caption": "old Claude run",
                        "evidence": {"frames": []},
                    },
                    {
                        "id": "r-mock-p-001",
                        "run_id": "r-mock",
                        "t_start": 2.0,
                        "t_end": 3.0,
                        "type": "goal",
                        "confidence": "high",
                        "caption": "mock run",
                        "evidence": {"frames": []},
                    },
                    {
                        "id": "r-new-p-001",
                        "run_id": "r-new",
                        "t_start": 12.0,
                        "t_end": 18.0,
                        "type": "goal",
                        "confidence": "high",
                        "caption": "latest Claude proposal",
                        "evidence": {
                            "frames": ["frames/r-new-p-001/frame-001.jpg"]
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (match / "decisions.json").write_text(
        json.dumps({"r-new-p-001": {"status": "rejected"}}), encoding="utf-8"
    )
    (match / "manifest.json").write_text(
        json.dumps(
            {
                "video_id": "match-test",
                "events": [
                    {
                        "id": "e-draft",
                        "from_proposal": None,
                        "t_start": 30.0,
                        "t_end": 35.0,
                        "type": "save",
                        "caption": "draft-only event",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (published / "manifest.json").write_text(
        json.dumps(
            {
                "video_id": "match-test",
                "collection": "moments_rev_1",
                "events": [
                    {
                        "id": "e-published",
                        "from_proposal": "r-new-p-001",
                        "t_start": 12.0,
                        "t_end": 18.0,
                        "type": "goal",
                        "caption": "published event",
                        "team": None,
                        "player": None,
                        "clip": "clips/e-published.mp4",
                        "verified_at": "2026-07-14T04:00:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (match / "CURRENT_REV").write_text("1\n", encoding="utf-8")

    monkeypatch.setattr(main, "_EMBEDDING_MODEL_INSTANCE", _StubEmbedding())
    monkeypatch.setattr(main, "_EMBEDDING_LOAD_ERROR", None)
    with TestClient(main.create_app(data_root)) as client:
        yield client, match


def test_lists_matches(api_client: tuple[TestClient, Path]) -> None:
    client, _ = api_client

    response = client.get("/api/matches")

    assert response.status_code == 200
    assert response.json() == [
        {
            "video_id": "match-test",
            "duration": 90.0,
            "current_revision": 1,
            "collection": "moments_rev_1",
            "event_count": 1,
        }
    ]


def test_timeline_uses_published_events_and_joins_rejections(
    api_client: tuple[TestClient, Path],
) -> None:
    client, _ = api_client

    payload = client.get("/api/matches/match-test/timeline").json()

    assert [event["id"] for event in payload["events"]] == ["e-published"]
    assert all(event["id"] != "e-draft" for event in payload["events"])
    assert payload["rejected"] == [
        {
            "proposal_id": "r-new-p-001",
            "t_start": 12.0,
            "t_end": 18.0,
            "caption": "latest Claude proposal",
        }
    ]


def test_proposals_only_include_the_most_recent_claude_run(
    api_client: tuple[TestClient, Path],
) -> None:
    client, _ = api_client

    response = client.get("/api/matches/match-test/proposals")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "r-new-p-001",
            "t_start": 12.0,
            "t_end": 18.0,
            "type": "goal",
            "confidence": "high",
            "caption": "latest Claude proposal",
            "status": "rejected",
            "frames": [
                "/media/match-test/frames/r-new-p-001/frame-001.jpg"
            ],
        }
    ]


def test_decisions_are_atomic_and_round_trip(
    api_client: tuple[TestClient, Path],
) -> None:
    client, match = api_client

    response = client.post(
        "/api/matches/match-test/decisions",
        json={"proposal_id": "r-new-p-001", "status": "accepted"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "proposal_id": "r-new-p-001",
        "status": "accepted",
        "event_id": None,
    }
    decisions = json.loads((match / "decisions.json").read_text(encoding="utf-8"))
    assert decisions["r-new-p-001"] == {"status": "accepted"}
    assert not list(match.glob(".decisions.json.*.tmp"))
    proposals = client.get("/api/matches/match-test/proposals").json()
    assert proposals[0]["status"] == "accepted"


def test_adding_human_event_updates_only_the_draft(
    api_client: tuple[TestClient, Path],
) -> None:
    client, match = api_client

    response = client.post(
        "/api/matches/match-test/events",
        json={
            "t_start": 40.0,
            "t_end": 45.0,
            "type": "counterattack",
            "caption": "human-added attack",
        },
    )

    assert response.status_code == 200
    assert response.json()["from_proposal"] is None
    draft = json.loads((match / "manifest.json").read_text(encoding="utf-8"))
    assert draft["events"][-1]["from_proposal"] is None
    assert draft["events"][-1]["caption"] == "human-added attack"
    timeline = client.get("/api/matches/match-test/timeline").json()
    assert [event["id"] for event in timeline["events"]] == ["e-published"]


def test_search_returns_503_when_qdrant_is_down(
    api_client: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = api_client

    def unavailable() -> Any:
        raise ConnectionError("offline")

    monkeypatch.setattr(main, "_make_qdrant_client", unavailable)
    response = client.get("/api/matches/match-test/search", params={"q": "goal"})

    assert response.status_code == 503
    assert "Qdrant" in response.json()["detail"]


def test_media_rejects_path_traversal(
    api_client: tuple[TestClient, Path], tmp_path: Path
) -> None:
    client, _ = api_client
    (tmp_path / "secret.txt").write_text("not public", encoding="utf-8")

    response = client.get("/media/%2e%2e%2fsecret.txt")

    assert response.status_code == 404
    assert response.text != "not public"
