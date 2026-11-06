import numpy as np
from typing import List, Dict, Any
from backend.app.decision.optimizer_adapter import DecisionAdapter
from backend.app.decision.models import (
    CandidateOption, DecisionInput, DecisionOutput, RankedCandidate
)
from backend.app.decision.objectives import evaluate_candidate_objectives

class OpenJEVAdapter(DecisionAdapter):
    """
    OpenJEV (Open Joint Evaluation & Value-Focused Compromise Solver) Adapter.
    Uses Chebyshev Compromise Programming to minimize maximum operational-commercial regret:
      d_infty = max_j ( w_j * |Ideal_j - Actual_j| )
    Prefers well-rounded campaigns that avoid excessive weakness in any single objective dimension.
    """
    def __init__(self):
        super().__init__(name="openjev_compromise_adapter")

    def _optimize_and_rank(
        self,
        feasible_candidates: List[CandidateOption],
        decision_input: DecisionInput
    ) -> DecisionOutput:
        obj_evals = evaluate_candidate_objectives(feasible_candidates, decision_input.weights)
        w = decision_input.weights

        # Compute Chebyshev regret score (lower regret = better compromise)
        regrets = []
        for i, scores in enumerate(obj_evals):
            # Distance from ideal (1.0 for each normalized objective)
            contrib_gap = w.expected_contribution * (1.0 - scores["expected_contribution"])
            suitability_gap = w.inventory_suitability * (1.0 - scores["inventory_suitability"])
            stockout_gap = w.stockout_exposure_reduction * (1.0 - scores["stockout_exposure_reduction"])
            eff_gap = w.cost_efficiency * (1.0 - scores["cost_efficiency"])
            seg_gap = w.segment_priority * (1.0 - scores["segment_priority"])

            max_regret = max(contrib_gap, suitability_gap, stockout_gap, eff_gap, seg_gap)
            regrets.append(max_regret)

        indexed = list(enumerate(feasible_candidates))
        # Sort ascending by maximum regret (min-max compromise), tie-breaker composite score
        indexed.sort(
            key=lambda x: (regrets[x[0]], -obj_evals[x[0]]["composite_score"])
        )

        ranked: List[RankedCandidate] = []
        for rank_num, (orig_idx, cand) in enumerate(indexed, start=1):
            scores = obj_evals[orig_idx]
            regret_val = regrets[orig_idx]
            rationale = (
                f"OpenJEV Compromise Rank #{rank_num}: Max Regret={regret_val:.3f}, "
                f"Composite Score={scores['composite_score']:.3f} "
                f"[Net Margin=${cand.expected_contribution:,.2f}, Coverage={cand.stock_coverage_ratio:.2f}x]"
            )
            ranked.append(
                RankedCandidate(
                    rank=rank_num,
                    campaign_id=cand.campaign_id,
                    campaign_name=cand.campaign_name,
                    composite_score=round(1.0 - regret_val, 4),  # Inverted regret as score
                    objective_scores=scores,
                    rationale=rationale
                )
            )

        top_cand = indexed[0][1]
        top_scores = obj_evals[indexed[0][0]]
        min_regret = regrets[indexed[0][0]]

        rationale = (
            f"OpenJEV compromise solver selected '{top_cand.campaign_id}' ({top_cand.campaign_name}) "
            f"minimizing maximum operational/financial regret to {min_regret:.3f}. "
            f"Delivers balanced performance: ${top_cand.expected_contribution:,.2f} net margin, "
            f"{top_cand.stock_coverage_ratio:.2f}x inventory coverage without excessive bottleneck risk."
        )

        raw_ids = [c.campaign_id for c in decision_input.candidates]
        feasible_ids = [c.campaign_id for c in feasible_candidates]

        return DecisionOutput(
            proposal_id=None,
            forecast_version=decision_input.forecast_version,
            candidate_campaign_ids=raw_ids,
            feasible_candidate_ids=feasible_ids,
            selected_campaign_id=top_cand.campaign_id,
            ranked_candidates=ranked,
            objective_values=top_scores,
            constraint_validation_status="passed",
            decision_rationale=rationale,
            framework_used=self.name,
            fallback_triggered=False,
            execution_latency_ms=0.0,
            approval_status="pending_review"
        )

