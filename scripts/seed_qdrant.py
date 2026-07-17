"""Seed Qdrant Cloud with match-001's verified events — create-if-missing + upsert-verify.

Non-destructive by default (safe re-run); destructive rebuild requires --force.
Env: QDRANT_URL, QDRANT_API_KEY. Run: ./.venv/bin/python scripts/seed_qdrant.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from qdrant_client import QdrantClient, models

from pipeline.index_qdrant import (
    DEFAULT_VECTOR_SIZE,
    EMBEDDING_MODEL,
    _point_id,
    collection_name,
    event_text,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default="deploy/bundle/match-001")
    ap.add_argument("--video-id", default="match-001")
    ap.add_argument("--force", action="store_true", help="delete+recreate the collection first")
    args = ap.parse_args()

    url = os.environ.get("QDRANT_URL")
    key = os.environ.get("QDRANT_API_KEY")
    if not url:
        sys.exit("QDRANT_URL is required (source .env.deploy)")

    bundle = Path(args.bundle)
    manifest = json.loads((bundle / "staging/rev-1/manifest.json").read_text())
    revision = int((bundle / "CURRENT_REV").read_text().strip())
    coll = collection_name(revision)
    events = manifest["events"]

    client = QdrantClient(url=url, api_key=key)
    exists = client.collection_exists(coll)
    if exists and args.force:
        client.delete_collection(coll)
        exists = False
        print(f"--force: deleted {coll}")
    if not exists:
        client.create_collection(
            collection_name=coll,
            vectors_config=models.VectorParams(
                size=DEFAULT_VECTOR_SIZE, distance=models.Distance.COSINE
            ),
        )
        print(f"created {coll}")
    else:
        print(f"{coll} exists — upserting {len(events)} events (non-destructive)")

    # Payload index on `id` — REQUIRED by Qdrant server >=1.18 for the search
    # filter (payload.id in manifest ids). Idempotent: ignore "already exists".
    try:
        client.create_payload_index(
            collection_name=coll,
            field_name="id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        print("created payload index on 'id'")
    except Exception as exc:  # noqa: BLE001 - index may already exist
        print(f"payload index on 'id': {type(exc).__name__} (likely already present)")

    from fastembed import TextEmbedding

    embedder = TextEmbedding(model_name=EMBEDDING_MODEL)
    vectors = list(embedder.embed([event_text(e) for e in events]))
    points = [
        models.PointStruct(
            id=_point_id(args.video_id, str(e["id"])),
            vector=[float(x) for x in v],
            payload=e,
        )
        for e, v in zip(events, vectors, strict=True)
    ]
    client.upsert(collection_name=coll, points=points, wait=True)
    count = client.count(collection_name=coll, exact=True).count
    print(f"seeded: {count} points in {coll}")
    if count < len(events):
        sys.exit(f"verify failed: expected >= {len(events)}, got {count}")


if __name__ == "__main__":
    main()
