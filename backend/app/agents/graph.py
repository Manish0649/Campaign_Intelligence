
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import math
import logging
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig

from backend.app.agents.state import CampaignPlanningState
from backend.app.db.session import SessionLocal

from backend.app.db.repositories.campaign_repo import CampaignRepository
from backend.app.db.repositories.inventory_repo import InventoryRepository
from backend.app.db.repositories.forecast_repo import FORECAST_MODEL, ForecastRepository
from backend.app.db.repositories.proposal_repo import ProposalRepository

from backend.app.api.schemas.proposal import FeasibilityRequest
from backend.app.domain.feasibility import evaluate_campaign_feasibility

from backend.app.decision.models import (
    CandidateOption,
    DecisionInput,
    ObjectiveWeights,
)
from backend.app.decision.laya_adapter import LayaAdapter
from knowledge_base.retriever import retrieve_policy_context

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# Helper: Get DB session from LangGraph config
# ---------------------------------------------------------

def get_db_session(config: RunnableConfig):
    db = config.get("configurable", {}).get("db")

    if db is None:
        raise RuntimeError(
            "Database session not provided to Campaign Planning Graph."
        )

    return db


# ---------------------------------------------------------
# 1. Substep: Retrieve Candidates
# ---------------------------------------------------------

def retrieve_candidates_node(
    state: CampaignPlanningState,
    config: RunnableConfig
) -> Dict[str, Any]:

    db = get_db_session(config)
    camp_repo = CampaignRepository(db)

    campaign_ids = state.get("campaign_ids", [])
    candidates = []

    if not campaign_ids:
        # Default to evaluating all available candidates
        all_camps = camp_repo.get_all_campaigns()
        candidates = all_camps[:5]
    else:
        for cid in campaign_ids:
            campaign = camp_repo.get_campaign(cid)

            if campaign:
                candidates.append(campaign)

    log_entries = [f"Retrieved {len(candidates)} candidate campaigns from catalogue."]

    # RAG is advisory context only. The deterministic feasibility engine and
    # SQL records remain authoritative and are never overridden by retrieval.
    policy_context = []
    if candidates:
        campaign_types = sorted({str(item.get("campaign_type", "")) for item in candidates})
        policy_query = (
            "Campaign planning policies for campaign types "
            + ", ".join(campaign_types)
            + ": budget ceiling, inventory safety stock, supplier lead time, "
              "minimum order quantity, replenishment timing and human approval."
        )
        try:
            policy_context = retrieve_policy_context(policy_query, top_k=3)
            log_entries.append(f"Retrieved {len(policy_context)} advisory policy passages from Zilliz.")
        except Exception as exc:
            logger.warning("Policy retrieval unavailable; deterministic planning continues: %s", type(exc).__name__)
            log_entries.append("Policy retrieval unavailable; deterministic feasibility rules remain authoritative.")

    return {
        "raw_candidates": candidates,
        "policy_context": policy_context,
        "current_step": "candidates_retrieved",
        "audit_log": state.get("audit_log", []) + log_entries
    }


# ---------------------------------------------------------
# 2. Substep: Deterministic Feasibility Evaluation
# ---------------------------------------------------------

