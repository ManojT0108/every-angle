"""Build a revisioned Qdrant index from the verified event manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path, PurePosixPath
from typing import Any


EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
# FastEmbed's model registry is locked by the pinned fastembed dependency in
# requirements.txt. Keep this name in the artifact metadata until the release
# bundle records a concrete downloaded model checksum (M1/D13).
EMBEDDING_MODEL_REVISION = "fastembed-pinned"
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_VECTOR_SIZE = 384


def collection_name(revision: int) -> str:
    if revision < 1:
        raise ValueError("revision must be positive")
    return f"moments_rev_{revision}"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _next_revision(data_dir: Path) -> int:
    pointer = data_dir / "CURRENT_REV"
    if not pointer.exists():
        return 1
    try:
        return int(pointer.read_text(encoding="utf-8").strip()) + 1
    except ValueError as exc:
        raise ValueError(f"invalid revision pointer: {pointer}") from exc


def _safe_relative_path(value: str, *, label: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must be a relative path without '..': {value}")
    return path


class MockProposalError(RuntimeError):
    """A published event traces back to a MockCaptioner run."""


def assert_no_mock_provenance(data_dir: Path, manifest: dict[str, Any]) -> None:
    """Refuse to publish events derived from mock captions.

    The plan's central honesty claim is that moments are AI-proposed. proposals.json
    accumulates runs, and a mock run sits right alongside the real ones — so without
    this check a demo could be quietly powered by canned text while claiming to be
    AI-generated. Resolve every event's proposal back to its run and reject mock.
    Human-added events (from_proposal = null) are fine: a human is not a mock.
    """
    proposals_path = data_dir / "proposals.json"
    if not proposals_path.is_file():
        # No proposals file is fine ONLY if nothing claims to be AI-proposed.
        # Otherwise the events assert a provenance we cannot verify — and an
        # unverifiable claim of "AI-proposed" is exactly what this gate exists
        # to stop.
        orphans = [
            e.get("id") for e in manifest.get("events", [])
            if e.get("from_proposal") is not None
        ]
        if orphans:
            raise MockProposalError(
                f"events {orphans} cite proposals, but {proposals_path} is missing — "
                "their captioner cannot be verified, so they cannot be published as "
                "AI-proposed"
            )
        return
    payload = _read_json(proposals_path)
    runs = {r["run_id"]: r for r in payload.get("runs", [])}
    by_id = {p["id"]: p for p in payload.get("proposals", [])}

    for event in manifest.get("events", []):
        pid = event.get("from_proposal")
        if pid is None:
            continue                                   # human-added; legitimate
        proposal = by_id.get(pid)
        if proposal is None:
            raise MockProposalError(
                f"event {event.get('id')} cites unknown proposal {pid!r}"
            )
        run = runs.get(proposal.get("run_id"), {})
        captioner = (run.get("captioner") or {}).get("name")
        if captioner != "claude":
            raise MockProposalError(
                f"event {event.get('id')} derives from proposal {pid!r} whose run "
                f"used captioner {captioner!r} — refusing to publish mock-derived "
                "moments as AI-proposed"
            )


def stage_revision(
    data_dir: Path, manifest_path: Path, revision: int | None = None
) -> Path:
    """Stage a complete manifest and its referenced clips before publishing."""

    data_dir.mkdir(parents=True, exist_ok=True)
    revision = revision or _next_revision(data_dir)
    staging_dir = data_dir / "staging" / f"rev-{revision}"
    if staging_dir.exists():
        raise FileExistsError(f"staging revision already exists: {staging_dir}")
    manifest = _read_json(manifest_path)
    if not isinstance(manifest.get("events"), list):
        raise ValueError("manifest.json must contain an events list")
    assert_no_mock_provenance(data_dir, manifest)
    source_clips: list[tuple[PurePosixPath, Path]] = []
    for event in manifest["events"]:
        clip_value = event.get("clip")
        if not isinstance(clip_value, str):
            raise ValueError(f"event {event.get('id')} has no clip path")
        relative_clip = _safe_relative_path(clip_value, label="event.clip")
        source_clip = (data_dir / Path(*relative_clip.parts)).resolve()
        if (
            not source_clip.is_relative_to(data_dir.resolve())
            or not source_clip.is_file()
        ):
            raise FileNotFoundError(
                f"event clip does not exist inside data directory: {clip_value}"
            )
        source_clips.append((relative_clip, source_clip))
    staging_dir.mkdir(parents=True)
    staged_manifest = dict(manifest)
    staged_manifest["collection"] = collection_name(revision)
    _write_json_atomic(staging_dir / "manifest.json", staged_manifest)
    checksums: dict[str, str] = {
        "manifest.json": _sha256_file(staging_dir / "manifest.json")
    }
    for relative_clip, source_clip in source_clips:
        target_clip = staging_dir / Path(*relative_clip.parts)
        target_clip.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_clip, target_clip)
        checksums[target_clip.relative_to(staging_dir).as_posix()] = _sha256_file(
            target_clip
        )
    # Thumbnails are intentionally not generated in M0. D12 will add them to
    # this stage before the bundle-export implementation is enabled.
    _write_json_atomic(
        staging_dir / "stage.json",
        {
            "revision": revision,
            "collection": collection_name(revision),
            "checksums": checksums,
        },
    )
    return staging_dir


def _probe_clip_codecs(path: Path) -> tuple[bool, bool]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return False, False
    try:
        streams = json.loads(result.stdout.decode()).get("streams", [])
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False, False
    video = any(
        stream.get("codec_type") == "video" and stream.get("codec_name") == "h264"
        for stream in streams
    )
    audio = any(
        stream.get("codec_type") == "audio" and stream.get("codec_name") == "aac"
        for stream in streams
    )
    return video, audio


def validate_staged_revision(staging_dir: Path) -> dict[str, Any]:
    """Validate playable H.264/AAC clips before a Qdrant build."""

    manifest_path = staging_dir / "manifest.json"
    manifest = _read_json(manifest_path)
    events = manifest.get("events")
    if not isinstance(events, list):
        raise ValueError("staged manifest must contain an events list")
    for event in events:
        clip_value = event.get("clip")
        if not isinstance(clip_value, str):
            raise ValueError(f"event {event.get('id')} has no clip")
        clip = staging_dir / Path(
            *_safe_relative_path(clip_value, label="event.clip").parts
        )
        if not clip.is_file():
            raise FileNotFoundError(f"staged clip is missing: {clip}")
        has_video, has_audio = _probe_clip_codecs(clip)
        if not has_video or not has_audio:
            raise ValueError(f"staged clip is not playable H.264/AAC: {clip}")
    return manifest


def _event_text(event: dict[str, Any]) -> str:
    return f"{event.get('caption', '')} {event.get('type', '')}".strip()


def _embed_texts(texts: list[str]) -> list[list[float]]:
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:
        raise RuntimeError(
            "indexing requires fastembed; install pinned requirements.txt"
        ) from exc
    embedder = TextEmbedding(model_name=EMBEDDING_MODEL)
    return [list(vector) for vector in embedder.embed(texts)]


def _point_id(video_id: str, event_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"every-angle:{video_id}:{event_id}"))


def rebuild_collection_from_manifest(
    manifest: dict[str, Any],
    *,
    qdrant_url: str = DEFAULT_QDRANT_URL,
    qdrant_api_key: str | None = None,
    collection: str,
) -> int:
    """Idempotently recreate one revision collection from manifest truth."""

    try:
        from qdrant_client import QdrantClient, models
    except ImportError as exc:
        raise RuntimeError(
            "indexing requires qdrant-client; install pinned requirements.txt"
        ) from exc
    events = manifest.get("events", [])
    if not isinstance(events, list):
        raise ValueError("manifest must contain an events list")
    texts = [_event_text(event) for event in events]
    vectors = _embed_texts(texts) if texts else []
    vector_size = len(vectors[0]) if vectors else DEFAULT_VECTOR_SIZE
    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key or None)
    try:
        if client.collection_exists(collection):
            client.delete_collection(collection)
        client.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(
                size=vector_size, distance=models.Distance.COSINE
            ),
        )
        if vectors:
            points = [
                models.PointStruct(
                    id=_point_id(str(manifest.get("video_id", "")), str(event["id"])),
                    vector=vector,
                    payload=event,
                )
                for event, vector in zip(events, vectors)
            ]
            client.upsert(collection_name=collection, points=points, wait=True)
        count = client.count(collection_name=collection, exact=True).count
        if count != len(events):
            raise RuntimeError(
                f"Qdrant point count mismatch: expected {len(events)}, got {count}"
            )
        return count
    finally:
        client.close()


def promote_revision(data_dir: Path, revision: int) -> None:
    """Atomically make a validated revision the local current pointer."""

    pointer = data_dir / "CURRENT_REV"
    temporary = data_dir / "CURRENT_REV.tmp"
    temporary.write_text(f"{revision}\n", encoding="utf-8")
    temporary.replace(pointer)


def publish_revision(
    data_dir: Path,
    manifest_path: Path,
    *,
    qdrant_url: str = DEFAULT_QDRANT_URL,
    qdrant_api_key: str | None = None,
    revision: int | None = None,
) -> dict[str, Any]:
    """Stage, validate, index, then atomically promote a complete revision."""

    staging_dir = stage_revision(data_dir, manifest_path, revision=revision)
    staged_manifest = validate_staged_revision(staging_dir)
    revision = int(staging_dir.name.removeprefix("rev-"))
    name = collection_name(revision)
    count = rebuild_collection_from_manifest(
        staged_manifest,
        qdrant_url=qdrant_url,
        qdrant_api_key=qdrant_api_key,
        collection=name,
    )
    expected = len(staged_manifest["events"])
    if count != expected:
        raise RuntimeError(
            f"staged revision count mismatch: expected {expected}, got {count}"
        )
    promote_revision(data_dir, revision)
    # TODO(D10): export only this promoted staging directory as bundle-revN.zip,
    # include bundle.json checksums, then upload it to the selected object store.
    return {
        "revision": revision,
        "collection": name,
        "event_count": expected,
        "staging_dir": str(staging_dir),
        "embedding_model": EMBEDDING_MODEL,
        "embedding_model_revision": EMBEDDING_MODEL_REVISION,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument(
        "--qdrant-url", default=os.getenv("QDRANT_URL", DEFAULT_QDRANT_URL)
    )
    parser.add_argument("--qdrant-api-key", default=os.getenv("QDRANT_API_KEY"))
    parser.add_argument("--revision", type=int, default=None)
    args = parser.parse_args()
    data_dir = args.data_dir or args.manifest.parent
    result = publish_revision(
        data_dir,
        args.manifest,
        qdrant_url=args.qdrant_url,
        qdrant_api_key=args.qdrant_api_key,
        revision=args.revision,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
