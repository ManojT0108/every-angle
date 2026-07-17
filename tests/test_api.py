"""HTTP contract tests for the Every Angle FastAPI backend."""

from __future__ import annotations

import json
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient, models

from api import main
from pipeline.clip import proposal_clip_id
from pipeline.index_qdrant import event_text


class _StubEmbedding:
    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * 384
            if text == "ranking query" or "orphan" in text:
                vector[0] = 1.0
            elif "second valid" in text:
                vector[0] = 0.8
                vector[1] = 0.6
            else:
                vector[0] = 0.9
                vector[1] = 0.435889894
            vectors.append(vector)
        return vectors


class _RecordingEmbedding(_StubEmbedding):
    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts.extend(texts)
        return super().embed(texts)


class _NoCloseQdrant:
    def __init__(self, client: QdrantClient) -> None:
        self._client = client

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def close(self) -> None:
        pass


def _published_event() -> dict[str, Any]:
    return {
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


def _promoted_manifest(match: Path) -> dict[str, Any]:
    return json.loads(
        (match / "staging" / "rev-1" / "manifest.json").read_text(encoding="utf-8")
    )


def _enable_source_video(match: Path) -> Path:
    source = match / "source.mp4"
    source.write_bytes(b"source")
    windows_path = match / "windows.json"
    windows = json.loads(windows_path.read_text(encoding="utf-8"))
    windows["source"] = str(source)
    windows_path.write_text(json.dumps(windows), encoding="utf-8")
    return source


def _stub_cut_event(_: Path, event: dict[str, Any], clips_dir: Path) -> Path:
    destination = clips_dir / f"{event['id']}.mp4"
    destination.write_bytes(b"cut clip")
    return destination


@pytest.fixture
def in_memory_qdrant(monkeypatch: pytest.MonkeyPatch) -> Iterator[QdrantClient]:
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="moments_rev_1",
        vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE),
    )
    event = _published_event()
    vector = _StubEmbedding().embed([event_text(event)])[0]
    client.upsert(
        collection_name="moments_rev_1",
        points=[
            models.PointStruct(
                id=main._point_id("match-test", str(event["id"])),
                vector=vector,
                payload=event,
            )
        ],
        wait=True,
    )
    wrapper = _NoCloseQdrant(client)
    monkeypatch.setattr(main, "_make_qdrant_client", lambda: wrapper)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def api_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    in_memory_qdrant: QdrantClient,
) -> Iterator[tuple[TestClient, Path]]:
    data_root = tmp_path / "data"
    match = data_root / "match-test"
    published = match / "staging" / "rev-1"
    published.mkdir(parents=True)
    (match / "clips").mkdir(parents=True)
    (match / "frames" / "r-new-p-001").mkdir(parents=True)
    (match / "frames" / "r-new-p-001" / "frame-001.jpg").write_bytes(b"image")
    (match / "clips" / "e-published.mp4").write_bytes(b"dummy clip")
    pending_event_id = main._proposal_event_id("r-new-p-002")
    (match / "clips" / f"{pending_event_id}.mp4").write_bytes(b"pending clip")
    (match / "clips" / f"{proposal_clip_id('r-new-p-002')}.mp4").write_bytes(
        b"proposal clip"
    )

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
                        "evidence": {"frames": ["frames/r-new-p-001/frame-001.jpg"]},
                    },
                    {
                        "id": "r-new-p-002",
                        "run_id": "r-new",
                        "t_start": 40.0,
                        "t_end": 46.0,
                        "type": "save",
                        "confidence": "medium",
                        "caption": "latest pending proposal",
                        "evidence": {"frames": []},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (match / "decisions.json").write_text(
        json.dumps(
            {
                "r-new-p-001": {
                    "status": "rejected",
                    "event_id": "e-published",
                }
            }
        ),
        encoding="utf-8",
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
                "events": [_published_event()],
            }
        ),
        encoding="utf-8",
    )
    (match / "CURRENT_REV").write_text("1\n", encoding="utf-8")

    monkeypatch.setattr(main, "_EMBEDDING_MODEL_INSTANCE", _StubEmbedding())
    monkeypatch.setattr(main, "_EMBEDDING_LOAD_ERROR", None)
    assert in_memory_qdrant.collection_exists("moments_rev_1")
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


