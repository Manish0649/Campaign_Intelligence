
"""Knowledge Base UI: conversational RAG assistant and semantic document search."""

import os

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

# These values match the policy categories indexed in the knowledge base.
CATEGORIES = [
    "campaign_planning_policy",
    "campaign_playbooks_and_scenario_guidelines",
    "decision_system_and_approval_hierarchy",
    "inventory_and_safety_stock_rules",
    "supplier_replenishment_and_lead_time_protocols",
]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _render_sources(sources: list[dict], key_prefix: str) -> None:
    """Render the source metadata returned by the RAG API."""
    if not sources:
        return

    with st.expander(f"📚 Sources used ({len(sources)})", expanded=False):
        for index, source in enumerate(sources, start=1):
            title = source.get("section_title") or source.get("doc_name") or f"Source {index}"
            doc_name = source.get("doc_name") or "Unknown document"
            category = source.get("category") or "Uncategorized"
            score = source.get("similarity_score")

            st.markdown(f"**{index}. {title}**")
            st.caption(f"{doc_name} · {category}")

            if score is not None:
                st.caption(f"Retrieval score: {float(score):.4f}")

            if index < len(sources):
                st.divider()


def _render_chat_message(message: dict, index: int) -> None:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        if message["role"] == "assistant":
            _render_sources(message.get("sources", []), f"history_{index}")


