import streamlit as st
import httpx
import os

API_URL = os.getenv("API_URL", "http://localhost:8000")


def show_orchestrate(token: str):
    headers = {"Authorization": f"Bearer {token}"}
    st.subheader("🚀 Orchestrated Campaign Planning — LangGraph Workflow")

    st.info(
        "This runs the **full end‑to‑end LangGraph planning pipeline**:\n\n"
        "1. **Candidate Preparation + Feasibility** → 2. **Laya Decision Ranking** → "
        "3. **Proposal Persistence**"
    )

    with st.form("orchestrate_form"):
        campaign_ids_input = st.text_input(
            "Campaign IDs (comma‑separated, leave blank for all)",
            placeholder="CAMP-001, CAMP-002",
        )
        st.text_input("Decision Framework", value="Laya", disabled=True)
        uplift_pct = st.slider("Assumed Uplift %", min_value=0, max_value=200, value=20, step=5)
        submitted = st.form_submit_button("Run Full Orchestration")

    if submitted:
        ids = [c.strip() for c in campaign_ids_input.split(",") if c.strip()] or None
        payload = {
            "campaign_ids": ids,
            "decision_framework": "laya",
            "assumed_uplift_pct": uplift_pct / 100.0,
        }
        with st.spinner("Running LangGraph orchestration… this may take a few seconds."):
            try:
                r = httpx.post(
                    f"{API_URL}/decision/orchestrate",
                    json=payload,
                    headers=headers,
                    timeout=60,
                )
                r.raise_for_status()
                result = r.json()

                # Summary metrics
                col1, col2, col3 = st.columns(3)
                col1.metric("Status", result.get("status", "—").upper())
                col2.metric("Feasible Candidates", result.get("feasible_options_count", 0))
                col3.metric("Infeasible Candidates", result.get("infeasible_options_count", 0))

                if result.get("selected_campaign"):
                    st.success(f"✅ Selected Campaign: **{result['selected_campaign']}**")

                if result.get("current_step"):
                    st.caption(f"Last step completed: `{result['current_step']}`")

                # Generated proposal details
                if result.get("generated_proposal"):
                    with st.expander("📋 Generated Proposal"):
                        st.json(result["generated_proposal"])

                # Decision result details
                if result.get("decision_result"):
                    with st.expander("🧭 Decision Result"):
                        st.json(result["decision_result"])

                # Audit log
                if result.get("audit_log"):
                    with st.expander("📜 Audit Log"):
                        for entry in result["audit_log"]:
                            st.markdown(f"- {entry}")

            except httpx.HTTPStatusError as e:
                st.error(f"HTTP {e.response.status_code}: {e.response.text}")
            except Exception as e:
                st.error(f"Orchestration failed: {e}")

