from typing import List, Tuple
from backend.app.decision.models import CandidateOption

def filter_feasible_candidates(candidates: List[CandidateOption]) -> Tuple[List[CandidateOption], List[str]]:
    """
    Hard Constraint Filter (Rule 3):
    The decision layer can only rank and optimize candidates that have PASSED
    all mandatory deterministic feasibility checks.
    Infeasible proposals are strictly discarded.
    """
    feasible = []
    discarded_reasons = []

    for c in candidates:
        if not c.is_feasible:
            discarded_reasons.append(
                f"Discarded '{c.campaign_id}': Failed feasibility status '{c.feasibility_status}'"
            )
            continue
        if c.total_projected_cost > c.campaign_budget:
            discarded_reasons.append(
                f"Discarded '{c.campaign_id}': Projected cost (${c.total_projected_cost:,.2f}) exceeds budget (${c.campaign_budget:,.2f})"
            )
            continue
        if c.projected_supply < c.projected_units:
            discarded_reasons.append(
                f"Discarded '{c.campaign_id}': Projected supply ({c.projected_supply}) cannot cover demand ({c.projected_units:.1f})"
            )
            continue
        feasible.append(c)

    return feasible, discarded_reasons

def verify_decision_selection_inviolability(
    selected: CandidateOption
) -> Tuple[bool, str]:
    """
    Post-decision recheck to ensure no decision model output has bypassed hard constraints.
    """
    if not selected.is_feasible:
        return False, f"Inviolability breach: Selected candidate '{selected.campaign_id}' is flagged infeasible."
    if selected.total_projected_cost > selected.campaign_budget:
        return False, f"Inviolability breach: Selected candidate '{selected.campaign_id}' exceeds budget."
    if selected.projected_supply < selected.projected_units:
        return False, f"Inviolability breach: Selected candidate '{selected.campaign_id}' has supply deficit."
    return True, "passed"