def evaluate_feasibility_node(
    state: CampaignPlanningState,
    config: RunnableConfig
) -> Dict[str, Any]:

    db = get_db_session(config)

    camp_repo = CampaignRepository(db)
    inv_repo = InventoryRepository(db)
    fc_repo = ForecastRepository()

    raw_candidates = state.get("raw_candidates", [])
    assumed_uplift = state.get("assumed_uplift_pct", 0.20)

    feasible_options = []
    infeasible_options = []
    evaluations = {}

    for campaign in raw_candidates:

        campaign_id = campaign["campaign_id"]

        cost_assumptions = camp_repo.get_cost_assumption(campaign_id)

        product_ids = campaign["target_product_ids"]

        duration_days = (
            campaign["end_date"] - campaign["start_date"]
        ).days + 1

        product_data = {}

        for product_id in product_ids:

            # Retrieve product information from NeonDB
            product_meta = camp_repo.get_product(product_id)

            if product_meta is None:
                raise LookupError(
                    f"Product '{product_id}' not found in NeonDB."
                )

            # Retrieve inventory and supplier information
            inventory_snapshot = (
                inv_repo.get_inventory_snapshot(product_id)
            )

            supplier_info = (
                inv_repo.get_supplier_replenishment(product_id)
            )

            # ForecastRepository remains file-backed
            forecast_result = fc_repo.get_forecast(
                product_id,
                start_date=campaign["start_date"],
                horizon_days=duration_days,
                model=FORECAST_MODEL,
            )

            product_data[product_id] = {
                "product_name": product_meta.get(
                    "product_name", product_id
                ),
                "base_price": product_meta["base_price"],
                "inventory": inventory_snapshot,
                "supplier": supplier_info,
                "baseline_forecast": (
                    forecast_result.total_forecast_units
                )
            }

        # Build feasibility request
        feasibility_request = FeasibilityRequest(
            campaign_id=campaign_id,
            product_ids=product_ids,
            start_date=campaign["start_date"],
            end_date=campaign["end_date"],
            budget_limit=campaign["campaign_budget"],
            assumed_uplift_pct=assumed_uplift
        )

        # Evaluate campaign feasibility
        feasibility_result = evaluate_campaign_feasibility(
            request=feasibility_request,
            campaign_budget=campaign["campaign_budget"],
            discount_rate=campaign["discount_rate"],
            cost_assumptions=cost_assumptions,
            product_data=product_data
        )

        evaluations[campaign_id] = feasibility_result.model_dump()

        # Compute aggregate revenue and supply metrics
        total_units = sum(
            detail.promotional_demand_units
            for detail in feasibility_result.product_details
        )

        total_supply = sum(
            detail.projected_supply
            for detail in feasibility_result.product_details
        )

        net_usable = sum(
            detail.net_usable_stock
            for detail in feasibility_result.product_details
        )

        weighted_revenue = sum(
            detail.promotional_demand_units
            * product_data[detail.product_id]["base_price"]
            for detail in feasibility_result.product_details
        )

        expected_contribution = round(
            weighted_revenue - feasibility_result.total_projected_cost,
            2
        )

        stock_ratio = round(
            total_supply / (total_units + 1e-4),
            2
        )

        stockout_risk = round(
            max(
                0.0,
                1.0 - (
                    total_supply / (total_units * 1.5 + 1e-4)
                )
            ),
            2
        )

        candidate_option = CandidateOption(
            campaign_id=campaign_id,
            campaign_name=campaign["campaign_name"],
            campaign_type=campaign["campaign_type"],
            target_product_ids=product_ids,
            target_segments=campaign["target_segments"],
            campaign_budget=campaign["campaign_budget"],
            discount_rate=campaign["discount_rate"],
            total_projected_cost=feasibility_result.total_projected_cost,
            projected_units=total_units,
            gross_revenue=weighted_revenue,
            expected_contribution=expected_contribution,
            projected_supply=total_supply,
            net_usable_stock=net_usable,
            stock_coverage_ratio=stock_ratio,
            stockout_risk_score=stockout_risk,
            feasibility_status=feasibility_result.status,
            is_feasible=(
                feasibility_result.status == "feasible_for_review"
            )
        )

        if candidate_option.is_feasible:
            feasible_options.append(candidate_option.model_dump())
        else:
            infeasible_options.append(candidate_option.model_dump())

    log_entry = (
        f"Feasibility engine filtered candidates: "
        f"{len(feasible_options)} feasible, "
        f"{len(infeasible_options)} infeasible."
    )

    return {
        "feasibility_evaluations": evaluations,
        "feasible_options": feasible_options,
        "infeasible_options": infeasible_options,
        "current_step": "feasibility_evaluated",
        "audit_log": state.get("audit_log", []) + [log_entry]
    }


# ---------------------------------------------------------
# 2. Node: Laya Decision Ranking
# ---------------------------------------------------------

def decision_ranking_node(
    state: CampaignPlanningState
) -> Dict[str, Any]:
    feasible_dicts = state.get("feasible_options", [])
    feasible_candidates = [
        CandidateOption(**candidate)
        for candidate in feasible_dicts
    ]
    decision_input = DecisionInput(
        candidates=feasible_candidates,
        weights=ObjectiveWeights(),
        forecast_version=state.get("forecast_version", "m5-dynamic-linear-v2"),
        framework="laya"
    )
    adapter = LayaAdapter()
    decision_output = adapter.evaluate(decision_input)
    log_entry = (
        f"Decision adapter '{adapter.name}' evaluated "
        f"{len(feasible_candidates)} options. "
        f"Selected: '{decision_output.selected_campaign_id}' "
        f"(Fallback: {decision_output.fallback_triggered})."
    )
    return {
        "decision_result": decision_output.model_dump(),
        "current_step": "decision_ranked",
        "audit_log": state.get("audit_log", []) + [log_entry]
    }


