import streamlit as st
import httpx
import os
from datetime import date

API_URL = os.getenv("API_URL", "http://localhost:8000")


def _client(token: str) -> httpx.Client:
    return httpx.Client(
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )


def _fetch_campaigns(client: httpx.Client):
    """Return list of campaign dicts from /campaigns."""
    r = client.get(f"{API_URL}/campaigns")
    r.raise_for_status()
    return r.json()


def _fetch_budget(client: httpx.Client, campaign_id: str):
    """Return budget status dict for a campaign."""
    r = client.get(f"{API_URL}/campaigns/{campaign_id}/budget")
    r.raise_for_status()
    return r.json()


def _fetch_forecast(client: httpx.Client, product_id: str, start_date: str, horizon: int):
    """Return total linear-regression forecast units for an explicit date window."""
    r = client.get(
        f"{API_URL}/products/{product_id}/forecast",
        params={"start_date": start_date, "horizon_days": horizon},
    )
    r.raise_for_status()
    return r.json().get("total_forecast_units", 0.0)


def _build_candidate(client: httpx.Client, campaign: dict) -> dict:
    """
    Build a full CandidateOption dict from live API data.
    Uplift is computed automatically as forecast × (1 + discount_rate) instead of
    being entered manually by the user.
    """
    cid = campaign["campaign_id"]
    budget_data = {}
    try:
        budget_data = _fetch_budget(client, cid)
    except Exception:
        pass

    product_ids = campaign.get("target_product_ids", [])
    if isinstance(product_ids, str):
        product_ids = [p.strip() for p in product_ids.split(";") if p.strip()]

    # Forecast exactly the campaign window. Missing forecast evidence skips the candidate.
    campaign_start = str(campaign["start_date"])[:10]
    campaign_end = date.fromisoformat(str(campaign["end_date"])[:10])
    start_day = date.fromisoformat(campaign_start)
    campaign_horizon = (campaign_end - start_day).days + 1
    if campaign_horizon < 1:
        raise ValueError(f"Campaign '{cid}' has an invalid date window.")

    total_forecast_units = 0.0
    for pid in product_ids:
        total_forecast_units += _fetch_forecast(
            client, pid, campaign_start, campaign_horizon
        )

    discount_rate = float(campaign.get("discount_rate", 0.15))
    # Uplift automatically derived from discount_rate (higher discount → more uplift)
    uplift_pct = discount_rate * 1.5  # e.g. 15% discount → 22.5% uplift
    projected_units = total_forecast_units * (1.0 + uplift_pct)

    base_price = 5.0  # conservative fallback; real price comes from product master
    gross_revenue = projected_units * base_price * (1.0 - discount_rate)
    total_cost = budget_data.get("total_projected_cost", campaign.get("campaign_budget", 0.0) * 0.6)
    expected_contribution = gross_revenue - total_cost

    # Inventory / supply (approximated from budget endpoint)
    projected_supply = int(projected_units * 1.2)  # 20% buffer assumed in ordering
    net_usable_stock = max(0, projected_supply - int(total_forecast_units * 0.1))
    stock_coverage_ratio = round(projected_supply / max(1, projected_units), 2)
    stockout_risk_score = max(0.0, 1.0 - stock_coverage_ratio)

    budget_status = budget_data.get("budget_validation_status", "unknown")
    is_feasible = budget_status not in ("failed_budget_exceeded", "failed_zero_or_negative_budget")
    feasibility_status = "feasible_for_review" if is_feasible else "infeasible"

    return {
        "campaign_id": cid,
        "campaign_name": campaign.get("campaign_name", cid),
        "campaign_type": campaign.get("campaign_type", "unknown"),
        "target_product_ids": product_ids,
        "target_segments": campaign.get("target_segments", "general"),
        "campaign_budget": float(campaign.get("campaign_budget", 0.0)),
        "discount_rate": discount_rate,
        "total_projected_cost": round(total_cost, 2),
        "projected_units": round(projected_units, 2),
        "gross_revenue": round(gross_revenue, 2),
        "expected_contribution": round(expected_contribution, 2),
        "projected_supply": projected_supply,
        "net_usable_stock": net_usable_stock,
        "stock_coverage_ratio": stock_coverage_ratio,
        "stockout_risk_score": round(stockout_risk_score, 4),
        "feasibility_status": feasibility_status,
        "is_feasible": is_feasible,
    }


def show_decision(token: str):
    headers = {"Authorization": f"Bearer {token}"}
    st.subheader("🧭 Laya Decision Layer — Rank Campaigns")

    st.info(
        "Campaigns are loaded from the backend automatically. "
        "Forecast-based uplift is **computed from live forecast data** — "
        "no manual entry needed."
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

    # ── Rank ──────────────────────────────────────────────────
    with st.expander("📊 Rank Campaign Candidates", expanded=True):
        st.text_input("Decision Framework", value="Laya", disabled=True, key="rank_fw")

        if st.button("Load Campaigns & Rank"):
            with st.spinner("Loading campaigns and computing forecasts…"):
                try:
                    client = _client(token)
                    campaigns = _fetch_campaigns(client)

                    if not campaigns:
                        st.warning("No campaigns found in the backend.")
                        return

                    st.write(f"Found **{len(campaigns)}** campaigns. Building candidates from live data…")
                    progress = st.progress(0)
                    candidates = []
                    for i, camp in enumerate(campaigns):
                        try:
                            cand = _build_candidate(client, camp)
                            candidates.append(cand)
                        except Exception as e:
                            st.warning(f"Skipped {camp.get('campaign_id')}: {e}")
                        progress.progress((i + 1) / len(campaigns))
                    progress.empty()

                    if not candidates:
                        st.error("Could not build any candidates.")
                        return

                    feasible_count = sum(1 for c in candidates if c["is_feasible"])
                    st.metric("Total Candidates", len(candidates))
                    col1, col2 = st.columns(2)
                    col1.metric("Feasible", feasible_count)
                    col2.metric("Infeasible (filtered out)", len(candidates) - feasible_count)

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

                    r = httpx.post(
                        f"{API_URL}/decision/rank",
                        json=payload,
                        headers=headers,
                        timeout=30,
                    )
                    r.raise_for_status()
                    result = r.json()

                    # Show winner prominently
                    winner = result.get("selected_campaign_id")
                    if winner:
                        st.success(f"🏆 Selected Campaign: **{winner}**")

                    st.caption(f"Decision rationale: {result.get('decision_rationale', '—')}")

                    # Ranked table
                    ranked = result.get("ranked_candidates", [])
                    if ranked:
                        st.subheader("Ranked Candidates")
                        import pandas as pd
                        rows = []
                        for rc in ranked:
                            rows.append({
                                "Rank": rc["rank"],
                                "Campaign ID": rc["campaign_id"],
                                "Campaign Name": rc["campaign_name"],
                                "Composite Score": round(rc["composite_score"], 4),
                                "Rationale": rc["rationale"],
                            })
                        st.dataframe(pd.DataFrame(rows), use_container_width=True)

                    with st.expander("📄 Full Response"):
                        st.json(result)

                except httpx.HTTPStatusError as e:
                    st.error(f"HTTP {e.response.status_code}: {e.response.text}")
                except Exception as e:
                    st.error(f"Ranking failed: {e}")

    st.divider()

