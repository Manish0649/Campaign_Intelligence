import logging
import numpy as np
from typing import List, Dict, Any, Optional

import laya
from laya.common import confidence_from_probs

from backend.app.decision.optimizer_adapter import DecisionAdapter
from backend.app.decision.models import (
    CandidateOption, DecisionInput, DecisionOutput, RankedCandidate
)
from backend.app.decision.objectives import evaluate_candidate_objectives

logger = logging.getLogger(__name__)


class LayaAdapter(DecisionAdapter):
    """
    Laya Multi-Attribute Decision Adapter.
    Uses the application's weighted multi-attribute objective scores to rank feasible
    candidates and the installed Laya package's confidence_from_probs() function to
    calibrate confidence from the resulting candidate-score distribution.

    Candidate objective calculation and sorting are application-side logic; the Laya
    package is used directly for confidence calibration.
    """
    def __init__(self):
        super().__init__(name="laya_decision_adapter")
        self.laya_version = getattr(laya, "__version__", "0.4.22")

    def _optimize_and_rank(
        self,
        feasible_candidates: List[CandidateOption],
        decision_input: DecisionInput
    ) -> DecisionOutput:
        obj_evals = evaluate_candidate_objectives(feasible_candidates, decision_input.weights)

        # 1. Rank candidates by multi-attribute composite utility
        indexed = list(enumerate(feasible_candidates))
        indexed.sort(
            key=lambda x: obj_evals[x[0]]["composite_score"],
            reverse=True
        )

        # 2. Compute Laya calibrated decision confidence across candidates
        composite_scores = np.array([obj_evals[i]["composite_score"] for i, _ in indexed], dtype=float)
        k = len(composite_scores)
        if k >= 2 and np.ptp(composite_scores) > 1e-6:
            # Softmax distribution over candidate utility scores
            exp_scores = np.exp(composite_scores - np.max(composite_scores))
            probs = exp_scores / np.sum(exp_scores)
            laya_conf = float(confidence_from_probs(probs, k))
        else:
            laya_conf = 1.0

        ranked: List[RankedCandidate] = []
        for rank_num, (orig_idx, cand) in enumerate(indexed, start=1):
            scores = obj_evals[orig_idx]
            rationale = (
                f"Laya Composite Utility={scores['composite_score']:.3f} "
                f"[Contribution={scores['expected_contribution']:.2f}, "
                f"Coverage={scores['inventory_suitability']:.2f}, "
                f"StockoutSafety={scores['stockout_exposure_reduction']:.2f}, "
                f"ROI={scores['cost_efficiency']:.2f}, "
                f"Segment={scores['segment_priority']:.2f}]"
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

        top_cand = indexed[0][1]
        top_scores = dict(obj_evals[indexed[0][0]])
        top_scores["laya_confidence"] = round(laya_conf, 4)

        rationale = (
            f"Campaign Intelligence LayaAdapter (Laya v{self.laya_version}) selected '{top_cand.campaign_id}' "
            f"({top_cand.campaign_name}) with top composite utility of {top_scores['composite_score']:.3f} "
            f"(calibrated confidence: {laya_conf:.2%}). "
            f"Balances net contribution of ${top_cand.expected_contribution:,.2f} "
            f"against {top_cand.stock_coverage_ratio:.2f}x supply coverage and "
            f"{top_scores['stockout_exposure_reduction']:.2f} safety stock buffer score."
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