def test_timeline_uses_manifest_as_truth_over_stale_rejection(
    api_client: tuple[TestClient, Path],
) -> None:
    client, _ = api_client

    payload = client.get("/api/matches/match-test/timeline").json()

    assert [event["id"] for event in payload["events"]] == ["e-published"]
    assert all(event["id"] != "e-draft" for event in payload["events"])
    assert payload["rejected"] == []


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
            "caption": "published event",
            "status": "accepted",
            "clip": "/media/match-test/clips/e-published.mp4",
            "frames": ["/media/match-test/frames/r-new-p-001/frame-001.jpg"],
        },
        {
            "id": "r-new-p-002",
            "t_start": 40.0,
            "t_end": 46.0,
            "type": "save",
            "confidence": "medium",
            "caption": "latest pending proposal",
            "status": "pending",
            "clip": (
                f"/media/match-test/clips/{proposal_clip_id('r-new-p-002')}.mp4"
            ),
            "frames": [],
        },
    ]


def test_rejected_after_acceptance_keeps_event_clip(
    api_client: tuple[TestClient, Path],
) -> None:
    client, _ = api_client

    response = client.post("/api/matches/match-test/proposals/r-new-p-001/reject")
    proposal = client.get("/api/matches/match-test/proposals").json()[0]

    assert response.status_code == 200
    assert proposal["status"] == "rejected"
    assert proposal["clip"] == "/media/match-test/clips/e-published.mp4"


def test_proposal_clip_is_none_when_neither_candidate_exists(
    api_client: tuple[TestClient, Path],
) -> None:
    client, match = api_client
    event_id = main._proposal_event_id("r-new-p-002")
    (match / "clips" / f"{event_id}.mp4").unlink()
    (match / "clips" / f"{proposal_clip_id('r-new-p-002')}.mp4").unlink()

    proposals = client.get("/api/matches/match-test/proposals").json()
    proposal = next(row for row in proposals if row["id"] == "r-new-p-002")

    assert proposal["clip"] is None


def test_source_free_match_serves_resolved_proposal_clip(
    api_client: tuple[TestClient, Path],
) -> None:
    client, _ = api_client

    assert client.get("/api/matches/match-test/capabilities").json() == {
        "source_video_available": False
    }
    proposals = client.get("/api/matches/match-test/proposals").json()
    proposal = next(row for row in proposals if row["id"] == "r-new-p-002")

    response = client.get(proposal["clip"])

    assert response.status_code == 200
    assert response.content == b"proposal clip"


def test_accept_writes_through_to_manifest_index_and_media(
    api_client: tuple[TestClient, Path],
    in_memory_qdrant: QdrantClient,
) -> None:
    client, match = api_client
    proposal_id = "r-new-p-002"
    event_id = main._proposal_event_id(proposal_id)

    response = client.post(f"/api/matches/match-test/proposals/{proposal_id}/accept")

    assert response.status_code == 200
    assert response.json() == {
        "proposal_id": proposal_id,
        "status": "accepted",
        "event_id": event_id,
    }
    manifest = _promoted_manifest(match)
    accepted = next(event for event in manifest["events"] if event["id"] == event_id)
    assert accepted["from_proposal"] == proposal_id
    assert accepted["caption"] == "latest pending proposal"
    draft = json.loads((match / "manifest.json").read_text(encoding="utf-8"))
    assert [event["id"] for event in draft["events"]] == ["e-draft"]

    points = in_memory_qdrant.retrieve(
        collection_name="moments_rev_1",
        ids=[main._point_id("match-test", event_id)],
        with_payload=True,
    )
    assert len(points) == 1
    assert points[0].payload["id"] == event_id
    search = client.get(
        "/api/matches/match-test/search", params={"q": "latest pending proposal"}
    )
    assert search.status_code == 200
    assert event_id in {event["id"] for event in search.json()}
    timeline = client.get("/api/matches/match-test/timeline").json()
    assert event_id in {event["id"] for event in timeline["events"]}
    assert client.get(f"/media/match-test/clips/{event_id}.mp4").status_code == 200

    decisions = json.loads((match / "decisions.json").read_text(encoding="utf-8"))
    assert decisions[proposal_id] == {"status": "accepted", "event_id": event_id}
    assert not list(match.glob(".decisions.json.*.tmp"))
    assert not list((match / "staging" / "rev-1").glob(".manifest.json.*.tmp"))