# ---------------------------------------------------------
# 3. Node: Structured Proposal Generation & Persistence
# ---------------------------------------------------------

def get_financial_assessment(expected_contribution: float) -> Dict[str, Any]:
    """
    Classifies a campaign using its estimated expected contribution.

    A negative expected contribution is a financial warning,
    not an automatic feasibility rejection.
    """

    contribution = round(float(expected_contribution), 2)

    if contribution > 0:
        return {
            "financial_status": "positive_expected_contribution",
            "financial_warning": None,
            "requires_financial_attention": False
        }

    if contribution == 0:
        return {
            "financial_status": "break_even",
            "financial_warning": (
                "The campaign is expected to break even "
                "under the current assumptions."
            ),
            "requires_financial_attention": True
        }

    return {
        "financial_status": "negative_expected_contribution",
        "financial_warning": (
            "The campaign has a negative expected contribution "
            "under the current assumptions. It is financially "
            "unfavorable and requires explicit human review "
            "before any activation decision."
        ),
        "requires_financial_attention": True
    }
def generate_proposal_node(
    state: CampaignPlanningState,
    config: RunnableConfig
) -> Dict[str, Any]:

    decision_result = state.get("decision_result") or {}
    audit_log = state.get("audit_log", [])

    selected_campaign_id = decision_result.get(
        "selected_campaign_id"
    )

    # -----------------------------------------------------
    # 1. Validate that a campaign was selected
    # -----------------------------------------------------

    if not selected_campaign_id:

        log_entry = (
            "Proposal generation aborted: "
            "No feasible campaign selected."
        )

        return {
            "generated_proposal": None,
            "has_errors": True,
            "error_message": (
                "No feasible campaign option available."
            ),
            "current_step": "proposal_aborted",
            "audit_log": audit_log + [log_entry]
        }

    # -----------------------------------------------------
    # 2. Find the selected campaign in feasible_options
    # -----------------------------------------------------

    feasible_options = state.get("feasible_options", [])

    selected_option = next(
        (
            option
            for option in feasible_options
            if option.get("campaign_id") == selected_campaign_id
        ),
        None
    )

    if selected_option is None:

        log_entry = (
            f"Proposal generation aborted: Selected campaign "
            f"'{selected_campaign_id}' was not found in "
            f"the feasible options."
        )

        return {
            "generated_proposal": None,
            "has_errors": True,
            "error_message": (
                "Selected campaign was not found in "
                "the feasible options."
            ),
            "current_step": "proposal_aborted",
            "audit_log": audit_log + [log_entry]
        }

    # -----------------------------------------------------
    # 3. Retrieve the actual feasibility evaluation
    # -----------------------------------------------------

    feasibility = (
        state.get("feasibility_evaluations", {})
        .get(selected_campaign_id)
    )

    if not feasibility:

        log_entry = (
            f"Proposal generation aborted: No feasibility "
            f"evaluation found for '{selected_campaign_id}'."
        )

        return {
            "generated_proposal": None,
            "has_errors": True,
            "error_message": (
                "Feasibility evaluation not found "
                "for selected campaign."
            ),
            "current_step": "proposal_aborted",
            "audit_log": audit_log + [log_entry]
        }

    # -----------------------------------------------------
    # 4. Validate feasibility status
    # -----------------------------------------------------

    feasibility_status = feasibility.get("status")

    if feasibility_status != "feasible_for_review":

        log_entry = (
            f"Proposal generation aborted: Campaign "
            f"'{selected_campaign_id}' is not feasible for review."
        )

        return {
            "generated_proposal": None,
            "has_errors": True,
            "error_message": (
                "Selected campaign is not feasible for review."
            ),
            "current_step": "proposal_aborted",
            "audit_log": audit_log + [log_entry]
        }

    # -----------------------------------------------------
    # 5. Validate budget and inventory
    # -----------------------------------------------------

    budget_status = feasibility.get(
        "budget_validation"
    )

    inventory_status = feasibility.get(
        "inventory_validation"
    )

    if (
        budget_status != "passed"
        or inventory_status != "passed"
    ):

        log_entry = (
            f"Proposal generation aborted: Validation failed "
            f"for '{selected_campaign_id}'. "
            f"Budget={budget_status}, "
            f"Inventory={inventory_status}."
        )

        return {
            "generated_proposal": None,
            "has_errors": True,
            "error_message": (
                "Budget or inventory validation did not pass."
            ),
            "current_step": "proposal_aborted",
            "audit_log": audit_log + [log_entry]
        }

    # -----------------------------------------------------
    # 6. Retrieve expected contribution from selected option
    # -----------------------------------------------------

    expected_contribution = selected_option.get(
        "expected_contribution"
    )

    if expected_contribution is None:

        log_entry = (
            f"Proposal generation aborted: Expected contribution "
            f"is missing for '{selected_campaign_id}'."
        )

        return {
            "generated_proposal": None,
            "has_errors": True,
            "error_message": (
                "Expected contribution is missing for "
                "the selected campaign."
            ),
            "current_step": "proposal_aborted",
            "audit_log": audit_log + [log_entry]
        }

    try:
        expected_contribution = round(
            float(expected_contribution),
            2
        )

    except (TypeError, ValueError):

        log_entry = (
            f"Proposal generation aborted: Invalid expected "
            f"contribution for '{selected_campaign_id}'."
        )

        return {
            "generated_proposal": None,
            "has_errors": True,
            "error_message": (
                "Expected contribution has an invalid value."
            ),
            "current_step": "proposal_aborted",
            "audit_log": audit_log + [log_entry]
        }

    if not math.isfinite(expected_contribution):

        log_entry = (
            f"Proposal generation aborted: Non-finite expected "
            f"contribution for '{selected_campaign_id}'."
        )

        return {
            "generated_proposal": None,
            "has_errors": True,
            "error_message": (
                "Expected contribution must be a finite number."
            ),
            "current_step": "proposal_aborted",
            "audit_log": audit_log + [log_entry]
        }

    # -----------------------------------------------------
    # 7. Assess financial position
    # -----------------------------------------------------

    financial_assessment = get_financial_assessment(
        expected_contribution
    )

    financial_status = financial_assessment[
        "financial_status"
    ]

    financial_warning = financial_assessment[
        "financial_warning"
    ]

    requires_financial_attention = financial_assessment[
        "requires_financial_attention"
    ]

    # Important:
    # Negative expected contribution is NOT a hard feasibility
    # failure. The campaign remains eligible for human review.

    if financial_warning:

        financial_log = (
            f"Financial warning for '{selected_campaign_id}': "
            f"Expected contribution = "
            f"{expected_contribution}. "
            f"Status = {financial_status}. "
            f"Human review required."
        )

    else:

        financial_log = (
            f"Financial assessment for '{selected_campaign_id}': "
            f"Expected contribution = "
            f"{expected_contribution}. "
            f"Status = {financial_status}."
        )

    # -----------------------------------------------------
    # 8. Get database session and repository
    # -----------------------------------------------------

    db = get_db_session(config)
    proposal_repo = ProposalRepository(db)

    proposal_id = (
        f"PROP-{datetime.now(timezone.utc).strftime('%Y%m%d')}-"
        f"{uuid.uuid4().hex[:6].upper()}"
    )

    # -----------------------------------------------------
    # 9. Persist proposal in NeonDB
    # -----------------------------------------------------

    proposal_record = proposal_repo.save_proposal(
        proposal_id=proposal_id,
        campaign_id=selected_campaign_id,
        forecast_version=state.get(
            "forecast_version",
            "m5-dynamic-linear-v2"
        ),
        decision_status=(
            f"selected_by_"
            f"{decision_result.get('framework_used', 'decision_layer')}"
        ),
        selected_option_id="OPT-1-MULTI-OBJECTIVE",
        budget_validation_status=budget_status,
        inventory_validation_status=inventory_status,
        approval_status="pending_review",
        approver_id="PENDING_ASSIGNMENT",
        created_by="AGENT_ORCHESTRATOR",
        created_by_role="SYSTEM",
    )

    # -----------------------------------------------------
    # 10. Prepare proposal response
    # -----------------------------------------------------

    proposal_data = {
        "proposal_id": proposal_record.proposal_id,

        "campaign_id": proposal_record.campaign_id,

        "forecast_version": proposal_record.forecast_version,

        "decision_status": proposal_record.decision_status,

        "selected_option_id": proposal_record.selected_option_id,

        "budget_validation_status": (
            proposal_record.budget_validation_status
        ),

        "inventory_validation_status": (
            proposal_record.inventory_validation_status
        ),

        "approval_status": proposal_record.approval_status,

        # Financial information
        "financial_assessment": {
            "expected_contribution": expected_contribution,
            "financial_status": financial_status,
            "financial_warning": financial_warning,
            "requires_financial_attention": (
                requires_financial_attention
            )
        },

        # Decision-layer information
        "objective_values": decision_result.get(
            "objective_values",
            {}
        ),

        "decision_rationale": decision_result.get(
            "decision_rationale"
        ),

        "policy_references": [
            {
                "doc_name": item.get("doc_name"),
                "section_title": item.get("section_title"),
                "category": item.get("category"),
                "similarity_score": item.get("similarity_score"),
            }
            for item in state.get("policy_context", [])
        ],

        "created_at": (
            proposal_record.created_at.isoformat()
            if hasattr(proposal_record.created_at, "isoformat")
            else str(proposal_record.created_at)
        )
    }

    # -----------------------------------------------------
    # 11. Audit logging
    # -----------------------------------------------------

    log_entry = (
        f"Generated proposal '{proposal_id}' for "
        f"'{selected_campaign_id}' with status "
        f"'pending_review'."
    )

    updated_audit_log = (
        audit_log
        + [
            financial_log,
            log_entry
        ]
    )

    return {
        "generated_proposal": proposal_data,
        "current_step": "proposal_generated",
        "has_errors": False,
        "error_message": None,
        "audit_log": updated_audit_log
    }



