# Campaign Intelligence

Campaign Intelligence is a retail campaign-planning application combining demand forecasts, deterministic feasibility checks, multi-objective campaign ranking, proposal governance, human approval, and policy retrieval from Zilliz Cloud.

The system is designed around an important boundary: **AI and ranking components may recommend and explain; they cannot approve or activate a campaign.** Deterministic business rules remain authoritative.

## Core capabilities

- **Forecasting:** 7-day M5-based demand forecasts, chronological validation and forecast error reporting.
- **Feasibility engine:** campaign budget, product metadata, inventory, safety stock, supplier status, lead time, MOQ, capacity and replenishment-window checks.
- **Decision layer:** Laya ranking after deterministic feasibility filtering; the deterministic baseline remains only as a safety fallback if Laya fails.
- **Proposal governance:** proposals begin in `pending_review` only when they pass feasibility; rejected proposals cannot be approved or activated. Lifecycle events are persisted in an audit table.
- **Authentication:** signed JWTs carry the authenticated subject and role. Approval/activation handlers ignore caller-claimed authority and use token claims.
- **Knowledge base:** Markdown policies are chunked, embedded with OpenAI embeddings and upserted into Zilliz. A protected API and Streamlit page provide semantic search.
- **Frontend:** Streamlit admin dashboard for health, forecasts, feasibility, proposals, decision ranking, orchestration and policy retrieval.

## Architecture

```text
Streamlit UI
    |
    | Bearer JWT
    v
FastAPI
    |-- Auth (/auth)
    |-- Forecast API ---------------- Forecast CSV repository
    |-- Feasibility API ------------- PostgreSQL / NeonDB
    |-- Proposal + approval API ----- PostgreSQL / NeonDB
    |-- Decision API ---------------- Deterministic filters + rankers
    |-- Orchestration API ----------- LangGraph workflow
    `-- Knowledge Base API --------- OpenAI embeddings -> Zilliz Cloud

PostgreSQL is the source of truth for structured campaign, product, inventory,
supplier, cost and proposal data. Zilliz is used for unstructured policy and
playbook retrieval; it does not replace SQL or make feasibility decisions.
```

## Requirements

- Python 3.10+
- PostgreSQL / NeonDB
- Zilliz Cloud account for semantic policy search
- OpenAI API key for `text-embedding-3-small` embeddings

## Local setup (Windows PowerShell)

### 1. Configure environment

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set your own database URL, a random `JWT_SECRET` (at least 32 characters), login credentials and any Zilliz/OpenAI credentials. Do not upload `.env` or commit it.

For multiple human approvers, configure `AUTH_USERS_JSON` instead of a single admin account. Example:

```env
AUTH_USERS_JSON={"admin@example.com":{"password":"REPLACE_ME","role":"SYS-ADMIN"},"marketing.director@example.com":{"password":"REPLACE_ME","role":"DIR-MKT"},"store.manager@example.com":{"password":"REPLACE_ME","role":"MGR-STORE"},"ops.manager@example.com":{"password":"REPLACE_ME","role":"OPS-MANAGER"}}
```

The role comes from the signed JWT, never from the approval request body. Supported approval roles and spending limits are defined in `backend/app/api/routes/proposals.py`. Activation requires `SYS-ADMIN`, `OPS-MANAGER` or `MGR-STORE`.

For local development without NeonDB, you may set `USE_SQLITE=true` and `ENVIRONMENT=development`; this mode is not allowed in production. The tests always use their isolated in-memory SQLite database.

### 2. Install backend dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 3. Start the API

From the project root:

```powershell
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: `http://127.0.0.1:8000/docs`

`GET /health` (liveness) and `GET /health/ready` (database readiness) are public. Forecast, feasibility, proposal, decision and knowledge-base routes require a valid Bearer token. Obtain a token with `POST /auth/login` using the configured account. Proposal lifecycle history is available from `GET /campaigns/proposals/{proposal_id}/audit`.

### 4. Start the Streamlit frontend

Open a second PowerShell terminal, activate the same virtual environment (or create a separate one), then:

```powershell
pip install -r frontend/requirements.txt
cd frontend
streamlit run app.py
```

The UI opens at `http://localhost:8501`.

## Zilliz knowledge-base setup

1. Configure `ZILLIZ_ENDPOINT`, `ZILLIZ_TOKEN`, `OPENAI_API_KEY`, `EMBEDDING_MODEL` and `EMBEDDING_DIMENSION` in `.env`.
2. From the project root, run:

```powershell
python -m knowledge_base.setup_milvus_zilliz
```

The ingestion pipeline chunks the Markdown files in `knowledge_base/`, generates real semantic embeddings and uses deterministic IDs with `upsert`, so re-running ingestion updates existing chunks rather than appending duplicates.

**Safety:** an existing collection is never dropped automatically. If the collection has an incompatible old schema, back it up and explicitly run:

```powershell
python -m knowledge_base.setup_milvus_zilliz --recreate
```

`--recreate` is destructive and replaces the configured collection. Do not use it against a collection containing data you need to retain.

Semantic retrieval is available through authenticated `POST /knowledge-base/search` and the Streamlit **Policy Knowledge Base** page.

## Forecasting and data pipelines

