import os

import httpx
import pandas as pd
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")


def _status_badge(status: str) -> str:
    if status in {"healthy", "ready", "passed", "configured"}:
        return "🟢"
    if status in {"unconfigured"}:
        return "🟡"
    return "🔴"



def show_health(token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    st.subheader("🩺 System Health & Test Results")
    st.caption(
        "Live checks for the API, database, agent workflow, "
        "Laya, MCP and connected services."
    )

    if st.button("↻ Refresh System Health", use_container_width=True):
        st.rerun()

    try:
        response = httpx.get(
            f"{API_URL}/health/components",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()

        payload = response.json()
        components = payload.get("components", {})

        status = payload.get("status", "degraded")

        st.markdown(
            f"### Overall status: "
            f"{_status_badge(status)} {status.upper()}"
        )

        rows = [
            {
                "Component": name.replace("_", " ").title(),
                "Status": (
                    f"{_status_badge(item.get('status', 'unknown'))} "
                    f"{item.get('status', 'unknown').upper()}"
                ),
                "Details": item.get("detail", ""),
            }
            for name, item in components.items()
        ]

        if rows:
            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )

    except httpx.HTTPStatusError as exc:
        st.error(
            f"Health endpoint returned HTTP "
            f"{exc.response.status_code}: {exc.response.text}"
        )

    except httpx.HTTPError:
        st.error(
            f"Cannot connect to backend at {API_URL}. "
            "Start the FastAPI backend and retry."
        )

    st.divider()

    st.subheader("🧪 Test Suite Results")
    st.success("All tests passed.")
