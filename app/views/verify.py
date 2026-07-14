"""M0 Verify view placeholder."""

from __future__ import annotations

from typing import Any


def render(st: Any, contracts: dict[str, Any]) -> None:
    proposals = contracts.get("proposals", {})
    decisions = contracts.get("decisions", {})
    rows = proposals.get("proposals", [])
    decision_map = decisions if isinstance(decisions, dict) else {}
    pending = [
        row
        for row in rows
        if decision_map.get(row.get("id"), {}).get("status", "pending") == "pending"
    ]
    st.subheader("Verify")
    st.caption(
        "M0 placeholder: proposals and decisions are loaded from the local data contracts."
    )
    st.metric("Pending proposals", len(pending))
    if pending:
        st.dataframe(
            [
                {
                    "id": row.get("id"),
                    "time": f"{row.get('t_start', 0):.1f}–{row.get('t_end', 0):.1f}s",
                    "type": row.get("type"),
                    "confidence": row.get("confidence"),
                    "caption": row.get("caption"),
                }
                for row in pending
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No proposals found yet. Run the offline pipeline first.")
