"""Every Angle Streamlit shell: Verify → Search → Reel."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from app.contracts import load_data_contracts, video_ids
from app.views import reel, search, verify


st.set_page_config(page_title="Every Angle", page_icon="⚽", layout="wide")
st.title("Every Angle")
st.caption("AI-assisted, human-verified football moments")

data_root = Path(os.getenv("DATA_ROOT", "data"))
ids = video_ids(data_root)
with st.sidebar:
    st.header("Demo data")
    selected_video = st.selectbox("Video", ids, index=0) if ids else None
    st.caption(f"Data root: {data_root}")

contracts = load_data_contracts(data_root, selected_video)
if not contracts["video_id"]:
    st.info("No pipeline data found. Run the offline pipeline first.")
else:
    if contracts["current_revision"]:
        st.caption(
            f"Published revision {contracts['current_revision']} · {contracts['collection']}"
        )
    view = st.radio(
        "View",
        ("verify", "search", "reel"),
        horizontal=True,
        label_visibility="collapsed",
    )
    if view == "verify":
        verify.render(st, contracts)
    elif view == "search":
        search.render(st, contracts)
    else:
        reel.render(st, contracts)
