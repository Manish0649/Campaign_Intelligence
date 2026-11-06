import os

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")


def show_proposals(token: str, role: str | None = None):
    headers = {"Authorization": f"Bearer {token}"}
    is_submitter = role == "PROPOSAL-SUBMITTER"
    st.subheader("🗂️ Proposals — Human-In-The-Loop (HITL)")
    if is_submitter:
        st.info("Your account can submit proposals. Authorized reviewers/admins handle approval and activation.")

    proposal_rows = []
    try:
        list_response = httpx.get(
            f"{API_URL}/campaigns/proposals",
            headers=headers,
            timeout=15,
        )
        list_response.raise_for_status()
        proposal_rows = list_response.json().get("proposals", [])
    except httpx.HTTPError as exc:
        st.warning(f"Could not load proposal list: {exc}")

    if proposal_rows:
        st.markdown("### Proposal Queue" if not is_submitter else "### My Submitted Proposals")
        st.dataframe(proposal_rows, use_container_width=True, hide_index=True)
    else:
        st.caption("No proposals are currently available for this account.")

    pending_ids = [
        item["proposal_id"] for item in proposal_rows
        if item.get("approval_status") == "pending_review"
    ]

    with st.expander("➕ Create New Proposal", expanded=True):
        campaign_id = st.text_input("Campaign ID", key="prop_cid")
        forecast_version = st.text_input("Forecast Version", value="m5-dynamic-linear-v2", key="prop_fv")
        selected_option_id = st.text_input("Selected Option ID (optional)", key="prop_soid")
        if st.button("Create Proposal"):
            payload = {
                "campaign_id": campaign_id,
                "forecast_version": forecast_version,
                "selected_option_id": selected_option_id or "OPT-1-STANDARD",
            }
            try:
                response = httpx.post(
                    f"{API_URL}/campaigns/proposals",
                    json=payload,
                    headers=headers,
                    timeout=20,
                )
                response.raise_for_status()
                st.success("Proposal submitted for review.")
                st.json(response.json())
            except httpx.HTTPStatusError as exc:
                st.error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            except httpx.HTTPError as exc:
                st.error(f"Could not submit proposal: {exc}")

    with st.expander("🔍 Fetch Proposal by ID"):
        proposal_id = st.text_input("Proposal ID", key="prop_lookup")
        if st.button("Fetch Proposal"):
            try:
                response = httpx.get(
                    f"{API_URL}/campaigns/proposals/{proposal_id}",
                    headers=headers,
                    timeout=10,
                )
                response.raise_for_status()
                st.json(response.json())
            except httpx.HTTPStatusError as exc:
                st.error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            except httpx.HTTPError as exc:
                st.error(f"Could not fetch proposal: {exc}")

    with st.expander("🧾 Proposal Audit History"):
        audit_id = st.text_input("Proposal ID for audit history", key="audit_pid")
        if st.button("Load Audit History"):
            try:
                response = httpx.get(
                    f"{API_URL}/campaigns/proposals/{audit_id}/audit",
                    headers=headers,
                    timeout=10,
                )
                response.raise_for_status()
                events = response.json().get("events", [])
                if not events:
                    st.info("No lifecycle events recorded.")
                for event in events:
                    st.markdown(
                        f"**{event['event_type']}** · {event['actor_id']} "
                        f"({event['actor_role']}) · {event['created_at']}"
                    )
                    if event.get("details"):
                        st.json(event["details"])
            except httpx.HTTPStatusError as exc:
                st.error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            except httpx.HTTPError as exc:
                st.error(f"Could not load audit history: {exc}")

    if not is_submitter:
        with st.expander("✅ Approve / Reject Proposal"):
            st.caption(
                "Role spending limits: MGR-MKT $7,500 | MGR-STORE $10,000 | "
                "MGR-INV $20,000 | APPR-FIN $50,000 | DIR-MKT $100,000 | "
                "EXEC-DIR $250,000 | SYS-ADMIN $1,000,000"
            )
            if pending_ids:
                approval_id = st.selectbox("Pending proposal to review", pending_ids, key="appr_pid")
            else:
                approval_id = st.text_input("Proposal ID to Approve/Reject", key="appr_pid")
                st.caption("No pending proposals were found in the queue; you can enter an ID manually.")
            st.caption("Identity and spending authority come from your signed login token.")
            comments = st.text_area("Review comments (optional)", max_chars=2000, key="approval_comments")
            action = st.radio("Action", ["approve", "reject"], horizontal=True, key="appr_action")
            if st.button("Submit Decision"):
                try:
                    response = httpx.post(
                        f"{API_URL}/campaigns/proposals/{approval_id}/approval",
                        json={"action": action, "comments": comments or None},
                        headers=headers,
                        timeout=20,
                    )
                    response.raise_for_status()
                    st.success(f"Decision submitted: {action.upper()}")
                    st.json(response.json())
                except httpx.HTTPStatusError as exc:
                    st.error(f"HTTP {exc.response.status_code}: {exc.response.text}")
                except httpx.HTTPError as exc:
                    st.error(f"Could not submit decision: {exc}")

        with st.expander("🚀 Activate Approved Proposal"):
            activation_id = st.text_input("Proposal ID to Activate", key="act_pid")
            channel = st.selectbox("Activation Channel", ["email", "sms", "push", "in-app"], key="act_channel")
            if st.button("Activate Proposal"):
                try:
                    response = httpx.post(
                        f"{API_URL}/campaigns/proposals/{activation_id}/activation",
                        json={"channel": channel},
                        headers=headers,
                        timeout=20,
                    )
                    response.raise_for_status()
                    st.success("Proposal activated.")
                    st.json(response.json())
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 409:
                        st.warning("Duplicate activation request blocked.")
                    elif exc.response.status_code == 403:
                        st.error("Unauthorized: proposal must be approved and you must have activation permission.")
                    else:
                        st.error(f"HTTP {exc.response.status_code}: {exc.response.text}")
                except httpx.HTTPError as exc:
                    st.error(f"Could not activate proposal: {exc}")
