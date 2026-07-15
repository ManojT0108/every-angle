"""FastAPI backend for the Every Angle web application."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, model_validator
from qdrant_client import QdrantClient
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from pipeline.index_qdrant import (
    DEFAULT_QDRANT_URL,
    EMBEDDING_MODEL,
    collection_name,
)


DATA_ROOT = Path(os.getenv("DATA_ROOT", "data")).resolve()
FRONTEND_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
EVENT_TYPES = Literal[
    "goal", "save", "penalty", "card", "counterattack", "celebration"
]

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
    team: str | None = None
    player: str | None = None
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
    status: Literal["pending", "accepted", "rejected"]
    frames: list[str]


class DecisionRequest(BaseModel):
    """A human accept/reject action for one proposal."""

    proposal_id: str = Field(min_length=1)
    status: Literal["accepted", "rejected"]


class DecisionResponse(BaseModel):
    """The persisted decision state for one proposal."""

    proposal_id: str
    status: Literal["accepted", "rejected"]
    event_id: str | None = None


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
    if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
        raise HTTPException(status_code=500, detail="Invalid manifest events")
    return cast(list[dict[str, Any]], events)


def _media_url(video_id: str, relative_path: str) -> str | None:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        return None
    full_path = PurePosixPath(video_id) / path
    return f"/media/{quote(full_path.as_posix(), safe='/')}"


def _latest_claude_run_id(proposals: dict[str, Any]) -> str | None:
    runs = proposals.get("runs", [])
    if not isinstance(runs, list):
        raise HTTPException(status_code=500, detail="Invalid proposals runs")
    candidates = [
        (str(run.get("created_at", "")), index, str(run.get("run_id", "")))
        for index, run in enumerate(runs)
        if isinstance(run, dict)
        and isinstance(run.get("captioner"), dict)
        and run["captioner"].get("name") == "claude"
        and run.get("run_id")
    ]
    return max(candidates)[2] if candidates else None


def _proposal_responses(match_dir: Path, video_id: str) -> list[ProposalResponse]:
    artifact = _read_json_object(
        match_dir / "proposals.json", default={"runs": [], "proposals": []}
    )
    run_id = _latest_claude_run_id(artifact)
    if run_id is None:
        return []
    rows = artifact.get("proposals", [])
    if not isinstance(rows, list):
        raise HTTPException(status_code=500, detail="Invalid proposals artifact")
    decisions = _read_json_object(match_dir / "decisions.json", default={})
    responses: list[ProposalResponse] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("run_id") != run_id:
            continue
        proposal_id = str(row.get("id", ""))
        decision = decisions.get(proposal_id, {})
        status = decision.get("status", "pending") if isinstance(decision, dict) else "pending"
        if status not in {"pending", "accepted", "rejected"}:
            status = "pending"
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
                    type=str(row.get("type", "")),
                    confidence=str(row.get("confidence", "")),
                    caption=str(row.get("caption", "")),
                    status=status,
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

            _EMBEDDING_MODEL_INSTANCE = TextEmbedding(model_name=EMBEDDING_MODEL)
        except Exception as exc:  # startup remains available for non-search endpoints
            _EMBEDDING_LOAD_ERROR = str(exc) or type(exc).__name__


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    _load_embedding_model()
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


def _next_event_id(events: list[dict[str, Any]]) -> str:
    numbers = [
        int(match.group(1))
        for event in events
        if (match := _EVENT_ID_PATTERN.fullmatch(str(event.get("id", ""))))
    ]
    return f"e-{max(numbers, default=0) + 1:03d}"


def _safe_published_clip(published_dir: Path, clip_value: Any) -> Path:
    if not isinstance(clip_value, str):
        raise HTTPException(status_code=500, detail="Published event has no clip")
    relative = PurePosixPath(clip_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise HTTPException(status_code=500, detail="Published event has an invalid clip")
    clip = (published_dir / Path(*relative.parts)).resolve()
    if not clip.is_relative_to(published_dir.resolve()) or not clip.is_file():
        raise HTTPException(status_code=500, detail="Published event clip is missing")
    return clip


def _ffconcat_path(path: Path) -> str:
    return str(path).replace("'", "'\\''")


def _build_reel(destination: Path, clips: list[Path]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    concat_path: Path | None = None
    encoded_path = destination.parent / f".{destination.stem}.{uuid.uuid4().hex}.tmp.mp4"
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
            message = result.stderr.decode(errors="replace").strip()
            raise HTTPException(status_code=500, detail=f"Reel encoding failed: {message}")
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
            raise HTTPException(status_code=500, detail="Invalid timeline window") from exc
        _, _, manifest = _published_manifest(match_dir)
        events = [EventResponse.model_validate(event) for event in _artifact_events(manifest)]
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
            if not isinstance(decision, dict) or decision.get("status") != "rejected":
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

    @application.post(
        "/api/matches/{video_id}/decisions", response_model=DecisionResponse
    )
    def update_decision(video_id: str, request: DecisionRequest) -> DecisionResponse:
        match_dir = _match_dir(root, video_id)
        proposals = _read_json_object(
            match_dir / "proposals.json", default={"proposals": []}
        )
        rows = proposals.get("proposals", [])
        known_ids = {
            str(row.get("id"))
            for row in rows
            if isinstance(row, dict) and row.get("id")
        } if isinstance(rows, list) else set()
        if request.proposal_id not in known_ids:
            raise HTTPException(status_code=404, detail="Proposal not found")
        path = match_dir / "decisions.json"
        decisions = _read_json_object(path, default={})
        previous = decisions.get(request.proposal_id, {})
        updated: dict[str, Any] = {"status": request.status}
        if (
            request.status == "accepted"
            and isinstance(previous, dict)
            and isinstance(previous.get("event_id"), str)
        ):
            updated["event_id"] = previous["event_id"]
        decisions[request.proposal_id] = updated
        _write_json_atomic(path, decisions)
        return DecisionResponse(proposal_id=request.proposal_id, **updated)

    @application.post(
        "/api/matches/{video_id}/events", response_model=EventResponse
    )
    def add_human_event(video_id: str, request: HumanEventRequest) -> EventResponse:
        match_dir = _match_dir(root, video_id)
        path = match_dir / "manifest.json"
        manifest = _read_json_object(
            path, default={"video_id": video_id, "events": []}
        )
        events = _artifact_events(manifest)
        event_id = _next_event_id(events)
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
        events.append(event)
        manifest["events"] = events
        manifest.setdefault("video_id", video_id)
        _write_json_atomic(path, manifest)
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
        revision, _, _ = _published_manifest(match_dir, required=True)
        assert revision is not None
        vector = _query_vector(q)
        client: QdrantClient | None = None
        try:
            client = _make_qdrant_client()
            response = client.query_points(
                collection_name=collection_name(revision),
                query=vector,
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
            results.append(SearchResult.model_validate({**payload, "score": point.score}))
        return results

    @application.post(
        "/api/matches/{video_id}/reel", response_model=ReelResponse
    )
    def create_reel(video_id: str, request: ReelRequest) -> ReelResponse:
        match_dir = _match_dir(root, video_id)
        _, published_dir, manifest = _published_manifest(match_dir, required=True)
        assert published_dir is not None
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
            clips = [
                _safe_published_clip(published_dir, event.get("clip"))
                for event in selected
            ]
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

    application.mount(
        "/media", GuardedStaticFiles(directory=root), name="media"
    )
    if FRONTEND_DIST.is_dir():
        application.mount(
            "/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend"
        )
    return application


app = create_app()