# ---------------------------------------------------------
# 4. Combined Candidate Preparation Node
# ---------------------------------------------------------

def prepare_candidates_node(
    state: CampaignPlanningState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    Run candidate retrieval and deterministic feasibility evaluation
    as one LangGraph node.

    LangGraph nodes return state updates rather than mutating the
    shared state directly. The intermediate state below makes the
    retrieved candidates and policy context available to the
    feasibility evaluator.
    """

    retrieved_update = retrieve_candidates_node(state, config)

    intermediate_state = {
        **state,
        **retrieved_update
    }

    feasibility_update = evaluate_feasibility_node(
        intermediate_state,
        config
    )

    # Merge both node updates. The feasibility update contains the
    # accumulated audit log and the final step name.
    return {
        **retrieved_update,
        **feasibility_update
    }


# ---------------------------------------------------------
# 5. Build LangGraph StateGraph
# ---------------------------------------------------------

def build_campaign_orchestration_graph():

    workflow = StateGraph(CampaignPlanningState)

    workflow.add_node("prepare_candidates", prepare_candidates_node)
    workflow.add_node("decision_ranking", decision_ranking_node)

    workflow.add_node(
        "generate_proposal",
        generate_proposal_node
    )

    workflow.set_entry_point("prepare_candidates")
    workflow.add_edge("prepare_candidates", "decision_ranking")

    workflow.add_edge(
        "decision_ranking",
        "generate_proposal"
    )

    workflow.add_edge(
        "generate_proposal",
        END
    )

    return workflow.compile()


# Compile graph
campaign_agent_graph = build_campaign_orchestration_graph()


# ---------------------------------------------------------
# 6. Orchestration Entry Point
# ---------------------------------------------------------

def orchestrate_campaign_planning(
    campaign_ids: Optional[List[str]] = None,
    decision_framework: str = "laya",
    assumed_uplift_pct: float = 0.20
) -> Dict[str, Any]:
    """
    Executes the end-to-end LangGraph Campaign Planning workflow.

    A single NeonDB session is shared across the sequential graph nodes.
    """

    initial_state: CampaignPlanningState = {
        "campaign_ids": campaign_ids or [],
        "forecast_version": "m5-dynamic-linear-v2",
        "decision_framework": decision_framework,
        "assumed_uplift_pct": assumed_uplift_pct,
        "raw_candidates": [],
        "policy_context": [],
        "feasibility_evaluations": {},
        "feasible_options": [],
        "infeasible_options": [],
        "decision_result": None,
        "generated_proposal": None,
        "audit_log": [
            "Orchestration session initialized."
        ],
        "current_step": "init",
        "has_errors": False,
        "error_message": None
    }

    # Open one database session for the graph execution
    with SessionLocal() as db:

        result = campaign_agent_graph.invoke(
            initial_state,
            config={
                "configurable": {
                    "db": db
                }
            }
        )

    return result
