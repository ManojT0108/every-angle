"""Data-contract loading for the app views — pure functions, no Streamlit.

Search/Reel serve ONLY the promoted revision (plan D12) — never the mutable
root manifest, which is the Verify draft.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        return default
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    return payload if isinstance(payload, dict) else default


def video_ids(data_root: Path) -> list[str]:
    if not data_root.is_dir():
        return []
    return sorted(
        path.name
        for path in data_root.iterdir()
        if path.is_dir()
        and not path.name.startswith(".")
        and ((path / "manifest.json").is_file() or (path / "proposals.json").is_file())
    )


def load_data_contracts(
    data_root: Path, video_id: str | None = None
) -> dict[str, Any]:
    """Load only the local JSON contracts consumed by the app views."""

    ids = video_ids(data_root)
    selected = video_id or (ids[0] if ids else None)
    data_dir = data_root / selected if selected else data_root
    current_revision = None
    pointer = data_dir / "CURRENT_REV"
    if pointer.is_file():
        value = pointer.read_text(encoding="utf-8").strip()
        current_revision = int(value) if value.isdigit() else None
    published_dir = (
        data_dir / "staging" / f"rev-{current_revision}" if current_revision else None
    )
    return {
        "data_root": str(data_root),
        "data_dir": str(data_dir),
        "video_id": selected,
        "current_revision": current_revision,
        "collection": f"moments_rev_{current_revision}" if current_revision else None,
        "published_dir": str(published_dir) if published_dir else None,
        "published_manifest": (
            _read_json(published_dir / "manifest.json", {"events": []})
            if published_dir
            else {"events": []}
        ),
        "proposals": _read_json(
            data_dir / "proposals.json", {"proposals": [], "runs": []}
        ),
        "decisions": _read_json(data_dir / "decisions.json", {}),
        "manifest": _read_json(data_dir / "manifest.json", {"events": []}),
    }
