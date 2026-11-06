# Campaign Intelligence — Streamlit Admin UI

## Prerequisites

- Python 3.10+
- Backend API running (`uvicorn backend.app.main:app --reload`)
- Project-root `.env` configured; see the root `README.md` and `.env.example`.

## Setup (PowerShell)

```powershell
# From the project root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
pip install -r frontend/requirements.txt
```

## Run

From the project root:

```powershell
streamlit run frontend/app.py
```

The app reads `API_URL` from the project-root `.env` and sends the signed JWT obtained from `/auth/login` with protected API requests. Approval roles and user IDs are not selected in the browser; the API derives them from the token.

## Pages

- Health Check
- Forecasts
- Feasibility Engine
- Proposals (HITL) — create, inspect, approve/reject, activate and view persisted audit history
- Decision Layer
- Orchestrated Planning
- Policy Knowledge Base — semantic search over indexed Markdown policies in Zilliz
