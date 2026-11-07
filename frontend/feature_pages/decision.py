import streamlit as st
import httpx
import os

API_URL = os.getenv("API_URL", "http://localhost:8000")


def show_decision(token: str):
    headers = {"Authorization": f"Bearer {token}"}
    st.subheader("🧭 Laya Decision Layer — Rank Campaigns")

    st.info(
        "Forecasts and campaign candidates are prepared and cached by the backend "
        "during startup. The Decision Layer only runs the selected ranking framework."
    )

    # ── Shared options ──────────────────────────────────────────
    with st.expander("⚙️ Forecast & Objective Settings", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("Forecast Model", value="linear_regression", disabled=True)
            st.caption("Forecast dates and horizon are taken from each campaign.")
        with col2:
            w_contrib = col2.slider("Weight: Expected Contribution", 0.0, 1.0, 0.35, 0.05)
            w_inv = col2.slider("Weight: Inventory Suitability", 0.0, 1.0, 0.25, 0.05)
            w_stock = col2.slider("Weight: Stockout Safety", 0.0, 1.0, 0.20, 0.05)
            w_roi = col2.slider("Weight: Cost Efficiency (ROI)", 0.0, 1.0, 0.10, 0.05)
            w_seg = col2.slider("Weight: Segment Priority", 0.0, 1.0, 0.10, 0.05)

    # ── Prepared candidates and ranking ─────────────────────────
    with st.expander("📊 Prepared Campaign Candidates & Ranking", expanded=True):
        st.caption(
            "Forecasts and campaign candidates are prepared by the backend at startup. "
            "Ranking only runs when you request it."
        )

        refresh_col, rank_col = st.columns(2)
        if refresh_col.button("🔄 Refresh Prepared Candidates", use_container_width=True):
            with st.spinner("Refreshing forecasts and rebuilding campaign candidates…"):
                try:
                    response = httpx.post(
                        f"{API_URL}/decision/candidates/refresh",
                        headers=headers,
                        timeout=180,
                    )
                    response.raise_for_status()
                    refreshed = response.json()
                    st.success(
                        f"Prepared {refreshed.get('total_candidates', 0)} candidates."
                    )
                    if refreshed.get("skipped"):
                        st.warning(f"{len(refreshed['skipped'])} campaign(s) could not be prepared.")
                        st.json(refreshed["skipped"])
                except httpx.HTTPStatusError as e:
                    st.error(f"HTTP {e.response.status_code}: {e.response.text}")
                except Exception as e:
                    st.error(f"Candidate refresh failed: {e}")

        if rank_col.button("🏆 Load Prepared Candidates & Rank", use_container_width=True):
            with st.spinner("Loading prepared candidates and running Laya ranking…"):
                try:
                    response = httpx.get(
                        f"{API_URL}/decision/candidates",
                        headers=headers,
                        timeout=30,
                    )
                    response.raise_for_status()
                    prepared = response.json()
                    candidates = prepared.get("candidates", [])

                    if not candidates:
                        st.warning(
                            "No prepared candidates are available. Use 'Refresh Prepared Candidates' "
                            "or check the backend startup logs."
                        )
                        if prepared.get("skipped"):
                            st.json(prepared["skipped"])
                        return

                    st.caption(
                        f"Prepared at: {prepared.get('prepared_at') or 'unknown'} · "
                        f"{len(candidates)} candidate(s) ready"
                    )
                    feasible_count = sum(1 for c in candidates if c["is_feasible"])
                    st.metric("Total Candidates", len(candidates))
                    col1, col2 = st.columns(2)
                    col1.metric("Feasible", feasible_count)
                    col2.metric("Infeasible (filtered out)", len(candidates) - feasible_count)

                    if prepared.get("skipped"):
                        with st.expander("⚠️ Campaigns skipped during preparation"):
                            st.json(prepared["skipped"])

                    payload = {
                        "candidates": candidates,
                        "framework": "laya",
                        "forecast_version": "m5-dynamic-linear-v2",
                        "weights": {
                            "expected_contribution": w_contrib,
                            "inventory_suitability": w_inv,
                            "stockout_exposure_reduction": w_stock,
                            "cost_efficiency": w_roi,
                            "segment_priority": w_seg,
                        },
                    }
                    rank_response = httpx.post(
                        f"{API_URL}/decision/rank",
                        json=payload,
                        headers=headers,
                        timeout=30,
                    )
                    rank_response.raise_for_status()
                    result = rank_response.json()

                    winner = result.get("selected_campaign_id")
                    if winner:
                        st.success(f"🏆 Selected Campaign: **{winner}**")
                    st.caption(f"Decision rationale: {result.get('decision_rationale', '—')}")

                    ranked = result.get("ranked_candidates", [])
                    if ranked:
                        st.subheader("Ranked Candidates")
                        import pandas as pd
                        rows = [{
                            "Rank": rc["rank"],
                            "Campaign ID": rc["campaign_id"],
                            "Campaign Name": rc["campaign_name"],
                            "Composite Score": round(rc["composite_score"], 4),
                            "Rationale": rc["rationale"],
                        } for rc in ranked]
                        st.dataframe(pd.DataFrame(rows), use_container_width=True)

                    with st.expander("📄 Full Response"):
                        st.json(result)

                except httpx.HTTPStatusError as e:
                    st.error(f"HTTP {e.response.status_code}: {e.response.text}")
                except Exception as e:
                    st.error(f"Ranking failed: {e}")

    st.divider()

