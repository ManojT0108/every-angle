"""Manifest-grounded commentary placeholder."""

from __future__ import annotations

from typing import Any


def render_template(st: Any, events: list[dict[str, Any]]) -> None:
    if not events:
        st.caption("Commentary becomes available after verification.")
        return
    captions = [event.get("caption") for event in events if event.get("caption")]
    st.write(" ".join(captions))
