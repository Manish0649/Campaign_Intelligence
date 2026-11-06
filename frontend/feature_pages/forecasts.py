import streamlit as st
import httpx
import os
import pandas as pd
from datetime import date, timedelta

API_URL = os.getenv("API_URL", "http://localhost:8000")


def _render_forecast_result(item: dict):
    """Render metrics + an interactive line chart for a forecast response."""
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Forecast Units", f"{item.get('total_forecast_units', 0):,.2f}")
    col2.metric("Model", item.get("model", "—"))
    col3.metric("Horizon (days)", item.get("horizon_days", "—"))

    daily = item.get("daily_forecasts", [])
    if daily:
        df_chart = pd.DataFrame(daily).rename(
            columns={"date": "Date", "forecast_units": "Forecast Units"}
        )
        df_chart["Date"] = pd.to_datetime(df_chart["Date"])
        df_chart = df_chart.set_index("Date")
        st.line_chart(df_chart["Forecast Units"])
        st.caption("📊 On-demand linear-regression predictions using historical demand, date seasonality and lag features.")

        with st.expander("📋 Daily Breakdown Table"):
            st.dataframe(
                df_chart.reset_index().style.format({"Forecast Units": "{:.2f}"}),
                use_container_width=True,
            )
    else:
        st.info("No daily forecast data returned.")

    with st.expander("📄 Full API Response"):
        st.json(item)


