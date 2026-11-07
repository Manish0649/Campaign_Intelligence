import streamlit as st
import httpx
import os
from datetime import date, timedelta

API_URL = os.getenv("API_URL", "http://localhost:8000")


def show_feasibility(token: str):
    """Full UI for the Feasibility Engine — covers all three feasibility endpoints."""
    headers = {"Authorization": f"Bearer {token}"}
    st.subheader("🔧 Feasibility Engine")

    # ───────────────────── List All Campaigns ─────────────────────
    with st.expander("📋 List All Campaigns"):
        if st.button("Fetch Campaigns"):
            try:
                r = httpx.get(f"{API_URL}/campaigns", headers=headers, timeout=10)
                r.raise_for_status()
                campaigns = r.json()
                if campaigns:
                    st.success(f"Found {len(campaigns)} campaign(s)")
                    for c in campaigns:
                        st.markdown(f"- **{c.get('campaign_id')}** – {c.get('campaign_name', '—')}")
                else:
                    st.info("No campaigns found in the database.")
            except httpx.HTTPStatusError as e:
                st.error(f"HTTP {e.response.status_code}: {e.response.text}")
            except Exception as e:
                st.error(f"Error: {e}")

    st.divider()

    # ───────────────────── Run Feasibility Check ─────────────────────
    with st.expander("✅ Run Feasibility Check (POST /campaigns/feasibility)"):
        st.caption("Evaluates budget, inventory, supplier readiness, and forecast for a campaign.")
        campaign_id_f = st.text_input("Campaign ID", key="feas_cid")
        product_ids_f = st.text_input("Product IDs (comma‑separated)", value="p1,p2", key="feas_pids")
        # Forecast history ends on 2016-04-24. Set explicit calendar bounds:
        # Streamlit's implicit date_input lower bound can otherwise prevent
        # navigation to dates earlier than roughly 10 years before today.
        earliest_forecast_date = date(2016, 4, 25)
        latest_forecast_date = date(2036, 4, 19)  # 7,300-day lead limit from history end
        default_start_date = min(
            max(date.today() + timedelta(days=1), earliest_forecast_date),
            latest_forecast_date,
        )
        default_end_date = min(default_start_date + timedelta(days=7), latest_forecast_date)

        date_col1, date_col2 = st.columns(2)
        start_date_f = date_col1.date_input(
            "Campaign Start Date",
            value=default_start_date,
            min_value=earliest_forecast_date,
            max_value=latest_forecast_date,
            key="feas_sd",
        )
        end_max_date = min(start_date_f + timedelta(days=29), latest_forecast_date)
        end_default_date = min(max(default_end_date, start_date_f), end_max_date)
        # If the start date moves earlier, keep the stored end date inside the
        # newly valid range before rendering the end-date widget.
        stored_end_date = st.session_state.get("feas_ed")
        if stored_end_date is not None and not (start_date_f <= stored_end_date <= end_max_date):
            st.session_state["feas_ed"] = end_default_date
        end_date_f = date_col2.date_input(
            "Campaign End Date",
            value=end_default_date,
            min_value=start_date_f,
            max_value=end_max_date,
            key="feas_ed",
        )
        st.caption(
            f"Forecastable date range: {earliest_forecast_date:%d %b %Y} to "
            f"{latest_forecast_date:%d %b %Y}. Campaign duration: maximum 30 days."
        )
        budget_limit_f = st.number_input("Budget Limit ($)", min_value=0.0, value=10000.0, step=500.0, key="feas_bl")
        uplift_pct_f = st.slider("Assumed Uplift %", 0, 100, 20, key="feas_up")

        if st.button("Run Feasibility Check"):
            if end_date_f < start_date_f:
                st.warning("Campaign End Date must be on or after Campaign Start Date.")
                return

            payload = {
                "campaign_id": campaign_id_f,
                "product_ids": [p.strip() for p in product_ids_f.split(",") if p.strip()],
                "start_date": str(start_date_f),
                "end_date": str(end_date_f),
                "budget_limit": budget_limit_f,
                "assumed_uplift_pct": uplift_pct_f / 100.0,
            }
            try:
                r = httpx.post(f"{API_URL}/campaigns/feasibility", json=payload, headers=headers, timeout=15)
                r.raise_for_status()
                res = r.json()
                # Show verdict prominently
                status = res.get("status", "unknown")
                if status == "feasible_for_review":
                    st.success(f"✅ Feasibility Status: **{status}**")
                else:
                    st.error(f"❌ Feasibility Status: **{status}**")

                # Key checks
                col1, col2 = st.columns(2)
                col1.metric("Budget Validation", res.get("budget_validation", "—"))
                col2.metric("Inventory Validation", res.get("inventory_validation", "—"))

                if res.get("warnings"):
                    with st.expander("⚠️ Warnings"):
                        for w in res["warnings"]:
                            st.markdown(f"- {w}")

                if res.get("rejection_reasons"):
                    with st.expander("🚫 Rejection Reasons"):
                        for r_reason in res["rejection_reasons"]:
                            st.markdown(f"- {r_reason}")

                with st.expander("📄 Full Response"):
                    st.json(res)

            except httpx.HTTPStatusError as e:
                st.error(f"HTTP {e.response.status_code}: {e.response.text}")
            except Exception as e:
                st.error(f"Error: {e}")

    st.divider()

    # ───────────────────── Budget Status ─────────────────────
    with st.expander("💰 Campaign Budget Status (GET /campaigns/{id}/budget)"):
        campaign_id_b = st.text_input("Campaign ID", key="budget_cid")
        if st.button("Get Budget Status"):
            try:
                r = httpx.get(f"{API_URL}/campaigns/{campaign_id_b}/budget", headers=headers, timeout=10)
                r.raise_for_status()
                res = r.json()

                col1, col2, col3 = st.columns(3)
                col1.metric("Budget Limit", f"${res.get('budget_limit', 0):,.2f}")
                col2.metric("Projected Cost", f"${res.get('total_projected_cost', 0):,.2f}")
                col3.metric("Remaining", f"${res.get('budget_remaining', 0):,.2f}")

                st.caption(f"Validation Status: **{res.get('budget_validation_status', '—')}**")

                if res.get("cost_breakdown"):
                    with st.expander("📊 Cost Breakdown"):
                        st.json(res["cost_breakdown"])
            except httpx.HTTPStatusError as e:
                st.error(f"HTTP {e.response.status_code}: {e.response.text}")
            except Exception as e:
                st.error(f"Error: {e}")
