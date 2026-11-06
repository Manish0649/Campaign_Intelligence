# Campaign Intelligence MCP Server

The project exposes three MCP tools through a local FastMCP stdio server:

- `forecast_product_demand`: on-demand product demand forecast for a selected date window.
- `search_campaign_policies`: semantic retrieval from the Zilliz policy knowledge base.
- `rank_campaign_candidates`: Laya ranking for candidates that have already passed deterministic feasibility checks.

## Install and run

From the project root, install backend dependencies:

```bash
pip install -r backend/requirements.txt
```

Configure the normal project `.env` values (database, JWT, Gemini and Zilliz settings) before running tools that need those services.

Start the MCP server:

```bash
python -m backend.app.mcp_server
```

The server uses **stdio transport**. Configure your MCP-compatible desktop client/host to launch that command with the project root as its working directory and the same Python environment. It is a separate process from FastAPI; MCP is not automatically exposed over HTTP.

## Safety boundary

`rank_campaign_candidates` expects candidate dictionaries that already passed the Campaign Intelligence feasibility checks. MCP ranking does not approve or activate a campaign. Human approval and existing backend governance endpoints remain mandatory.
