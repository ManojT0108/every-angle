"""M0 Reel view placeholder."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def render(st: Any, contracts: dict[str, Any]) -> None:
    # Only the promoted revision's manifest and clips are served (plan D12);
    # the mutable root manifest is Verify's draft, not this view's input.
    manifest = contracts.get("published_manifest", {})
    events = manifest.get("events", [])
    published = contracts.get("published_dir")
    published_dir = Path(published) if published else None
    st.subheader("Reel")
    st.caption(
        "M0 placeholder: pre-cut verified clips will be assembled into a reel in a later milestone."
    )
    if not events or published_dir is None:
        st.info("No published revision yet — verify moments and publish first.")
        return
    st.write(f"{len(events)} published event(s) available")
    for event in events:
        clip_value = event.get("clip")
        clip_path = (
            published_dir / clip_value if isinstance(clip_value, str) else None
        )
        with st.expander(f"{event.get('id', 'event')} · {event.get('type', 'moment')}"):
            st.write(event.get("caption", ""))
            if clip_path and clip_path.is_file():
                st.video(str(clip_path))
            else:
                st.caption("Clip not generated yet.")
