import time
from typing import List
from backend.app.decision.models import (
    CandidateOption, DecisionInput, DecisionOutput, RankedCandidate
)
from backend.app.decision.constraints import filter_feasible_candidates, verify_decision_selection_inviolability
from backend.app.decision.objectives import evaluate_candidate_objectives

class BaselineRanker:
    """
    Deterministic Baseline Decision Ranker.
    Ranks feasible campaign options strictly by expected net contribution (Gross Revenue - Total Cost),
    with inventory safety buffer ratio as a secondary tie-breaker.
    """
    def __init__(self, name: str = "deterministic_baseline_ranker"):
        self.name = name

    def rank(self, decision_input: DecisionInput) -> DecisionOutput:
        start_time = time.perf_counter()
        raw_ids = [c.campaign_id for c in decision_input.candidates]

        # 1. Hard Constraint Filtering
        feasible_candidates, discarded = filter_feasible_candidates(decision_input.candidates)
        feasible_ids = [c.campaign_id for c in feasible_candidates]

        if not feasible_candidates:
            latency = (time.perf_counter() - start_time) * 1000.0
            return DecisionOutput(
                forecast_version=decision_input.forecast_version,
                candidate_campaign_ids=raw_ids,
                feasible_candidate_ids=[],
                selected_campaign_id=None,
                ranked_candidates=[],
                objective_values={},
                constraint_validation_status="failed_no_feasible_candidates",
                decision_rationale="No candidate campaigns satisfied mandatory deterministic constraints.",
                framework_used=self.name,
                fallback_triggered=False,
                execution_latency_ms=round(latency, 2),
                approval_status="rejected"
            )

        # 2. Compute Objective Scores
        obj_evals = evaluate_candidate_objectives(feasible_candidates, decision_input.weights)

        # 3. Deterministic Greedy Sort by Expected Contribution, then Stock Coverage
        indexed = list(enumerate(feasible_candidates))
        # Sort descending by expected contribution, then stock_coverage_ratio
        indexed.sort(
            key=lambda x: (x[1].expected_contribution, x[1].stock_coverage_ratio),
            reverse=True
        )

        ranked: List[RankedCandidate] = []
        for rank_num, (orig_idx, cand) in enumerate(indexed, start=1):
            scores = obj_evals[orig_idx]
            rationale = (
                f"Rank #{rank_num}: Net Contribution=${cand.expected_contribution:,.2f}, "
                f"Coverage={cand.stock_coverage_ratio:.2f}x, Budget-Use={cand.total_projected_cost/cand.campaign_budget:.1%}"
            )
            ranked.append(
                RankedCandidate(
                    rank=rank_num,
                    campaign_id=cand.campaign_id,
                    campaign_name=cand.campaign_name,
                    composite_score=scores["composite_score"],
                    objective_scores=scores,
                    rationale=rationale
                )
            )

        selected = indexed[0][1]
        recheck_ok, recheck_msg = verify_decision_selection_inviolability(selected)

        latency = (time.perf_counter() - start_time) * 1000.0
        selected_scores = obj_evals[indexed[0][0]]

        decision_rationale = (
            f"Baseline ranker selected '{selected.campaign_id}' ({selected.campaign_name}) "
            f"yielding highest projected net contribution (${selected.expected_contribution:,.2f}) "
            f"with {selected.stock_coverage_ratio:.2f}x supply coverage."
        )

        return DecisionOutput(
            proposal_id=None,
            forecast_version=decision_input.forecast_version,
            candidate_campaign_ids=raw_ids,
            feasible_candidate_ids=feasible_ids,
            selected_campaign_id=selected.campaign_id,
            ranked_candidates=ranked,
            objective_values=selected_scores,
            constraint_validation_status="passed" if recheck_ok else "failed_inviolability",
            decision_rationale=decision_rationale,
            framework_used=self.name,
            fallback_triggered=False,
            execution_latency_ms=round(latency, 2),
            approval_status="pending_review" if recheck_ok else "rejected"
        )