def test_edit_updates_caption_then_type_with_canonical_embedding_and_overlay(
    api_client: tuple[TestClient, Path],
    in_memory_qdrant: QdrantClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, match = api_client
    embedding = _RecordingEmbedding()
    monkeypatch.setattr(main, "_EMBEDDING_MODEL_INSTANCE", embedding)
    path = "/api/matches/match-test/proposals/r-new-p-001/edit"

    caption_edit = client.post(path, json={"caption": "corrected winning strike"})
    type_edit = client.post(path, json={"type": "save"})

    assert caption_edit.status_code == 200
    assert type_edit.status_code == 200
    assert embedding.texts[:2] == [
        "corrected winning strike. goal",
        "corrected winning strike. save",
    ]
    event = _promoted_manifest(match)["events"][0]
    assert event["caption"] == "corrected winning strike"
    assert event["type"] == "save"
    point = in_memory_qdrant.retrieve(
        collection_name="moments_rev_1",
        ids=[main._point_id("match-test", "e-published")],
        with_payload=True,
    )[0]
    assert point.payload["caption"] == "corrected winning strike"
    assert point.payload["type"] == "save"

    search = client.get(
        "/api/matches/match-test/search", params={"q": "corrected winning strike"}
    )
    proposal = client.get("/api/matches/match-test/proposals").json()[0]

    assert search.status_code == 200
    assert search.json()[0]["caption"] == "corrected winning strike"
    assert search.json()[0]["type"] == "save"
    assert proposal["caption"] == "corrected winning strike"
    assert proposal["type"] == "save"
    assert proposal["clip"] == "/media/match-test/clips/e-published.mp4"


def test_editing_pending_proposal_materializes_and_accepts_it(
    api_client: tuple[TestClient, Path],
    in_memory_qdrant: QdrantClient,
) -> None:
    client, match = api_client
    proposal_id = "r-new-p-002"
    event_id = main._proposal_event_id(proposal_id)

    response = client.post(
        f"/api/matches/match-test/proposals/{proposal_id}/edit",
        json={"caption": "edited pending counter", "type": "counterattack"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "proposal_id": proposal_id,
        "status": "accepted",
        "event_id": event_id,
    }
    event = next(
        row for row in _promoted_manifest(match)["events"] if row["id"] == event_id
    )
    assert event["caption"] == "edited pending counter"
    assert event["type"] == "counterattack"
    assert in_memory_qdrant.retrieve(
        collection_name="moments_rev_1",
        ids=[main._point_id("match-test", event_id)],
    )


def test_editing_type_to_none_reuses_reject_and_removes_from_search(
    api_client: tuple[TestClient, Path],
    in_memory_qdrant: QdrantClient,
) -> None:
    client, match = api_client

    response = client.post(
        "/api/matches/match-test/proposals/r-new-p-001/edit",
        json={"type": "none"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert _promoted_manifest(match)["events"] == []
    assert not in_memory_qdrant.retrieve(
        collection_name="moments_rev_1",
        ids=[main._point_id("match-test", "e-published")],
    )
    assert (
        client.get(
            "/api/matches/match-test/search", params={"q": "published event"}
        ).json()
        == []
    )


def test_edit_compensates_when_upsert_fails_after_mutating_point(
    api_client: tuple[TestClient, Path],
    in_memory_qdrant: QdrantClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, match = api_client
    real_upsert = main._upsert_event

    def fail_after_upsert(*args: Any, **kwargs: Any) -> None:
        real_upsert(*args, **kwargs)
        raise main.HTTPException(status_code=503, detail="injected upsert failure")

    monkeypatch.setattr(main, "_upsert_event", fail_after_upsert)

    response = client.post(
        "/api/matches/match-test/proposals/r-new-p-001/edit",
        json={"caption": "must not commit"},
    )

    assert response.status_code == 503
    assert _promoted_manifest(match)["events"][0]["caption"] == "published event"
    point = in_memory_qdrant.retrieve(
        collection_name="moments_rev_1",
        ids=[main._point_id("match-test", "e-published")],
        with_payload=True,
    )[0]
    assert point.payload["caption"] == "published event"
    search = client.get(
        "/api/matches/match-test/search", params={"q": "published event"}
    )
    assert search.status_code == 200
    assert search.json()[0]["caption"] == "published event"


def test_edit_compensates_when_manifest_commit_fails(
    api_client: tuple[TestClient, Path],
    in_memory_qdrant: QdrantClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, match = api_client
    real_write = main._write_json_atomic

    def fail_manifest(path: Path, payload: dict[str, Any]) -> None:
        if path.name == "manifest.json" and "staging" in path.parts:
            raise OSError("injected manifest failure")
        real_write(path, payload)

    monkeypatch.setattr(main, "_write_json_atomic", fail_manifest)

    response = client.post(
        "/api/matches/match-test/proposals/r-new-p-001/edit",
        json={"caption": "must not reach the manifest"},
    )

    assert response.status_code == 500
    assert _promoted_manifest(match)["events"][0]["caption"] == "published event"
    point = in_memory_qdrant.retrieve(
        collection_name="moments_rev_1",
        ids=[main._point_id("match-test", "e-published")],
        with_payload=True,
    )[0]
    assert point.payload["caption"] == "published event"
    search = client.get(
        "/api/matches/match-test/search", params={"q": "published event"}
    )
    assert search.status_code == 200
    assert search.json()[0]["caption"] == "published event"


def test_failed_compensation_forces_search_into_reconciliation(
    api_client: tuple[TestClient, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = api_client

    def fail_manifest(path: Path, _: dict[str, Any]) -> None:
        if path.name == "manifest.json" and "staging" in path.parts:
            raise OSError("injected manifest failure")
        raise AssertionError(f"unexpected write: {path}")

    def fail_restore(*_: Any, **__: Any) -> None:
        raise ConnectionError("injected compensation failure")

    def fail_reconcile(_: Path) -> None:
        raise ConnectionError("index remains unavailable")

    monkeypatch.setattr(main, "_write_json_atomic", fail_manifest)
    monkeypatch.setattr(main, "_restore_event_point", fail_restore)
    monkeypatch.setattr(main, "_reconcile_baseline", fail_reconcile)

    edit = client.post(
        "/api/matches/match-test/proposals/r-new-p-001/edit",
        json={"caption": "split value"},
    )
    search = client.get(
        "/api/matches/match-test/search", params={"q": "published event"}
    )

    assert edit.status_code == 503
    assert client.app.state.reconciliation_error
    assert search.status_code == 503


def test_adding_human_event_writes_through_to_current_revision(
    api_client: tuple[TestClient, Path],
    in_memory_qdrant: QdrantClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, match = api_client
    _enable_source_video(match)
    monkeypatch.setattr(main, "cut_event", _stub_cut_event)

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
    event = response.json()
    assert event["from_proposal"] is None
    assert (match / str(event["clip"])).is_file()
    draft = json.loads((match / "manifest.json").read_text(encoding="utf-8"))
    assert [row["id"] for row in draft["events"]] == ["e-draft"]
    manifest = _promoted_manifest(match)
    assert manifest["events"][-1]["id"] == event["id"]
    assert manifest["events"][-1]["caption"] == "human-added attack"
    assert in_memory_qdrant.retrieve(
        collection_name="moments_rev_1",
        ids=[main._point_id("match-test", event["id"])],
    )
    search = client.get(
        "/api/matches/match-test/search", params={"q": "human-added attack"}
    ).json()
    assert event["id"] in {row["id"] for row in search}
    timeline = client.get("/api/matches/match-test/timeline").json()
    assert event["id"] in {row["id"] for row in timeline["events"]}


def test_adding_human_event_does_not_reuse_reserved_decision_id(
    api_client: tuple[TestClient, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, match = api_client
    _enable_source_video(match)
    monkeypatch.setattr(main, "cut_event", _stub_cut_event)
    decisions_path = match / "decisions.json"
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    decisions["r-undone-p-001"] = {
        "status": "rejected",
        "event_id": "e-007",
    }
    decisions_path.write_text(json.dumps(decisions), encoding="utf-8")

    response = client.post(
        "/api/matches/match-test/events",
        json={
            "t_start": 50.0,
            "t_end": 55.0,
            "type": "save",
            "caption": "human save after an undone proposal",
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == "e-008"
    assert response.json()["id"] != "e-007"


def test_adding_human_celebration_is_supported(
    api_client: tuple[TestClient, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, match = api_client
    _enable_source_video(match)
    monkeypatch.setattr(main, "cut_event", _stub_cut_event)

    response = client.post(
        "/api/matches/match-test/events",
        json={
            "t_start": 80.0,
            "t_end": 90.0,
            "type": "celebration",
            "caption": "team lifts the trophy after full time",
        },
    )

    assert response.status_code == 200
    assert response.json()["type"] == "celebration"
    assert _promoted_manifest(match)["events"][-1]["type"] == "celebration"


def test_reject_removes_manifest_event_and_index_point(
    api_client: tuple[TestClient, Path],
    in_memory_qdrant: QdrantClient,
) -> None:
    client, match = api_client

    response = client.post("/api/matches/match-test/proposals/r-new-p-001/reject")

    assert response.status_code == 200
    assert response.json() == {
        "proposal_id": "r-new-p-001",
        "status": "rejected",
        "event_id": "e-published",
    }
    assert _promoted_manifest(match)["events"] == []
    assert not in_memory_qdrant.retrieve(
        collection_name="moments_rev_1",
        ids=[main._point_id("match-test", "e-published")],
    )
    assert (
        client.get(
            "/api/matches/match-test/search", params={"q": "published event"}
        ).json()
        == []
    )
    proposals = client.get("/api/matches/match-test/proposals").json()
    assert proposals[0]["status"] == "rejected"
    timeline = client.get("/api/matches/match-test/timeline").json()
    assert [row["proposal_id"] for row in timeline["rejected"]] == ["r-new-p-001"]


def test_reaccept_is_idempotent(
    api_client: tuple[TestClient, Path],
    in_memory_qdrant: QdrantClient,
) -> None:
    client, match = api_client
    path = "/api/matches/match-test/proposals/r-new-p-001/accept"

    first = client.post(path)
    second = client.post(path)

    assert first.status_code == 200
    assert second.status_code == 200
    events = _promoted_manifest(match)["events"]
    assert [event["id"] for event in events].count("e-published") == 1
    assert (
        in_memory_qdrant.count(collection_name="moments_rev_1", exact=True).count == 1
    )


def test_search_filter_fills_limit_despite_higher_ranked_orphan(
    api_client: tuple[TestClient, Path],
    in_memory_qdrant: QdrantClient,
) -> None:
    client, match = api_client
    second = {
        **_published_event(),
        "id": "e-second",
        "from_proposal": None,
        "caption": "second valid event",
        "clip": "clips/e-second.mp4",
    }
    orphan = {
        **_published_event(),
        "id": "e-orphan",
        "from_proposal": None,
        "caption": "orphan event",
        "clip": "clips/e-orphan.mp4",
    }
    manifest = _promoted_manifest(match)
    manifest["events"].append(second)
    (match / "staging" / "rev-1" / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    embedder = _StubEmbedding()
    in_memory_qdrant.upsert(
        collection_name="moments_rev_1",
        points=[
            models.PointStruct(
                id=main._point_id("match-test", "e-second"),
                vector=embedder.embed(["second valid event"])[0],
                payload=second,
            ),
            models.PointStruct(
                id=main._point_id("match-test", "e-orphan"),
                vector=embedder.embed(["orphan event"])[0],
                payload=orphan,
            ),
        ],
        wait=True,
    )
    query = embedder.embed(["ranking query"])[0]
    unfiltered = in_memory_qdrant.query_points(
        collection_name="moments_rev_1",
        query=query,
        limit=1,
        with_payload=True,
    )
    assert unfiltered.points[0].payload["id"] == "e-orphan"

    response = client.get(
        "/api/matches/match-test/search",
        params={"q": "ranking query", "limit": 2},
    )

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert {event["id"] for event in response.json()} == {
        "e-published",
        "e-second",
    }


def test_search_waits_for_an_in_progress_edit_on_the_match_lock(
    api_client: tuple[TestClient, Path],
    in_memory_qdrant: QdrantClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = api_client
    upserted = threading.Event()
    release_edit = threading.Event()
    query_reached = threading.Event()
    real_upsert = main._upsert_event

    class QuerySignalQdrant(_NoCloseQdrant):
        def query_points(self, *args: Any, **kwargs: Any) -> Any:
            query_reached.set()
            return self._client.query_points(*args, **kwargs)

    monkeypatch.setattr(
        main, "_make_qdrant_client", lambda: QuerySignalQdrant(in_memory_qdrant)
    )

    def pausing_upsert(*args: Any, **kwargs: Any) -> None:
        real_upsert(*args, **kwargs)
        upserted.set()
        assert release_edit.wait(timeout=2)

    monkeypatch.setattr(main, "_upsert_event", pausing_upsert)
    responses: dict[str, Any] = {}
    edit_thread = threading.Thread(
        target=lambda: responses.setdefault(
            "edit",
            client.post(
                "/api/matches/match-test/proposals/r-new-p-001/edit",
                json={"caption": "committed under lock"},
            ),
        )
    )
    edit_thread.start()
    assert upserted.wait(timeout=2)

    search_thread = threading.Thread(
        target=lambda: responses.setdefault(
            "search",
            client.get(
                "/api/matches/match-test/search",
                params={"q": "committed under lock"},
            ),
        )
    )
    search_thread.start()

    assert not query_reached.wait(timeout=0.1)
    release_edit.set()
    edit_thread.join(timeout=2)
    search_thread.join(timeout=2)

    assert not edit_thread.is_alive()
    assert not search_thread.is_alive()
    assert query_reached.is_set()
    assert responses["edit"].status_code == 200
    assert responses["search"].status_code == 200
    assert responses["search"].json()[0]["caption"] == "committed under lock"


def test_reconcile_baseline_restores_missing_and_deletes_extra(
    api_client: tuple[TestClient, Path],
    in_memory_qdrant: QdrantClient,
) -> None:
    _, match = api_client
    baseline_point_id = main._point_id("match-test", "e-published")
    extra_point_id = main._point_id("match-test", "e-extra")
    in_memory_qdrant.delete(
        collection_name="moments_rev_1",
        points_selector=models.PointIdsList(points=[baseline_point_id]),
        wait=True,
    )
    extra = {**_published_event(), "id": "e-extra", "caption": "extra event"}
    in_memory_qdrant.upsert(
        collection_name="moments_rev_1",
        points=[
            models.PointStruct(
                id=extra_point_id,
                vector=_StubEmbedding().embed(["extra event"])[0],
                payload=extra,
            )
        ],
        wait=True,
    )

    main._reconcile_baseline(match.parent)

    assert in_memory_qdrant.retrieve(
        collection_name="moments_rev_1", ids=[baseline_point_id]
    )
    assert not in_memory_qdrant.retrieve(
        collection_name="moments_rev_1", ids=[extra_point_id]
    )
    assert (
        in_memory_qdrant.count(collection_name="moments_rev_1", exact=True).count == 1
    )


def test_reconcile_skips_missing_collection_and_continues_published_match(
    api_client: tuple[TestClient, Path],
    in_memory_qdrant: QdrantClient,
) -> None:
    _, match = api_client
    baseline_point_id = main._point_id("match-test", "e-published")
    in_memory_qdrant.delete(
        collection_name="moments_rev_1",
        points_selector=models.PointIdsList(points=[baseline_point_id]),
        wait=True,
    )
    missing = match.parent / "a-missing-collection"
    missing_published = missing / "staging" / "rev-2"
    missing_published.mkdir(parents=True)
    (missing / "CURRENT_REV").write_text("2\n", encoding="utf-8")
    (missing_published / "manifest.json").write_text(
        json.dumps(
            {
                "video_id": "a-missing-collection",
                "collection": "moments_rev_2",
                "events": [],
            }
        ),
        encoding="utf-8",
    )

    main._reconcile_baseline(match.parent)

    assert not in_memory_qdrant.collection_exists("moments_rev_2")
    assert in_memory_qdrant.retrieve(
        collection_name="moments_rev_1", ids=[baseline_point_id]
    )


def test_search_lazily_retries_failed_startup_reconciliation(
    api_client: tuple[TestClient, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = api_client
    client.app.state.reconciliation_error = "startup unavailable"
    attempts = 0

    def flaky_reconcile(_: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("still unavailable")

    monkeypatch.setattr(main, "_reconcile_baseline", flaky_reconcile)

    first = client.get(
        "/api/matches/match-test/search", params={"q": "published event"}
    )

    assert first.status_code == 503
    assert client.app.state.reconciliation_error

    second = client.get(
        "/api/matches/match-test/search", params={"q": "published event"}
    )

    assert second.status_code == 200
    assert client.app.state.reconciliation_error is None
    assert attempts == 2


def test_capabilities_report_source_video_availability(
    api_client: tuple[TestClient, Path],
) -> None:
    client, match = api_client

    unavailable = client.get("/api/matches/match-test/capabilities")
    _enable_source_video(match)
    available = client.get("/api/matches/match-test/capabilities")

    assert unavailable.json() == {"source_video_available": False}
    assert available.json() == {"source_video_available": True}


def test_accept_without_published_collection_returns_clear_error(
    api_client: tuple[TestClient, Path],
    in_memory_qdrant: QdrantClient,
) -> None:
    client, match = api_client
    in_memory_qdrant.delete_collection("moments_rev_1")

    response = client.post("/api/matches/match-test/proposals/r-new-p-002/accept")

    assert response.status_code == 409
    assert "publish" in response.json()["detail"].lower()
    assert [event["id"] for event in _promoted_manifest(match)["events"]] == [
        "e-published"
    ]


def test_accept_cuts_missing_clip_when_source_is_available(
    api_client: tuple[TestClient, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, match = api_client
    proposal_id = "r-new-p-002"
    event_id = main._proposal_event_id(proposal_id)
    clip = match / "clips" / f"{event_id}.mp4"
    clip.unlink()
    (match / "clips" / f"{proposal_clip_id(proposal_id)}.mp4").unlink()
    _enable_source_video(match)
    monkeypatch.setattr(main, "cut_event", _stub_cut_event)

    response = client.post(f"/api/matches/match-test/proposals/{proposal_id}/accept")

    assert response.status_code == 200
    assert response.json()["event_id"] == event_id
    assert clip.is_file()
    search = client.get(
        "/api/matches/match-test/search", params={"q": "latest pending proposal"}
    )
    assert search.status_code == 200
    assert event_id in {event["id"] for event in search.json()}


def test_accept_promotes_proposal_clip_without_source(
    api_client: tuple[TestClient, Path],
) -> None:
    client, match = api_client
    proposal_id = "r-new-p-002"
    event_id = main._proposal_event_id(proposal_id)
    event_clip = match / "clips" / f"{event_id}.mp4"
    proposal_clip = match / "clips" / f"{proposal_clip_id(proposal_id)}.mp4"
    event_clip.unlink()
    assert main._source_video(match) is None

    response = client.post(f"/api/matches/match-test/proposals/{proposal_id}/accept")

    assert response.status_code == 200
    assert response.json()["event_id"] == event_id
    assert event_clip.read_bytes() == proposal_clip.read_bytes()
    assert event_id in {event["id"] for event in _promoted_manifest(match)["events"]}
    search = client.get(
        "/api/matches/match-test/search", params={"q": "latest pending proposal"}
    )
    assert search.status_code == 200
    assert event_id in {event["id"] for event in search.json()}


def test_accept_missing_clip_without_source_returns_409(
    api_client: tuple[TestClient, Path],
) -> None:
    client, match = api_client
    proposal_id = "r-new-p-002"
    event_id = main._proposal_event_id(proposal_id)
    (match / "clips" / f"{event_id}.mp4").unlink()
    (match / "clips" / f"{proposal_clip_id(proposal_id)}.mp4").unlink()

    response = client.post(f"/api/matches/match-test/proposals/{proposal_id}/accept")

    assert response.status_code == 409
    assert "no source video" in response.json()["detail"].lower()
    assert event_id not in {
        event["id"] for event in _promoted_manifest(match)["events"]
    }


def test_legacy_decisions_route_is_retired(
    api_client: tuple[TestClient, Path],
) -> None:
    client, _ = api_client

    response = client.post(
        "/api/matches/match-test/decisions",
        json={"proposal_id": "r-new-p-001", "status": "rejected"},
    )

    assert response.status_code == 405


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


def test_build_reel_stream_copies_normalized_clips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clips: list[Path] = []
    for index, color in enumerate(("red", "blue"), start=1):
        clip = tmp_path / f"clip-{index}.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=1280x720:r=25:d=0.5",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000:d=0.5",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-shortest",
                "-y",
                str(clip),
            ],
            capture_output=True,
            check=True,
        )
        clips.append(clip)

    real_run = main.subprocess.run
    commands: list[list[str]] = []

    def record_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        commands.append(command)
        return real_run(command, **kwargs)

    monkeypatch.setattr(main.subprocess, "run", record_run)
    destination = tmp_path / "reels" / "highlights.mp4"

    main._build_reel(destination, clips)

    assert len(commands) == 1
    assert ["-c", "copy"] == commands[0][
        commands[0].index("-c") : commands[0].index("-c") + 2
    ]
    probe = real_run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,width,height",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(destination),
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    media = json.loads(probe.stdout)
    assert {stream["codec_name"] for stream in media["streams"]} == {"h264", "aac"}
    video = next(stream for stream in media["streams"] if stream["codec_name"] == "h264")
    assert (video["width"], video["height"]) == (1280, 720)
    assert float(media["format"]["duration"]) > 0.9