- Build M5 features: `python scripts/build_m5_features.py`
- Generate and evaluate forecasts: `python scripts/forecasting/forecast_pipeline.py`
- Run processed-table quality checks: `python scripts/data_quality_checks.py`
- Load processed data into NeonDB: review `scripts/load_to_neon.py` and `data/processed/clean_db_ready/schema_neon.sql` before running. Default ingestion uses primary-key upserts and preserves live proposal records. The explicit `--replace-existing` option truncates target tables (and related audit rows via cascade); take a backup before using it.

The feature builder applies lag/rolling windows independently per product and removes warm-up rows without allowing one product's history to flow into another product's features. Forecast reports include MAE, RMSE, WAPE and sMAPE; MAPE is diagnostic only because zero-demand observations make it unstable. See `docs/forecast_validation_report.md` and `docs/current_data_quality_audit.md` for the latest generated results.

## Docker deployment (local container stack)

After configuring `.env`:

```powershell
docker compose build
docker compose up -d
docker compose logs -f backend
```

- API: `http://localhost:8000`
- Streamlit UI: `http://localhost:8501`
- Stop: `docker compose down`

The containers use the external `DATABASE_URL` and optional Zilliz/OpenAI credentials from `.env`; no secrets are copied into the images. The backend health check verifies the API process, not the availability of NeonDB or Zilliz. Verify those external services separately before a production launch.

## Tests

From the project root:

```powershell
pytest -v
pytest --cov=backend.app --cov=scripts --cov-report=term-missing
```

Tests use an isolated in-memory SQLite database and deterministic supplier fixtures. They do not require a live NeonDB or Zilliz connection. The full suite does require the packages listed in `backend/requirements.txt`, including LangGraph and the decision adapter dependency.

## Important business and safety boundaries

- A forecast is an estimate, not proof of incremental campaign lift.
- Assumed uplift is a scenario input, not a measured causal effect.
- Expected contribution is a financial signal, not proof of realized profitability.
- Missing or invalid product, inventory or supplier evidence must not be silently replaced with assumed values.
- Feasibility constraints are deterministic and run before decision ranking.
- A proposal must pass feasibility and receive human approval before activation.
- Approval uses authenticated identity/role and role-specific spending limits; proposal creator and approver must differ, and approver and activator must differ.
- Proposal creation, approval/rejection and activation are recorded in the persistent audit table.
- Activation rechecks inventory and supplier readiness and is guarded against concurrent duplicate activation.
- Zilliz retrieval supplies policy context only; it cannot override structured data or hard business constraints.

## Project layout

```text
backend/             FastAPI app, SQLAlchemy models/repos, domain and decision logic
frontend/            Streamlit admin dashboard
knowledge_base/      Policy Markdown, embedding and Zilliz retrieval/ingestion
scripts/              Data cleaning, feature engineering, forecasting and quality checks
tests/                API, unit, security, forecasting and validation tests
data/                 Processed data, forecasts and local database artifacts
docs/                 Project reports, implementation audit and validation documentation
```

## Credentials and dataset handling

- `.env` is local-only and excluded by `.gitignore`.
- Do not include API keys, database URLs, JWT secrets or passwords in ZIPs or source control.
- Raw Kaggle/third-party datasets are excluded from Git by default; obtain them from their original sources and place them under `data/raw/`.
- Rotate credentials if a populated `.env` or any credential-bearing export has been shared outside its intended environment.
- See `docs/implementation_audit.md` for completed work, validation performed and remaining production hardening.


## Recent platform updates

### Dynamic demand forecasting
The API now generates linear-regression forecasts on demand from `data/processed/m5_processed_features.csv`. Users can select a future start date and a 1–30 day horizon; the API no longer requires the request dates to exist in a pre-generated seven-day forecast CSV. The regression uses calendar, lag and rolling-demand features, blended with recent weekday demand to retain weekly seasonality.

### Laya decision framework
LayaAdapter is the only selectable decision framework. Application-side weighted objective scores rank the candidates, while the installed Laya package provides confidence calibration. OpenJEV and the multi-framework comparison path have been removed. Deterministic feasibility filtering remains mandatory, and the baseline ranker is retained only as an exception safety fallback if the Laya adapter fails.

### Consolidated LangGraph workflow
The orchestration graph has three nodes:
1. Candidate preparation (retrieval + deterministic feasibility evaluation)
2. Laya decision ranking
3. Proposal generation and persistence

### MCP server
Install backend dependencies and run `python -m backend.app.mcp_server` from the project root. The FastMCP stdio server exposes `forecast_product_demand`, `search_campaign_policies`, and `rank_campaign_candidates`. See [MCP_SETUP.md](MCP_SETUP.md) for MCP host configuration and safety boundaries.

### Proposal submitter account
Set `PROPOSAL_USER_EMAIL` and `PROPOSAL_USER_PASSWORD` in your local `.env` to create a second login with the `PROPOSAL-SUBMITTER` role. Choose a unique password of at least 12 characters. This role can submit proposals but cannot approve or activate them. The reviewer/admin account remains responsible for approval.

### Health and tests
The Health Check page reports API, database, LangGraph, Laya, MCP SDK, Gemini configuration and Zilliz connectivity. A `SYS-ADMIN` can run the pytest suite from the page and see passed, failed, error and skipped counts. Pytest runs only when requested.
#   C a m p a i g n _ I n t e l l i g e n c e  
 