"""Campaign Intelligence MCP server.

Run locally with: python -m backend.app.mcp_server
The server uses MCP stdio transport and is intended to be launched by an MCP client.
"""
from datetime import date
from typing import Any

from fastmcp import FastMCP

from backend.app.db.repositories.forecast_repo import ForecastRepository
from backend.app.decision.laya_adapter import LayaAdapter
from backend.app.decision.models import CandidateOption, DecisionInput, ObjectiveWeights
from knowledge_base.retriever import retrieve_policy_context

mcp = FastMCP(
    name="Campaign Intelligence",
    instructions=(
        "Tools for demand forecasting, policy retrieval and Laya-based campaign ranking. "
        "Hard feasibility checks and human approval remain authoritative."
    ),
)


@mcp.tool
def forecast_product_demand(
    product_id: str,
    start_date: str,
    horizon_days: int = 7,
) -> dict[str, Any]:
    """Forecast product demand for a user-selected date window (YYYY-MM-DD)."""
    result = ForecastRepository().get_forecast(
        product_id=product_id,
        start_date=date.fromisoformat(start_date),
        horizon_days=horizon_days,
    )
    return result.model_dump(mode="json")


@mcp.tool
def search_campaign_policies(query: str, top_k: int = 4) -> list[dict[str, Any]]:
    """Retrieve relevant campaign policy passages from the Zilliz knowledge base."""
    return retrieve_policy_context(query, top_k=top_k)


@mcp.tool
def rank_campaign_candidates(
    candidates: list[dict[str, Any]],
    weights: dict[str, float] | None = None,
    forecast_version: str = "m5-dynamic-linear-v2",
) -> dict[str, Any]:
    """Rank already-feasibility-checked campaign candidates using the Laya adapter."""
    candidate_models = [CandidateOption(**candidate) for candidate in candidates]
    objective_weights = ObjectiveWeights(**(weights or {}))
    decision = DecisionInput(
        candidates=candidate_models,
        weights=objective_weights,
        forecast_version=forecast_version,
        framework="laya",
    )
    return LayaAdapter().evaluate(decision).model_dump(mode="json")


if __name__ == "__main__":
    mcp.run(transport="stdio")
