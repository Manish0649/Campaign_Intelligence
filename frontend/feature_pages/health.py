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


def show_health(token: str | None = None, role: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    st.subheader("🩺 System Health & Test Results")
    st.caption("Live checks for the API, database, agent workflow, Laya, MCP and connected services.")

    col_a, col_b = st.columns(2)
    col_a.button("↻ Refresh System Health", use_container_width=True)
    run_tests = False
    if role == "SYS-ADMIN":
        run_tests = col_b.button("▶ Run Pytest Suite", use_container_width=True)
    else:
        col_b.info("Pytest execution is available to SYS-ADMIN users.")

    try:
        response = httpx.get(f"{API_URL}/health/components", headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        components = payload.get("components", {})
        st.markdown(f"### Overall status: {_status_badge(payload.get('status', 'degraded'))} {payload.get('status', 'unknown').upper()}")
        rows = [
            {"Component": name.replace("_", " ").title(), "Status": f"{_status_badge(item.get('status', 'unknown'))} {item.get('status', 'unknown').upper()}", "Details": item.get("detail", "")}
            for name, item in components.items()
        ]
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    except httpx.HTTPStatusError as exc:
        st.error(f"Health endpoint returned HTTP {exc.response.status_code}: {exc.response.text}")
    except httpx.HTTPError:
        st.error(f"Cannot connect to backend at {API_URL}. Start the FastAPI backend and retry.")

    if run_tests:
        with st.spinner("Running pytest suite on the backend. This may take up to 3 minutes…"):
            try:
                response = httpx.get(f"{API_URL}/health/tests", headers=headers, timeout=190)
                response.raise_for_status()
                test_result = response.json()
                counts = test_result.get("counts", {})
                st.session_state["last_pytest_result"] = test_result
            except httpx.HTTPStatusError as exc:
                st.error(f"Pytest request failed (HTTP {exc.response.status_code}): {exc.response.text}")
            except httpx.HTTPError as exc:
                st.error(f"Could not run pytest: {exc}")

    test_result = st.session_state.get("last_pytest_result")
    if test_result:
        counts = test_result.get("counts", {})
        st.divider()
        st.subheader("🧪 Pytest Results")
        metric_cols = st.columns(4)
        metric_cols[0].metric("Passed", counts.get("passed", 0))
        metric_cols[1].metric("Failed", counts.get("failed", 0))
        metric_cols[2].metric("Errors", counts.get("errors", 0))
        metric_cols[3].metric("Skipped", counts.get("skipped", 0))
        if test_result.get("status") == "passed":
            st.success(test_result.get("summary", "All tests passed."))
        else:
            st.error(test_result.get("summary", "Some tests failed."))
        with st.expander("Pytest output"):
            st.code(test_result.get("output", ""), language="text")
