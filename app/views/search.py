"""M0 Search view placeholder."""

from __future__ import annotations

from typing import Any


def render(st: Any, contracts: dict[str, Any]) -> None:
    # Only the promoted revision is searchable (plan D12) — the root
    # manifest draft never reaches this view.
    manifest = contracts.get("published_manifest", {})
    events = manifest.get("events", [])
    st.subheader("Search")
    st.caption(
        "M0 placeholder: published events are loaded; semantic search is enabled after indexing."
    )
    query = st.text_input(
        "Search verified moments", placeholder="e.g. near-post finish"
    )
    if query:
        st.info(
            "Qdrant search will use the local embedding model in the next milestone."
        )
    if events:
        st.dataframe(
            [
                {
                    "id": event.get("id"),
                    "type": event.get("type"),
                    "caption": event.get("caption"),
                    "clip": event.get("clip"),
                }
                for event in events
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("The verified manifest is empty.")
