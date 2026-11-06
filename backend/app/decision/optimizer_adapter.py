import abc
import time
import logging
from typing import Optional, List

from backend.app.decision.models import DecisionInput, DecisionOutput, CandidateOption
from backend.app.decision.baseline_ranker import BaselineRanker
from backend.app.decision.constraints import filter_feasible_candidates, verify_decision_selection_inviolability

logger = logging.getLogger(__name__)

class DecisionAdapter(abc.ABC):
    """
    Abstract Decision Adapter Interface.
    Encapsulates the Laya decision framework with:
      - Mandatory deterministic feasibility pre-filtering
      - Execution timeout enforcement
      - Safety fallback to deterministic BaselineRanker on solver failure
      - Returned campaign identifier validation
      - Re-check verification
    """
    def __init__(self, name: str):
        self.name = name
        self.baseline_ranker = BaselineRanker()

    @abc.abstractmethod
    def _optimize_and_rank(
        self,
        feasible_candidates: List[CandidateOption],
        decision_input: DecisionInput
    ) -> DecisionOutput:
        """Subclasses implement specific multi-objective ranking or solver algorithms."""
        pass

    def evaluate(self, decision_input: DecisionInput) -> DecisionOutput:
        start_time = time.perf_counter()
        raw_ids = [c.campaign_id for c in decision_input.candidates]

        # 1. Hard Constraint Filter: Decision layer can only optimize feasible candidates
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
                decision_rationale="No candidate campaigns passed deterministic feasibility checks.",
                framework_used=self.name,
                fallback_triggered=False,
                execution_latency_ms=round(latency, 2),
                approval_status="rejected"
            )

        # 2. Execute the local deterministic solver directly; avoid per-request
        # thread-pool creation overhead for this CPU-bound in-process ranking.
        try:
            output = self._optimize_and_rank(feasible_candidates, decision_input)

            # 3. Validate returned campaign ID
            if output.selected_campaign_id not in feasible_ids:
                raise ValueError(
                    f"Invalid decision output: Selected ID '{output.selected_campaign_id}' is not in feasible set {feasible_ids}"
                )

            # 4. Inviolability Re-check
            selected_cand = next(c for c in feasible_candidates if c.campaign_id == output.selected_campaign_id)
            recheck_ok, recheck_msg = verify_decision_selection_inviolability(selected_cand)
            if not recheck_ok:
                raise ValueError(f"Decision safety violation: {recheck_msg}")

            output.execution_latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            output.candidate_campaign_ids = raw_ids
            output.feasible_candidate_ids = feasible_ids
            return output

        except Exception as e:
            logger.warning(f"Decision framework '{self.name}' encountered error ({e}). Falling back to baseline ranker.")
            fallback_res = self.baseline_ranker.rank(decision_input)
            fallback_res.fallback_triggered = True
            fallback_res.decision_rationale = (
                f"[Fallback Alert] '{self.name}' failed with error: {str(e)}. "
                f"Deterministically selected '{fallback_res.selected_campaign_id}' via {self.baseline_ranker.name}."
            )
            fallback_res.execution_latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            return fallback_res