def _show_assistant(token: str) -> None:
    st.markdown("### 💬 Knowledge Assistant")

    st.caption(
        "Ask questions about campaign policies, inventory constraints, "
        "safety stock, supplier protocols and approval rules. Answers are "
        "grounded in the documents indexed in Zilliz."
    )

    controls_col1, controls_col2 = st.columns([1, 2])

    with controls_col1:
        top_k = st.select_slider(
            "Context passages",
            options=[2, 3, 4, 5, 6, 8, 10],
            value=4,
            help="Number of relevant knowledge-base chunks sent to the answer generator.",
            key="kb_chat_top_k",
        )

    with controls_col2:
        category_choice = st.selectbox(
            "Knowledge category",
            options=["All categories"] + CATEGORIES,
            format_func=lambda value: value.replace("_", " ").title()
            if value != "All categories"
            else value,
            help="Optionally restrict retrieval to one policy category.",
            key="kb_chat_category",
        )

    if "kb_chat_history" not in st.session_state:
        st.session_state.kb_chat_history = []

    history = st.session_state.kb_chat_history

    if history:
        for index, message in enumerate(history):
            _render_chat_message(message, index)
    else:
        st.info(
            "Start a conversation by asking a question below. "
            "For example: **What happens when inventory data is older than 72 hours?**"
        )

    prompt = st.chat_input(
        "Ask a question about Campaign Intelligence policies...",
        max_chars=2000,
        key="kb_chat_prompt",
    )

    if prompt:
        clean_prompt = prompt.strip()

        if len(clean_prompt) < 3:
            st.warning("Please enter at least 3 characters.")
            return

        request_body = {
            "query": clean_prompt,
            "top_k": top_k,
            "category": None if category_choice == "All categories" else category_choice,
        }

        with st.chat_message("user"):
            st.markdown(clean_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Searching the knowledge base and preparing an answer..."):
                try:
                    response = httpx.post(
                        f"{API_URL}/knowledge-base/ask",
                        json=request_body,
                        headers=_auth_headers(token),
                        timeout=90,
                    )

                    response.raise_for_status()

                    payload = response.json()

                    answer = payload.get("answer") or (
                        "I couldn't generate an answer from the available knowledge-base context."
                    )

                    sources = payload.get("sources", [])

                    st.markdown(answer)
                    _render_sources(sources, "current")

                    history.append(
                        {
                            "role": "user",
                            "content": clean_prompt,
                        }
                    )

                    history.append(
                        {
                            "role": "assistant",
                            "content": answer,
                            "sources": sources,
                        }
                    )

                    st.session_state.kb_chat_history = history

                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code

                    if status_code == 401:
                        error_message = (
                            "Your session may have expired. "
                            "Please log out and sign in again."
                        )

                    elif status_code == 403:
                        error_message = (
                            "Your account is not authorized to use "
                            "the Knowledge Assistant."
                        )

                    else:
                        try:
                            detail = exc.response.json().get(
                                "detail",
                                "The backend returned an error.",
                            )
                        except (ValueError, AttributeError):
                            detail = "The backend returned an error."

                        error_message = (
                            f"Request failed (HTTP {status_code}): {detail}"
                        )

                    st.error(error_message)

                    history.extend(
                        [
                            {"role": "user", "content": clean_prompt},
                            {
                                "role": "assistant",
                                "content": error_message,
                                "sources": [],
                            },
                        ]
                    )

                    st.session_state.kb_chat_history = history

                except httpx.TimeoutException:
                    error_message = (
                        "The request timed out while waiting for an answer. "
                        "Please try again."
                    )

                    st.error(error_message)

                    history.extend(
                        [
                            {"role": "user", "content": clean_prompt},
                            {
                                "role": "assistant",
                                "content": error_message,
                                "sources": [],
                            },
                        ]
                    )

                    st.session_state.kb_chat_history = history

                except httpx.HTTPError:
                    error_message = (
                        f"Cannot reach the backend at {API_URL}. "
                        "Check that the FastAPI server is running."
                    )

                    st.error(error_message)

                    history.extend(
                        [
                            {"role": "user", "content": clean_prompt},
                            {
                                "role": "assistant",
                                "content": error_message,
                                "sources": [],
                            },
                        ]
                    )

                    st.session_state.kb_chat_history = history

        st.rerun()

    if history:
        st.divider()

        if st.button("🗑️ Clear conversation", key="kb_clear_chat"):
            st.session_state.kb_chat_history = []
            st.rerun()


def _show_document_search(token: str) -> None:
    """Keep the original semantic search workflow available."""

    st.markdown("### 🔎 Search Knowledge Base")

    st.caption(
        "Retrieve matching policy passages directly from Zilliz "
        "without generating an answer."
    )

    query = st.text_area(
        "Search indexed documents",
        placeholder="Example: What happens when inventory is below safety stock?",
        key="kb_search_query",
    )

    top_k = st.slider(
        "Number of passages",
        min_value=1,
        max_value=10,
        value=4,
        key="kb_search_top_k",
    )

    if st.button(
        "Search documents",
        type="primary",
        disabled=len(query.strip()) < 3,
        key="kb_search_button",
    ):
        try:
            response = httpx.post(
                f"{API_URL}/knowledge-base/search",
                json={
                    "query": query.strip(),
                    "top_k": top_k,
                },
                headers=_auth_headers(token),
                timeout=30,
            )

            response.raise_for_status()

            payload = response.json()
            results = payload.get("results", [])

            st.success(
                f"Retrieved {payload.get('result_count', len(results))} passages."
            )

            for index, result in enumerate(results, start=1):
                title = (
                    result.get("section_title")
                    or result.get("doc_name")
                    or f"Passage {index}"
                )

                score = result.get("similarity_score")

                score_label = (
                    f" · retrieval score {float(score):.3f}"
                    if score is not None
                    else ""
                )

                with st.expander(
                    f"{index}. {title}{score_label}",
                    expanded=index == 1,
                ):
                    st.caption(
                        f"Source: {result.get('doc_name', 'Unknown')} · "
                        f"Category: {result.get('category', 'Uncategorized')}"
                    )

                    st.markdown(
                        result.get("content")
                        or "_No passage content returned._"
                    )

        except httpx.HTTPStatusError as exc:
            st.error(
                f"Knowledge search failed (HTTP {exc.response.status_code})."
            )

        except httpx.TimeoutException:
            st.error(
                "The document search timed out. Please try again."
            )

        except httpx.HTTPError:
            st.error(
                f"Cannot reach the backend at {API_URL}. Is it running?"
            )


def show_knowledge_base(token: str):
    st.title("📚 Policy Knowledge Base")

    st.caption(
        "Explore Campaign Intelligence policies with retrieval-augmented "
        "answers or search the indexed source documents directly."
    )

    assistant_tab, search_tab = st.tabs(
        ["💬 Ask the Assistant", "🔎 Search Documents"]
    )

    with assistant_tab:
        _show_assistant(token)

    with search_tab:
        _show_document_search(token)