def show_forecasts(token: str):
    """Forecast UI backed by on-demand historical-demand regression."""
    headers = {"Authorization": f"Bearer {token}"}
    st.subheader("📈 Demand Forecasting")

    st.info(
        "Choose your own forecast start date and horizon. Forecasts are generated on demand "
        "from historical sales using calendar seasonality, lag demand and rolling averages; "
        "they are not restricted to the dates stored in the historical database."
    )

    # ── Demand Forecasts (POST) ──────────────────────────────────────────
    with st.expander("📦 Generate Demand Forecasts (POST /forecasts/demand)", expanded=True):
        st.caption("Generate forecasts for one or more products at once.")

        product_ids_input = st.text_input(
            "Product IDs (comma‑separated)",
            value="FOODS_1_018,FOODS_1_019",
            key="fc_pids",
        )
        col1, col2, col3 = st.columns(3)
        start_date = col1.date_input("Forecast Start Date", value=date.today() + timedelta(days=1), key="fc_sd")
        horizon = col2.number_input("Horizon (days)", min_value=1, max_value=30, value=7, key="fc_hor")
        col3.text_input("Forecasting Model", value="linear_regression", disabled=True, key="fc_model")

        if st.button("Generate Forecasts", key="btn_gen_fc"):
            pids = [p.strip() for p in product_ids_input.split(",") if p.strip()]
            if not pids:
                st.warning("Please enter at least one Product ID.")
            else:
                payload = {
                    "product_ids": pids,
                    "start_date": str(start_date),
                    "horizon_days": int(horizon),
                    "model": "linear_regression",
                }
                with st.spinner("Generating forecasts…"):
                    try:
                        r = httpx.post(
                            f"{API_URL}/forecasts/demand",
                            json=payload,
                            headers=headers,
                            timeout=15,
                        )
                        r.raise_for_status()
                        results = r.json()
                        st.success(f"Forecasts generated for **{len(results)}** product(s)")
                        for item in results:
                            st.markdown(f"### Product: `{item.get('product_id', '—')}`")
                            _render_forecast_result(item)
                            st.divider()
                    except httpx.HTTPStatusError as e:
                        st.error(f"HTTP {e.response.status_code}: {e.response.text}")
                    except Exception as e:
                        st.error(f"Error: {e}")

    # ── Single Product Forecast (GET) ─────────────────────────────────
    with st.expander("🔎 Single Product Forecast (GET /products/{id}/forecast)"):
        st.caption("Retrieve a forecast for one specific product over a custom horizon.")

        col1, col2, col3 = st.columns(3)
        pid = col1.text_input("Product ID", value="FOODS_1_018", key="single_pid")
        horizon_s = col2.slider("Horizon (days)", 1, 7, 7, key="single_hor")
        col3.text_input("Model", value="linear_regression", disabled=True, key="single_model")
        single_start_date = st.date_input("Forecast Start Date", value=date.today() + timedelta(days=1), key="single_sd")

        if st.button("Get Forecast", key="btn_get_fc"):
            if not pid.strip():
                st.warning("Please enter a Product ID.")
            else:
                with st.spinner("Fetching forecast…"):
                    try:
                        r = httpx.get(
                            f"{API_URL}/products/{pid.strip()}/forecast",
                            params={"start_date": str(single_start_date), "horizon_days": horizon_s},
                            headers=headers,
                            timeout=15,
                        )
                        r.raise_for_status()
                        item = r.json()
                        st.markdown(f"### Product: `{item.get('product_id', '—')}`")
                        _render_forecast_result(item)
                    except httpx.HTTPStatusError as e:
                        st.error(f"HTTP {e.response.status_code}: {e.response.text}")
                    except Exception as e:
                        st.error(f"Error: {e}")

    # ── Campaign Uplift Forecast ───────────────────────────────────────
    with st.expander("🚀 Campaign Uplift Forecast (auto-computed from baseline)"):
        st.caption(
            "Shows the **baseline** forecast vs. the **campaign uplift** forecast side‑by‑side. "
            "Uplift is derived automatically from the campaign's discount rate — no manual entry needed."
        )

        col1, col2 = st.columns(2)
        camp_pid = col1.text_input("Product ID", value="FOODS_1_018", key="uplift_pid")
        discount_rate = col2.slider(
            "Campaign Discount Rate (%)",
            min_value=5,
            max_value=50,
            value=15,
            step=5,
            key="disc_rate",
            help="Uplift is computed as: baseline × (1 + discount_rate × 1.5)",
        )
        col3, col4 = st.columns(2)
        uplift_horizon = col3.slider("Horizon (days)", 1, 7, 7, key="uplift_hor")
        col4.text_input("Model", value="linear_regression", disabled=True, key="uplift_model")
        camp_start = st.date_input("Campaign Start Date", value=date.today() + timedelta(days=1), key="uplift_sd")

        if st.button("Compute Uplift Forecast", key="btn_uplift"):
            with st.spinner("Computing baseline and uplift forecasts…"):
                try:
                    r = httpx.get(
                        f"{API_URL}/products/{camp_pid.strip()}/forecast",
                        params={"start_date": str(camp_start), "horizon_days": uplift_horizon},
                        headers=headers,
                        timeout=15,
                    )
                    r.raise_for_status()
                    baseline_resp = r.json()
                    daily = baseline_resp.get("daily_forecasts", [])

                    if not daily:
                        st.warning("No forecast data returned.")
                    else:
                        disc = discount_rate / 100.0
                        uplift_mult = 1.0 + disc * 1.5  # auto-computed uplift factor

                        df_base = pd.DataFrame(daily).rename(
                            columns={"date": "Date", "forecast_units": "Baseline Units"}
                        )
                        df_base["Date"] = pd.to_datetime(df_base["Date"])

                        df_base["Uplift Units"] = (df_base["Baseline Units"] * uplift_mult).round(2)
                        df_base["Uplift Factor"] = f"{uplift_mult:.2f}×"

                        col1, col2, col3 = st.columns(3)
                        col1.metric("Baseline Total", f"{df_base['Baseline Units'].sum():,.2f} units")
                        col2.metric(
                            "With Campaign Uplift",
                            f"{df_base['Uplift Units'].sum():,.2f} units",
                        )
                        col3.metric(
                            "Auto Uplift Factor",
                            f"{uplift_mult:.2f}×",
                            help=f"Computed as 1 + {discount_rate}% × 1.5",
                        )

                        chart_df = df_base.set_index("Date")[["Baseline Units", "Uplift Units"]]
                        st.line_chart(chart_df)
                        st.caption(
                            f"🔵 Baseline | 🟠 With campaign uplift "
                            f"(auto-computed: discount {discount_rate}% → {uplift_mult:.2f}× multiplier)"
                        )

                        with st.expander("📋 Daily Comparison Table"):
                            st.dataframe(
                                df_base[["Date", "Baseline Units", "Uplift Units"]].style.format(
                                    {"Baseline Units": "{:.2f}", "Uplift Units": "{:.2f}"}
                                ),
                                use_container_width=True,
                            )

                except httpx.HTTPStatusError as e:
                    st.error(f"HTTP {e.response.status_code}: {e.response.text}")
                except Exception as e:
                    st.error(f"Error: {e}")
