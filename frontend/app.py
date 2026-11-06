import sys, os

# Ensure the frontend folder is on the path so feature_pages imports work
sys.path.insert(0, os.path.dirname(__file__))

from pathlib import Path
from dotenv import load_dotenv

# Load project-root .env (holds API_URL, admin credentials, JWT settings)
load_dotenv(Path(__file__).parent.parent / ".env")

import streamlit as st
from feature_pages import auth, health, forecasts, feasibility, proposals, decision, orchestrate, knowledge_base

# ──────────────────────────────────────────────────────────
# Page config (must be first Streamlit call)
st.set_page_config(
    page_title="Campaign Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
    /* =========================================
       GLOBAL DARK THEME
    ========================================= */

    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"] {
        background-color: #0B1120 !important;
        color: #E2E8F0 !important;
    }

    [data-testid="stHeader"] {
        background-color: #0B1120 !important;
    }

    .main .block-container {
        background-color: #0B1120 !important;
        color: #E2E8F0 !important;
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    /* =========================================
       TYPOGRAPHY
    ========================================= */

    .stApp h1,
    .stApp h2,
    .stApp h3,
    .stApp h4,
    .stApp p,
    .stApp label,
    .stApp span,
    .stApp [data-testid="stMarkdownContainer"] {
        color: #E2E8F0;
    }

    .stApp [data-testid="stCaptionContainer"] {
        color: #94A3B8 !important;
    }

    /* =========================================
       SIDEBAR
    ========================================= */

    [data-testid="stSidebar"] {
        background-color: #111C30 !important;
        border-right: 1px solid #263449;
    }

    [data-testid="stSidebar"] * {
        color: #E2E8F0 !important;
    }

    [data-testid="stSidebar"] [data-testid="stRadio"] label {
        padding: .55rem .65rem;
        border-radius: .55rem;
    }

    /* =========================================
       INPUTS
    ========================================= */

    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stDateInput"] input,
    [data-testid="stTextArea"] textarea {
        background-color: #1E293B !important;
        color: #F1F5F9 !important;
        border: 1px solid #334155 !important;
        border-radius: .55rem !important;
        caret-color: #60A5FA;
    }

    [data-testid="stTextInput"] input::placeholder,
    [data-testid="stTextArea"] textarea::placeholder {
        color: #94A3B8 !important;
    }

    [data-testid="stSelectbox"] div[data-baseweb="select"],
    [data-testid="stMultiSelect"] div[data-baseweb="select"] {
        background-color: #1E293B !important;
        color: #F1F5F9 !important;
        border-radius: .55rem !important;
    }

    /* =========================================
       BUTTONS
    ========================================= */

    .stButton > button,
    .stFormSubmitButton > button {
        background-color: #2563EB !important;
        color: #FFFFFF !important;
        border: 1px solid #3B82F6 !important;
        border-radius: .65rem !important;
        font-weight: 600;
        min-height: 2.55rem;
        transition: all .2s ease;
    }

    .stButton > button:hover,
    .stFormSubmitButton > button:hover {
        background-color: #1D4ED8 !important;
        border-color: #60A5FA !important;
    }

    /* =========================================
       METRICS / CARDS
    ========================================= */

    [data-testid="stMetric"] {
        background-color: #111C30 !important;
        border: 1px solid #263449 !important;
        padding: 1rem;
        border-radius: .85rem;
        box-shadow: 0 3px 12px rgba(0, 0, 0, .15);
    }

    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"],
    [data-testid="stMetricDelta"] {
        color: #E2E8F0 !important;
    }

    [data-testid="stExpander"] {
        background-color: #111C30 !important;
        border: 1px solid #263449 !important;
        border-radius: .8rem !important;
    }

    /* =========================================
       DATAFRAMES AND TABLES
    ========================================= */

    [data-testid="stDataFrame"],
    [data-testid="stTable"] {
        background-color: #111C30 !important;
        border: 1px solid #263449 !important;
        border-radius: .7rem;
    }

    /* =========================================
       ALERTS AND STATUS MESSAGES
    ========================================= */

    [data-testid="stAlert"] {
        border-radius: .7rem !important;
    }

    /* =========================================
       DIVIDERS
    ========================================= */

    hr {
        border-color: #263449 !important;
    }

    /* =========================================
       GENERAL POLISH
    ========================================= */

    h1, h2, h3 {
        letter-spacing: -.02em;
    }

    ::selection {
        background-color: #2563EB;
        color: #FFFFFF;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────────────────
# Session State
if "jwt" not in st.session_state:
    st.session_state.jwt = None
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False


def do_login():
    token = auth.login(st.session_state["login_email"], st.session_state["login_password"])
    if token:
        st.session_state.jwt = token
        st.session_state.role = auth.role_from_token(token)
        st.session_state.logged_in = True
    else:
        st.session_state._login_error = True


# ──────────────────────────────────────────────────────────
# Login Wall
if not st.session_state.logged_in:
    # Centered login card via columns
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("## 🔐 Campaign Intelligence — Sign In")
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.button("Login", on_click=do_login, use_container_width=True)
        if st.session_state.get("_login_error"):
            st.error("❌ Invalid credentials. Check your email and password.")
            st.session_state._login_error = False
    st.stop()

# ──────────────────────────────────────────────────────────
# Sidebar — Navigation
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/combo-chart.png", width=64)
    st.title("Campaign Intelligence")
    st.caption(f"Signed in · {st.session_state.get('role', 'User')}")
    st.divider()

    role = st.session_state.get("role")
    if role == "PROPOSAL-SUBMITTER":
        page_options = ["🗂️ Proposals (HITL)", "🩺 Health Check"]
    else:
        page_options = [
            "🩺 Health Check",
            "📈 Forecasts",
            "🔧 Feasibility Engine",
            "🗂️ Proposals (HITL)",
            "🧭 Decision Layer",
            "🚀 Orchestrated Planning",
            "📚 Policy Knowledge Base",
        ]
    page = st.radio(
        "Navigate to",
        page_options,
        label_visibility="collapsed",
    )

    st.divider()
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.jwt = None
        st.session_state.role = None
        st.session_state.logged_in = False
        st.rerun()

# ──────────────────────────────────────────────────────────
# Page Router
token = st.session_state.jwt

if page == "🩺 Health Check":
    health.show_health(token, st.session_state.get("role"))

elif page == "📈 Forecasts":
    forecasts.show_forecasts(token)

elif page == "🔧 Feasibility Engine":
    feasibility.show_feasibility(token)

elif page == "🗂️ Proposals (HITL)":
    proposals.show_proposals(token, st.session_state.get("role"))

elif page == "🧭 Decision Layer":
    decision.show_decision(token)

elif page == "🚀 Orchestrated Planning":
    orchestrate.show_orchestrate(token)

elif page == "📚 Policy Knowledge Base":
    knowledge_base.show_knowledge_base(token)
