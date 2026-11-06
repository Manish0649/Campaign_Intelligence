# Implemented improvements

## Frontend
- Added a cleaner shared Streamlit visual theme and role-aware navigation.
- Updated date pickers to default to tomorrow instead of a hard-coded 2016 date.
- Updated forecast UI to support user-selected dates and 1–30 day horizons.
- Expanded Health Check to show backend, database, LangGraph, Laya, MCP SDK, Gemini configuration and Zilliz connectivity.
- Added an admin-only **Run Pytest Suite** action with passed/failed/error/skipped counts and captured output.

## Forecasting
- Replaced runtime lookups against a fixed seven-day CSV with on-demand per-product linear regression trained from historical demand.
- Generates dates from the requested start date, rather than requiring dates to exist in the historical database or a pre-generated forecast file.
- Uses calendar seasonality, lag demand, rolling statistics and a weekday seasonal blend so the forecast does not repeat one identical prediction across all days.
- Supported horizon: 1–30 days. Requested forecast dates must be after the latest historical observation for the product.

## Proposals and roles
- Added a configurable `PROPOSAL-SUBMITTER` account using `PROPOSAL_USER_EMAIL` and `PROPOSAL_USER_PASSWORD`.
- Added a proposal queue: reviewers can see all proposals, while submitters see only proposals they created.
- This account can create proposals. The existing backend approval and activation checks remain in force; submitters cannot approve or activate.
- Configure the two values in your private local `.env`. Use a unique password with at least 12 characters. Do not commit or share `.env`.

## Decision and agents
- Removed OpenJEV and the multi-framework comparison route/UI.
- LayaAdapter is the only selectable decision framework. Weighted objective scoring and sorting remain application-side; the Laya package is used for confidence calibration.
- Removed per-request thread-pool creation from the in-process Laya adapter path.
- Consolidated candidate retrieval and feasibility into one LangGraph node. The graph now has three stages: candidate preparation + feasibility, Laya ranking, proposal persistence.

## MCP
- Added `backend/app/mcp_server.py` using FastMCP.
- Tools: `forecast_product_demand`, `search_campaign_policies`, and `rank_campaign_candidates`.
- Added `MCP_SETUP.md` with install/run instructions. MCP runs as a separate stdio process and must be launched by an MCP-compatible host.

## Validation performed in this workspace
- All Python source files passed `py_compile`.
- Manually exercised the dynamic forecast for `FOODS_1_018` with a custom 2026 date window; returned requested dates and varying daily predictions.
- Full pytest suite and live database/Gemini/Zilliz/MCP integration could not be executed in this workspace because runtime packages such as `laya`, `langgraph`, `fastmcp` and `streamlit` are not installed here. Install `backend/requirements.txt` and `frontend/requirements.txt`, configure `.env`, then run the suite from the project root.

## Important setup after extracting the ZIP
1. Copy `.env.example` to `.env`.
2. Restore your private database, JWT, Gemini and Zilliz credentials in `.env`.
3. Set `PROPOSAL_USER_EMAIL` and `PROPOSAL_USER_PASSWORD` for the new submitter login.
4. Install backend and frontend requirements.
5. Run FastAPI and Streamlit as usual.
6. To use MCP, configure your MCP-compatible client to launch `python -m backend.app.mcp_server` from the project root.
