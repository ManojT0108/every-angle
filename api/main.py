"""FastAPI backend for the Every Angle web application."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, model_validator
from qdrant_client import QdrantClient, models
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from pipeline.clip import cut_event, latest_claude_run_id, resolve_proposal_clip
from pipeline.index_qdrant import (
    DEFAULT_QDRANT_URL,
    EMBEDDING_MODEL,
    _point_id,
    collection_name,
    event_text,
)


DATA_ROOT = Path(os.getenv("DATA_ROOT", "data")).resolve()
FRONTEND_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
LOGGER = logging.getLogger(__name__)
EVENT_TYPES = Literal["goal", "save", "penalty", "card", "counterattack", "celebration"]
PROPOSAL_TYPES = Literal[
    "goal", "save", "penalty", "card", "counterattack", "celebration", "none"
]
EVENT_TYPE_VALUES = {
    "goal",
    "save",
    "penalty",
    "card",
    "counterattack",
    "celebration",
}

_EMBEDDING_MODEL_INSTANCE: Any | None = None
_EMBEDDING_LOAD_ERROR: str | None = None
_EMBEDDING_LOCK = threading.Lock()
_EVENT_ID_PATTERN = re.compile(r"^e-(\d+)$")


class MatchSummary(BaseModel):
    """One match available beneath the configured data root."""

    video_id: str
    duration: float
    current_revision: int | None
    collection: str | None
    event_count: int


class TimelineWindow(BaseModel):
    """A detector window displayed on the match timeline."""

    id: str
    t_start: float
    t_end: float
    audio_peak: bool
    scene_cut: bool
    motion_peak: bool
    score: float


class EventResponse(BaseModel):
    """A verified or human-added manifest event."""

    model_config = ConfigDict(extra="allow")

    id: str
    from_proposal: str | None
    t_start: float
    t_end: float
    type: str
    caption: str
    team: str | None = Field(default=None, max_length=120)
    player: str | None = Field(default=None, max_length=120)
    clip: str | None = None
    verified_at: str | None = None


class RejectedProposal(BaseModel):
    """A rejected proposal joined back to its source proposal record."""

    proposal_id: str
    t_start: float
    t_end: float
    caption: str


class TimelineResponse(BaseModel):
    """All data needed to render the provenance timeline."""

    duration: float
    windows: list[TimelineWindow]
    events: list[EventResponse]
    rejected: list[RejectedProposal]


class ProposalResponse(BaseModel):
    """A proposal from the most recent Claude captioning run."""

    id: str
    t_start: float
    t_end: float
    type: str
    confidence: str
    caption: str
    team: str | None = Field(default=None, max_length=120)
    player: str | None = Field(default=None, max_length=120)
    status: Literal["pending", "accepted", "rejected"]
    clip: str | None
    frames: list[str]


class MatchCapabilities(BaseModel):
    """Request-time features available for one match."""

    source_video_available: bool


class DecisionResponse(BaseModel):
    """The persisted decision state for one proposal."""

    proposal_id: str
    status: Literal["accepted", "rejected"]
    event_id: str | None = None


class ProposalEditRequest(BaseModel):
    """Human corrections to a proposal before materialization."""

    caption: str | None = Field(default=None, min_length=1)
    type: PROPOSAL_TYPES | None = None
    team: str | None = Field(default=None, max_length=120)
    player: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_edit(self) -> ProposalEditRequest:
        identity_fields = {"team", "player"}.intersection(self.model_fields_set)
        if self.caption is None and self.type is None and not identity_fields:
            raise ValueError("caption, type, team, or player is required")
        if self.caption is not None and not self.caption.strip():
            raise ValueError("caption must not be blank")
        if self.team is not None:
            self.team = self.team.strip() or None
        if self.player is not None:
            self.player = self.player.strip() or None
        return self


class HumanEventRequest(BaseModel):
    """A manually identified moment to add to the draft manifest."""

    t_start: float = Field(ge=0)
    t_end: float = Field(gt=0)
    type: EVENT_TYPES
    caption: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_range(self) -> HumanEventRequest:
        if self.t_end <= self.t_start:
            raise ValueError("t_end must be greater than t_start")
        return self


class SearchResult(EventResponse):
    """A published event plus its Qdrant cosine score."""

    score: float


class ReelRequest(BaseModel):
    """The ordered published events to concatenate into a reel."""

    event_ids: list[str] = Field(min_length=1)


class ReelResponse(BaseModel):
    """The cached or newly encoded reel artifact."""

    url: str
    duration: float
    event_ids: list[str]


class GuardedStaticFiles(StaticFiles):
    """StaticFiles with an explicit resolved-path boundary check."""

    def __init__(self, *, directory: Path, html: bool = False) -> None:
        self._root = directory.resolve()
        super().__init__(directory=str(self._root), html=html, check_dir=False)

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            requested = (self._root / path).resolve()
            if not requested.is_relative_to(self._root):
                raise HTTPException(status_code=404, detail="Media file not found")
        except (OSError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="Media file not found") from exc
        return await super().get_response(path, scope)


def _read_json_object(path: Path, *, default: dict[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        return default
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500, detail=f"Invalid data artifact: {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=500, detail=f"Invalid data artifact: {path.name}"
        )
    return cast(dict[str, Any], payload)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _match_dir(data_root: Path, video_id: str) -> Path:
    try:
        match_dir = (data_root / video_id).resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Match not found") from exc
    if not match_dir.is_relative_to(data_root) or not match_dir.is_dir():
        raise HTTPException(status_code=404, detail="Match not found")
    return match_dir


def _current_revision(match_dir: Path) -> int | None:
    pointer = match_dir / "CURRENT_REV"
    if not pointer.is_file():
        return None
    try:
        revision = int(pointer.read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=500, detail="Invalid CURRENT_REV pointer"
        ) from exc
    if revision < 1:
        raise HTTPException(status_code=500, detail="Invalid CURRENT_REV pointer")
    return revision


def _published_manifest(
    match_dir: Path, *, required: bool = False
) -> tuple[int | None, Path | None, dict[str, Any]]:
    revision = _current_revision(match_dir)
    if revision is None:
        if required:
            raise HTTPException(status_code=404, detail="No published revision")
        return None, None, {"events": []}
    published_dir = match_dir / "staging" / f"rev-{revision}"
    manifest_path = published_dir / "manifest.json"
    if not manifest_path.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"Published revision {revision} is missing its manifest",
        )
    manifest = _read_json_object(manifest_path, default={"events": []})
    if not isinstance(manifest.get("events"), list):
        raise HTTPException(status_code=500, detail="Invalid published manifest")
    return revision, published_dir, manifest


def _artifact_events(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    events = manifest.get("events", [])
    if not isinstance(events, list) or not all(
        isinstance(event, dict) for event in events
    ):
        raise HTTPException(status_code=500, detail="Invalid manifest events")
    return cast(list[dict[str, Any]], events)


def _media_url(video_id: str, relative_path: str) -> str | None:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        return None
    full_path = PurePosixPath(video_id) / path
    return f"/media/{quote(full_path.as_posix(), safe='/')}"


def _proposal_responses(match_dir: Path, video_id: str) -> list[ProposalResponse]:
    artifact = _read_json_object(
        match_dir / "proposals.json", default={"runs": [], "proposals": []}
    )
    try:
        run_id = latest_claude_run_id(artifact)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if run_id is None:
        return []
    rows = artifact.get("proposals", [])
    if not isinstance(rows, list):
        raise HTTPException(status_code=500, detail="Invalid proposals artifact")
    decisions = _read_json_object(match_dir / "decisions.json", default={})
    _, _, manifest = _published_manifest(match_dir)
    accepted_by_proposal = {
        str(event["from_proposal"]): event
        for event in _artifact_events(manifest)
        if event.get("from_proposal") is not None
    }
    responses: list[ProposalResponse] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("run_id") != run_id:
            continue
        proposal_id = str(row.get("id", ""))
        decision = decisions.get(proposal_id, {})
        accepted_event = accepted_by_proposal.get(proposal_id)
        if accepted_event is not None and isinstance(accepted_event.get("clip"), str):
            clip = _media_url(video_id, str(accepted_event["clip"]))
        else:
            clip_path = resolve_proposal_clip(match_dir, proposal_id, decision)
            clip = (
                _media_url(video_id, clip_path.relative_to(match_dir).as_posix())
                if clip_path is not None
                else None
            )
        status = "accepted" if accepted_event is not None else "pending"
        if (
            status == "pending"
            and isinstance(decision, dict)
            and decision.get("status") == "rejected"
        ):
            status = "rejected"
        evidence = row.get("evidence")
        raw_frames = evidence.get("frames", []) if isinstance(evidence, dict) else []
        frames = [
            url
            for frame in raw_frames
            if isinstance(frame, str)
            and (url := _media_url(video_id, frame)) is not None
        ]
        try:
            responses.append(
                ProposalResponse(
                    id=proposal_id,
                    t_start=row["t_start"],
                    t_end=row["t_end"],
                    type=str(
                        accepted_event.get("type", "")
                        if accepted_event is not None
                        else row.get("type", "")
                    ),
                    confidence=str(row.get("confidence", "")),
                    caption=str(
                        accepted_event.get("caption", "")
                        if accepted_event is not None
                        else row.get("caption", "")
                    ),
                    team=(
                        accepted_event.get("team")
                        if accepted_event is not None
                        else row.get("team")
                    ),
                    player=(
                        accepted_event.get("player")
                        if accepted_event is not None
                        else row.get("player")
                    ),
                    status=status,
                    clip=clip,
                    frames=frames,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=500, detail=f"Invalid proposal: {proposal_id or 'unknown'}"
            ) from exc
    return responses


def _load_embedding_model() -> None:
    global _EMBEDDING_LOAD_ERROR, _EMBEDDING_MODEL_INSTANCE

    if _EMBEDDING_MODEL_INSTANCE is not None or _EMBEDDING_LOAD_ERROR is not None:
        return
    with _EMBEDDING_LOCK:
        if _EMBEDDING_MODEL_INSTANCE is not None or _EMBEDDING_LOAD_ERROR is not None:
            return
        try:
            from fastembed import TextEmbedding

            # In the deployed container the model cache is baked into the image, so
            # load strictly offline (FASTEMBED_LOCAL_ONLY=1). This removes the only
            # network dependency at startup: without it, a transient Hugging Face
            # metadata request during a cold start could fail, and because the error
            # is cached and never retried, Search would stay 503 until a restart.
            # Local dev leaves the env unset so a first run may still download.
            local_only = os.environ.get("FASTEMBED_LOCAL_ONLY") == "1"
            _EMBEDDING_MODEL_INSTANCE = TextEmbedding(
                model_name=EMBEDDING_MODEL, local_files_only=local_only
            )
        except Exception as exc:  # startup remains available for non-search endpoints
            _EMBEDDING_LOAD_ERROR = str(exc) or type(exc).__name__


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    _load_embedding_model()
    try:
        _reconcile_baseline(application.state.data_root)
    except Exception as exc:
        application.state.reconciliation_error = str(exc) or type(exc).__name__
        LOGGER.warning("Qdrant baseline reconciliation failed: %s", exc)
    else:
        application.state.reconciliation_error = None
    yield


def _query_vector(query: str) -> list[float]:
    if _EMBEDDING_MODEL_INSTANCE is None:
        detail = "Local search embedding model is unavailable"
        if _EMBEDDING_LOAD_ERROR:
            detail = f"{detail}: {_EMBEDDING_LOAD_ERROR}"
        raise HTTPException(status_code=503, detail=detail)
    try:
        vectors = list(_EMBEDDING_MODEL_INSTANCE.embed([query]))
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Local search embedding failed"
        ) from exc
    if not vectors:
        raise HTTPException(status_code=503, detail="Local search embedding failed")
    return [float(value) for value in vectors[0]]


def _make_qdrant_client() -> QdrantClient:
    return QdrantClient(
        url=os.getenv("QDRANT_URL", DEFAULT_QDRANT_URL),
        api_key=os.getenv("QDRANT_API_KEY") or None,
    )


def _request_qdrant_client() -> QdrantClient:
    try:
        return _make_qdrant_client()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Qdrant is unavailable; verify QDRANT_URL and retry",
        ) from exc


def _proposal_event_id(proposal_id: str) -> str:
    digest = hashlib.sha256(proposal_id.encode("utf-8")).hexdigest()[:16]
    return f"e-{digest}"


def _source_video(match_dir: Path) -> Path | None:
    windows = _read_json_object(match_dir / "windows.json", default={})
    value = windows.get("source")
    if not isinstance(value, str) or not value:
        return None
    raw = Path(value)
    candidates = [raw] if raw.is_absolute() else [Path.cwd() / raw, match_dir / raw]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    return None


def _event_clip(match_dir: Path, clip_value: Any) -> Path:
    if not isinstance(clip_value, str):
        raise HTTPException(status_code=500, detail="Published event has no clip")
    relative = PurePosixPath(clip_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise HTTPException(
            status_code=500, detail="Published event has an invalid clip"
        )
    clip = (match_dir / Path(*relative.parts)).resolve()
    if not clip.is_relative_to(match_dir.resolve()) or not clip.is_file():
        raise HTTPException(status_code=500, detail="Published event clip is missing")
    return clip


def _proposal_row(match_dir: Path, proposal_id: str) -> dict[str, Any]:
    proposals = _read_json_object(
        match_dir / "proposals.json", default={"proposals": []}
    )
    rows = proposals.get("proposals", [])
    if not isinstance(rows, list):
        raise HTTPException(status_code=500, detail="Invalid proposals artifact")
    for row in rows:
        if isinstance(row, dict) and row.get("id") == proposal_id:
            return row
    raise HTTPException(status_code=404, detail="Proposal not found")


def _event_for_proposal(
    proposal: dict[str, Any],
    manifest_events: list[dict[str, Any]],
    decisions: dict[str, Any],
    *,
    caption: str | None = None,
    event_type: str | None = None,
    team: str | None = None,
    player: str | None = None,
    team_supplied: bool = False,
    player_supplied: bool = False,
) -> dict[str, Any]:
    proposal_id = str(proposal.get("id", ""))
    if not proposal_id:
        raise HTTPException(status_code=500, detail="Invalid proposal id")
    for event in manifest_events:
        if event.get("from_proposal") == proposal_id:
            edited = dict(event)
            if caption is not None:
                edited["caption"] = caption
            if event_type is not None:
                edited["type"] = event_type
            if team_supplied:
                edited["team"] = team
            if player_supplied:
                edited["player"] = player
            if edited.get("type") != "goal":
                edited["team"] = None
                edited["player"] = None
            return EventResponse.model_validate(edited).model_dump()
    previous = decisions.get(proposal_id, {})
    event_id = (
        previous.get("event_id")
        if isinstance(previous, dict) and isinstance(previous.get("event_id"), str)
        else _proposal_event_id(proposal_id)
    )
    materialized_type = event_type or str(proposal.get("type", ""))
    if materialized_type not in EVENT_TYPE_VALUES:
        raise HTTPException(
            status_code=400, detail="Ordinary-play proposals cannot be accepted"
        )
    try:
        event = {
            "id": event_id,
            "from_proposal": proposal_id,
            "t_start": float(proposal["t_start"]),
            "t_end": float(proposal["t_end"]),
            "type": materialized_type,
            "caption": caption if caption is not None else str(proposal["caption"]),
            "team": (team if team_supplied else proposal.get("team"))
            if materialized_type == "goal"
            else None,
            "player": (player if player_supplied else proposal.get("player"))
            if materialized_type == "goal"
            else None,
            "clip": f"clips/{event_id}.mp4",
            "verified_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }
        return EventResponse.model_validate(event).model_dump()
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Invalid proposal") from exc


def _require_collection(client: QdrantClient, revision: int) -> str:
    name = collection_name(revision)
    try:
        exists = client.collection_exists(name)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Qdrant is unavailable; verify QDRANT_URL and retry",
        ) from exc
    if not exists:
        raise HTTPException(
            status_code=409,
            detail=f"Published collection {name} does not exist; publish the match first",
        )
    return name


def _upsert_event(
    client: QdrantClient,
    *,
    revision: int,
    video_id: str,
    event: dict[str, Any],
) -> None:
    name = _require_collection(client, revision)
    vector = _query_vector(event_text(event))
    try:
        client.upsert(
            collection_name=name,
            points=[
                models.PointStruct(
                    id=_point_id(video_id, str(event["id"])),
                    vector=vector,
                    payload=event,
                )
            ],
            wait=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Qdrant upsert failed") from exc


def _delete_event_point(
    client: QdrantClient, *, revision: int, video_id: str, event_id: str
) -> None:
    name = _require_collection(client, revision)
    try:
        client.delete(
            collection_name=name,
            points_selector=models.PointIdsList(points=[_point_id(video_id, event_id)]),
            wait=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Qdrant delete failed") from exc


def _capture_event_point(
    client: QdrantClient, *, revision: int, video_id: str, event_id: str
) -> tuple[Any, Any, dict[str, Any]] | None:
    name = _require_collection(client, revision)
    try:
        records = client.retrieve(
            collection_name=name,
            ids=[_point_id(video_id, event_id)],
            with_payload=True,
            with_vectors=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Qdrant read failed") from exc
    if not records:
        return None
    record = records[0]
    if record.vector is None:
        raise HTTPException(status_code=503, detail="Qdrant point has no vector")
    return record.id, record.vector, cast(dict[str, Any], record.payload or {})


def _restore_event_point(
    client: QdrantClient,
    *,
    revision: int,
    video_id: str,
    event_id: str,
    snapshot: tuple[Any, Any, dict[str, Any]] | None,
) -> None:
    name = collection_name(revision)
    if snapshot is None:
        client.delete(
            collection_name=name,
            points_selector=models.PointIdsList(points=[_point_id(video_id, event_id)]),
            wait=True,
        )
        return
    point_id, vector, payload = snapshot
    client.upsert(
        collection_name=name,
        points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
        wait=True,
    )


def _reconcile_baseline(data_root: Path) -> None:
    if not data_root.is_dir():
        return
    client: QdrantClient | None = None
    try:
        client = _make_qdrant_client()
        for match_dir in sorted(data_root.iterdir(), key=lambda path: path.name):
            if not match_dir.is_dir() or not (match_dir / "CURRENT_REV").is_file():
                continue
            revision, _, manifest = _published_manifest(match_dir, required=True)
            assert revision is not None
            name = collection_name(revision)
            # A match with no seeded collection is simply unpublished — skip it
            # here (its endpoints surface an actionable 409 via _require_collection)
            # rather than turning a non-transient state into a transient reconcile
            # failure. Genuine connectivity errors still propagate as transient.
            if not client.collection_exists(name):
                LOGGER.warning(
                    "Skipping reconcile for %s: collection %s missing",
                    match_dir.name,
                    name,
                )
                continue
            events = _artifact_events(manifest)
            if events:
                points = [
                    models.PointStruct(
                        id=_point_id(match_dir.name, str(event["id"])),
                        vector=_query_vector(event_text(event)),
                        payload=event,
                    )
                    for event in events
                ]
                client.upsert(collection_name=name, points=points, wait=True)

            expected = {_point_id(match_dir.name, str(event["id"])) for event in events}
            actual: set[str] = set()
            offset: Any | None = None
            while True:
                records, next_offset = client.scroll(
                    collection_name=name,
                    limit=256,
                    offset=offset,
                    with_payload=False,
                    with_vectors=False,
                )
                actual.update(str(record.id) for record in records)
                if next_offset is None:
                    break
                offset = next_offset
            extra = sorted(actual - expected)
            if extra:
                client.delete(
                    collection_name=name,
                    points_selector=models.PointIdsList(points=extra),
                    wait=True,
                )
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def _next_event_id(
    events: list[dict[str, Any]], reserved_ids: Iterable[str] = ()
) -> str:
    # Allocate against manifest event ids AND ids reserved in decisions, so an
    # id freed by an undo (removed from the manifest but still recorded in
    # decisions) is never reused and then duplicated when the proposal is
    # re-accepted.
    candidates = [str(event.get("id", "")) for event in events]
    candidates.extend(str(rid) for rid in reserved_ids)
    numbers = [
        int(match.group(1))
        for candidate in candidates
        if (match := _EVENT_ID_PATTERN.fullmatch(candidate))
    ]
    return f"e-{max(numbers, default=0) + 1:03d}"


def _ffconcat_path(path: Path) -> str:
    return str(path).replace("'", "'\\''")


def _build_reel(destination: Path, clips: list[Path]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    concat_path: Path | None = None
    encoded_path = (
        destination.parent / f".{destination.stem}.{uuid.uuid4().hex}.tmp.mp4"
    )
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.stem}.",
            suffix=".concat.txt",
            delete=False,
        ) as handle:
            concat_path = Path(handle.name)
            for clip in clips:
                handle.write(f"file '{_ffconcat_path(clip)}'\n")
        copy_result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_path),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                "-y",
                str(encoded_path),
            ],
            capture_output=True,
            check=False,
        )
        result = copy_result
        if copy_result.returncode != 0:
            encoded_path.unlink(missing_ok=True)
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_path),
                    "-vf",
                    "scale=1280:720:force_original_aspect_ratio=decrease,"
                    "pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "23",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    "-movflags",
                    "+faststart",
                    "-y",
                    str(encoded_path),
                ],
                capture_output=True,
                check=False,
            )
        if result.returncode != 0:
            copy_message = copy_result.stderr.decode(errors="replace").strip()
            fallback_message = result.stderr.decode(errors="replace").strip()
            raise HTTPException(
                status_code=500,
                detail=(
                    "Reel encoding failed: stream-copy concat failed "
                    f"({copy_message}); re-encode fallback failed ({fallback_message})"
                ),
            )
        os.replace(encoded_path, destination)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="ffmpeg is not installed") from exc
    finally:
        if concat_path is not None:
            concat_path.unlink(missing_ok=True)
        encoded_path.unlink(missing_ok=True)


def create_app(data_root: Path | None = None) -> FastAPI:
    """Create an API instance rooted at one artifact directory."""

    root = (data_root or DATA_ROOT).resolve()
    application = FastAPI(title="Every Angle API", lifespan=_lifespan)
    application.state.data_root = root
    match_locks: dict[str, threading.Lock] = {}
    match_locks_guard = threading.Lock()

    def match_lock(video_id: str) -> threading.Lock:
        with match_locks_guard:
            return match_locks.setdefault(video_id, threading.Lock())

    reconcile_guard = threading.Lock()

    def ensure_reconciled() -> None:
        # If startup reconciliation failed (a transient Qdrant outage), retry it
        # lazily before touching the index, and 503 until it succeeds — so Search
        # never silently serves a stale pre-reset collection (code-review fix).
        if not getattr(application.state, "reconciliation_error", None):
            return
        with reconcile_guard:
            # Re-check under the lock: another request may have reconciled while
            # we waited. Serializing here prevents two concurrent reconciles, one
            # of which could delete a point the other just accepted (code-review).
            if not getattr(application.state, "reconciliation_error", None):
                return
            try:
                _reconcile_baseline(root)
            except Exception as exc:
                application.state.reconciliation_error = str(exc) or type(exc).__name__
                raise HTTPException(
                    status_code=503,
                    detail="Index is reconciling after a startup issue; retry shortly",
                ) from exc
            application.state.reconciliation_error = None

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/api/matches", response_model=list[MatchSummary])
    def list_matches() -> list[MatchSummary]:
        if not root.is_dir():
            return []
        matches: list[MatchSummary] = []
        for match_dir in sorted(root.iterdir(), key=lambda path: path.name):
            if (
                not match_dir.is_dir()
                or match_dir.name.startswith(".")
                or not (
                    (match_dir / "manifest.json").is_file()
                    or (match_dir / "proposals.json").is_file()
                )
            ):
                continue
            windows = _read_json_object(match_dir / "windows.json", default={})
            revision, _, manifest = _published_manifest(match_dir)
            events = _artifact_events(manifest)
            matches.append(
                MatchSummary(
                    video_id=match_dir.name,
                    duration=float(windows.get("duration", 0.0)),
                    current_revision=revision,
                    collection=collection_name(revision) if revision else None,
                    event_count=len(events),
                )
            )
        return matches

    @application.get(
        "/api/matches/{video_id}/timeline", response_model=TimelineResponse
    )
    def get_timeline(video_id: str) -> TimelineResponse:
        match_dir = _match_dir(root, video_id)
        windows_artifact = _read_json_object(match_dir / "windows.json", default={})
        raw_windows = windows_artifact.get("windows", [])
        if not isinstance(raw_windows, list):
            raise HTTPException(status_code=500, detail="Invalid windows artifact")
        try:
            windows = [TimelineWindow.model_validate(window) for window in raw_windows]
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=500, detail="Invalid timeline window"
            ) from exc
        _, _, manifest = _published_manifest(match_dir)
        artifact_events = _artifact_events(manifest)
        events = [EventResponse.model_validate(event) for event in artifact_events]
        accepted_proposals = {
            str(event["from_proposal"])
            for event in artifact_events
            if event.get("from_proposal") is not None
        }
        proposals = _read_json_object(
            match_dir / "proposals.json", default={"proposals": []}
        )
        rows = proposals.get("proposals", [])
        if not isinstance(rows, list):
            raise HTTPException(status_code=500, detail="Invalid proposals artifact")
        by_id = {
            str(row.get("id")): row
            for row in rows
            if isinstance(row, dict) and row.get("id")
        }
        decisions = _read_json_object(match_dir / "decisions.json", default={})
        rejected: list[RejectedProposal] = []
        for proposal_id, decision in decisions.items():
            if (
                proposal_id in accepted_proposals
                or not isinstance(decision, dict)
                or decision.get("status") != "rejected"
            ):
                continue
            proposal = by_id.get(proposal_id)
            if proposal is None:
                continue
            rejected.append(
                RejectedProposal(
                    proposal_id=proposal_id,
                    t_start=proposal["t_start"],
                    t_end=proposal["t_end"],
                    caption=str(proposal.get("caption", "")),
                )
            )
        return TimelineResponse(
            duration=float(windows_artifact.get("duration", 0.0)),
            windows=windows,
            events=events,
            rejected=rejected,
        )

    @application.get(
        "/api/matches/{video_id}/proposals",
        response_model=list[ProposalResponse],
    )
    def get_proposals(video_id: str) -> list[ProposalResponse]:
        match_dir = _match_dir(root, video_id)
        return _proposal_responses(match_dir, video_id)

    @application.get(
        "/api/matches/{video_id}/capabilities",
        response_model=MatchCapabilities,
    )
    def get_capabilities(video_id: str) -> MatchCapabilities:
        match_dir = _match_dir(root, video_id)
        return MatchCapabilities(
            source_video_available=_source_video(match_dir) is not None
        )

    def compensate_point_or_mark_reconciliation(
        client: QdrantClient,
        *,
        revision: int,
        video_id: str,
        event_id: str,
        snapshot: tuple[Any, Any, dict[str, Any]] | None,
    ) -> None:
        try:
            _restore_event_point(
                client,
                revision=revision,
                video_id=video_id,
                event_id=event_id,
                snapshot=snapshot,
            )
        except Exception as exc:
            application.state.reconciliation_error = str(exc) or type(exc).__name__
            raise HTTPException(
                status_code=503,
                detail="Proposal update failed and the index requires reconciliation",
            ) from exc

    def accept_proposal_change(
        video_id: str,
        proposal_id: str,
        *,
        caption: str | None = None,
        event_type: str | None = None,
        team: str | None = None,
        player: str | None = None,
        team_supplied: bool = False,
        player_supplied: bool = False,
    ) -> DecisionResponse:
        match_dir = _match_dir(root, video_id)
        proposal = _proposal_row(match_dir, proposal_id)
        with match_lock(video_id):
            ensure_reconciled()
            revision, published_dir, manifest = _published_manifest(
                match_dir, required=True
            )
            assert revision is not None and published_dir is not None
            events = _artifact_events(manifest)
            decisions_path = match_dir / "decisions.json"
            decisions = _read_json_object(decisions_path, default={})
            event = _event_for_proposal(
                proposal,
                events,
                decisions,
                caption=caption,
                event_type=event_type,
                team=team,
                player=player,
                team_supplied=team_supplied,
                player_supplied=player_supplied,
            )
            try:
                _event_clip(match_dir, event.get("clip"))
            except HTTPException:
                # Prefer the hosted proposal preview. Cutting from the source is
                # the local fallback when no preview was prepared.
                clips_dir = match_dir / "clips"
                target = clips_dir / f"{event['id']}.mp4"
                proposal_clip = resolve_proposal_clip(match_dir, proposal_id, {})
                if proposal_clip is not None:
                    clips_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(proposal_clip, target)
                else:
                    source = _source_video(match_dir)
                    if source is None:
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                f"No clip for proposal {proposal_id} and no source "
                                "video available to cut it"
                            ),
                        ) from None
                    try:
                        cut_event(source, event, clips_dir)
                    except (OSError, RuntimeError, TypeError, ValueError) as exc:
                        raise HTTPException(
                            status_code=500,
                            detail="Could not cut the clip for this proposal",
                        ) from exc

            updated_events: list[dict[str, Any]] = []
            replaced = False
            for row in events:
                if row.get("from_proposal") == proposal_id:
                    updated_events.append(event)
                    replaced = True
                else:
                    updated_events.append(row)
            if not replaced:
                updated_events.append(event)
            updated_manifest = dict(manifest)
            updated_manifest["events"] = updated_events
            updated_manifest.setdefault("video_id", video_id)

            client: QdrantClient | None = None
            try:
                client = _request_qdrant_client()
                snapshot = _capture_event_point(
                    client,
                    revision=revision,
                    video_id=video_id,
                    event_id=str(event["id"]),
                )
                try:
                    _upsert_event(
                        client,
                        revision=revision,
                        video_id=video_id,
                        event=event,
                    )
                    # The manifest is the commit: Search holds this same match
                    # lock and cannot observe the point before this write lands.
                    _write_json_atomic(
                        published_dir / "manifest.json", updated_manifest
                    )
                except Exception as exc:
                    compensate_point_or_mark_reconciliation(
                        client,
                        revision=revision,
                        video_id=video_id,
                        event_id=str(event["id"]),
                        snapshot=snapshot,
                    )
                    if isinstance(exc, HTTPException):
                        raise
                    raise HTTPException(
                        status_code=500,
                        detail="Could not commit the proposal update",
                    ) from exc
            finally:
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        pass

            decision = {"status": "accepted", "event_id": str(event["id"])}
            decisions[proposal_id] = decision
            try:
                _write_json_atomic(decisions_path, decisions)
            except OSError as exc:
                raise HTTPException(
                    status_code=500, detail="Could not persist the proposal decision"
                ) from exc
            return DecisionResponse(proposal_id=proposal_id, **decision)

    def reject_proposal_change(video_id: str, proposal_id: str) -> DecisionResponse:
        match_dir = _match_dir(root, video_id)
        _proposal_row(match_dir, proposal_id)
        with match_lock(video_id):
            ensure_reconciled()
            revision, published_dir, manifest = _published_manifest(
                match_dir, required=True
            )
            assert revision is not None and published_dir is not None
            events = _artifact_events(manifest)
            decisions_path = match_dir / "decisions.json"
            decisions = _read_json_object(decisions_path, default={})
            accepted_event = next(
                (
                    event
                    for event in events
                    if event.get("from_proposal") == proposal_id
                ),
                None,
            )
            previous = decisions.get(proposal_id, {})
            event_id = (
                str(accepted_event["id"])
                if accepted_event is not None
                else str(previous["event_id"])
                if isinstance(previous, dict)
                and isinstance(previous.get("event_id"), str)
                else _proposal_event_id(proposal_id)
            )

            client: QdrantClient | None = None
            try:
                client = _request_qdrant_client()
                snapshot = _capture_event_point(
                    client,
                    revision=revision,
                    video_id=video_id,
                    event_id=event_id,
                )
                try:
                    _delete_event_point(
                        client,
                        revision=revision,
                        video_id=video_id,
                        event_id=event_id,
                    )
                    if accepted_event is not None:
                        updated_manifest = dict(manifest)
                        updated_manifest["events"] = [
                            event
                            for event in events
                            if event.get("from_proposal") != proposal_id
                        ]
                        # As in acceptance, this manifest write is the commit.
                        _write_json_atomic(
                            published_dir / "manifest.json", updated_manifest
                        )
                except Exception as exc:
                    compensate_point_or_mark_reconciliation(
                        client,
                        revision=revision,
                        video_id=video_id,
                        event_id=event_id,
                        snapshot=snapshot,
                    )
                    if isinstance(exc, HTTPException):
                        raise
                    raise HTTPException(
                        status_code=500,
                        detail="Could not commit the proposal rejection",
                    ) from exc
            finally:
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        pass

            decision = {"status": "rejected", "event_id": event_id}
            decisions[proposal_id] = decision
            try:
                _write_json_atomic(decisions_path, decisions)
            except OSError as exc:
                raise HTTPException(
                    status_code=500, detail="Could not persist the proposal decision"
                ) from exc
            return DecisionResponse(proposal_id=proposal_id, **decision)

    @application.post(
        "/api/matches/{video_id}/proposals/{proposal_id}/accept",
        response_model=DecisionResponse,
    )
    def accept_proposal(video_id: str, proposal_id: str) -> DecisionResponse:
        return accept_proposal_change(video_id, proposal_id)

    @application.post(
        "/api/matches/{video_id}/proposals/{proposal_id}/reject",
        response_model=DecisionResponse,
    )
    def reject_proposal(video_id: str, proposal_id: str) -> DecisionResponse:
        return reject_proposal_change(video_id, proposal_id)

    @application.post(
        "/api/matches/{video_id}/proposals/{proposal_id}/edit",
        response_model=DecisionResponse,
    )
    def edit_proposal(
        video_id: str, proposal_id: str, request: ProposalEditRequest
    ) -> DecisionResponse:
        if request.type == "none":
            return reject_proposal_change(video_id, proposal_id)
        return accept_proposal_change(
            video_id,
            proposal_id,
            caption=request.caption.strip() if request.caption is not None else None,
            event_type=request.type,
            team=request.team,
            player=request.player,
            team_supplied="team" in request.model_fields_set,
            player_supplied="player" in request.model_fields_set,
        )

    @application.post("/api/matches/{video_id}/events", response_model=EventResponse)
    def add_human_event(video_id: str, request: HumanEventRequest) -> EventResponse:
        match_dir = _match_dir(root, video_id)
        with match_lock(video_id):
            ensure_reconciled()
            source = _source_video(match_dir)
            if source is None:
                raise HTTPException(
                    status_code=409,
                    detail="Add Moment requires the source video for this match",
                )
            revision, published_dir, manifest = _published_manifest(
                match_dir, required=True
            )
            assert revision is not None and published_dir is not None
            events = _artifact_events(manifest)
            decisions = _read_json_object(match_dir / "decisions.json", default={})
            reserved_ids = [
                decision["event_id"]
                for decision in decisions.values()
                if isinstance(decision, dict)
                and isinstance(decision.get("event_id"), str)
            ]
            event_id = _next_event_id(events, reserved_ids)
            event = {
                "id": event_id,
                "from_proposal": None,
                "t_start": request.t_start,
                "t_end": request.t_end,
                "type": request.type,
                "caption": request.caption,
                "team": None,
                "player": None,
                "clip": f"clips/{event_id}.mp4",
                "verified_at": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            }
            try:
                cut_event(source, event, match_dir / "clips")
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=500, detail="Could not cut the added moment"
                ) from exc

            client: QdrantClient | None = None
            try:
                client = _request_qdrant_client()
                _upsert_event(
                    client,
                    revision=revision,
                    video_id=video_id,
                    event=event,
                )
            finally:
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        pass

            events.append(event)
            manifest["events"] = events
            manifest.setdefault("video_id", video_id)
            _write_json_atomic(published_dir / "manifest.json", manifest)
            return EventResponse.model_validate(event)

    @application.get(
        "/api/matches/{video_id}/search", response_model=list[SearchResult]
    )
    def search_events(
        video_id: str,
        q: str = Query(min_length=1),
        limit: int = Query(default=8, ge=1, le=50),
    ) -> list[SearchResult]:
        match_dir = _match_dir(root, video_id)
        with match_lock(video_id):
            # Re-check reconciliation only after acquiring the edit lock. A
            # Search that began while an edit was in flight must observe a
            # compensation failure raised by that edit, not the split point.
            ensure_reconciled()
            revision, _, manifest = _published_manifest(match_dir, required=True)
            assert revision is not None
            event_ids = [
                str(event["id"])
                for event in _artifact_events(manifest)
                if event.get("id") is not None
            ]
            if not event_ids:
                return []
            vector = _query_vector(q)
            client: QdrantClient | None = None
            try:
                client = _make_qdrant_client()
                response = client.query_points(
                    collection_name=collection_name(revision),
                    query=vector,
                    query_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="id", match=models.MatchAny(any=event_ids)
                            )
                        ]
                    ),
                    limit=limit,
                    with_payload=True,
                    with_vectors=False,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail="Qdrant search is unavailable; verify QDRANT_URL and retry",
                ) from exc
            finally:
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        pass
            results: list[SearchResult] = []
            for point in response.points:
                payload = point.payload or {}
                results.append(
                    SearchResult.model_validate({**payload, "score": point.score})
                )
            return results

    @application.post("/api/matches/{video_id}/reel", response_model=ReelResponse)
    def create_reel(video_id: str, request: ReelRequest) -> ReelResponse:
        match_dir = _match_dir(root, video_id)
        _, _, manifest = _published_manifest(match_dir, required=True)
        events = _artifact_events(manifest)
        by_id = {str(event.get("id")): event for event in events}
        missing = [event_id for event_id in request.event_ids if event_id not in by_id]
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"Published event not found: {', '.join(missing)}",
            )
        selected = [by_id[event_id] for event_id in request.event_ids]
        digest = hashlib.sha256(
            json.dumps(request.event_ids, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        destination = match_dir / "reels" / f"{digest}.mp4"
        if not destination.is_file():
            clips = [_event_clip(match_dir, event.get("clip")) for event in selected]
            _build_reel(destination, clips)
        duration = round(
            sum(float(event["t_end"]) - float(event["t_start"]) for event in selected),
            3,
        )
        return ReelResponse(
            url=f"/media/{quote(video_id, safe='')}/reels/{digest}.mp4",
            duration=duration,
            event_ids=request.event_ids,
        )

    application.mount("/media", GuardedStaticFiles(directory=root), name="media")
    if FRONTEND_DIST.is_dir():
        application.mount(
            "/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend"
        )
    return application


app = create_app()
