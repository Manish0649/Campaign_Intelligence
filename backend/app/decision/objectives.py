import numpy as np
from typing import List, Dict, Any
from backend.app.decision.models import CandidateOption, ObjectiveWeights

SEGMENT_PRIORITY_MAP = {
    "bulk_buyers": 1.0,
    "loyal_members": 0.95,
    "craft_enthusiasts": 0.85,
    "suburban_families": 0.80,
    "budget_conscious": 0.75,
    "bargain_hunters": 0.70
}

def min_max_normalize(values: List[float], higher_is_better: bool = True) -> List[float]:
    """
    Min-max normalizes a feature list into [0.0, 1.0].
    Handles zero-variance edge cases safely.
    """
    if not values:
        return []
    min_v = float(min(values))
    max_v = float(max(values))
    if max_v == min_v:
        return [1.0 for _ in values]
    
    if higher_is_better:
        return [(v - min_v) / (max_v - min_v) for v in values]
    else:
        return [(max_v - v) / (max_v - min_v) for v in values]

def evaluate_candidate_objectives(
    candidates: List[CandidateOption],
    weights: ObjectiveWeights
) -> List[Dict[str, float]]:
    """
    Calculates normalized multi-objective attribute vectors for each candidate option:
      - expected_contribution (net margin)
      - inventory_suitability (supply / demand coverage)
      - stockout_exposure_reduction (safety stock buffer cushion)
      - cost_efficiency (contribution / cost ratio)
      - segment_priority (customer segment alignment)
    """
    if not candidates:
        return []

    # Raw metrics
    raw_contrib = [c.expected_contribution for c in candidates]
    raw_suitability = [min(c.stock_coverage_ratio, 3.0) for c in candidates]
    raw_stockout_risk = [c.stockout_risk_score for c in candidates]
    raw_efficiency = [
        c.expected_contribution / (c.total_projected_cost + 1.0) for c in candidates
    ]
    raw_segments = [
        SEGMENT_PRIORITY_MAP.get(c.target_segments.lower(), 0.70) for c in candidates
    ]

    # Normalized metrics [0, 1]
    norm_contrib = min_max_normalize(raw_contrib, higher_is_better=True)
    norm_suitability = min_max_normalize(raw_suitability, higher_is_better=True)
    norm_stockout = min_max_normalize(raw_stockout_risk, higher_is_better=False)  # lower risk is better
    norm_efficiency = min_max_normalize(raw_efficiency, higher_is_better=True)
    norm_segments = min_max_normalize(raw_segments, higher_is_better=True)

    results = []
    for i in range(len(candidates)):
        obj = {
            "expected_contribution": round(norm_contrib[i], 4),
            "inventory_suitability": round(norm_suitability[i], 4),
            "stockout_exposure_reduction": round(norm_stockout[i], 4),
            "cost_efficiency": round(norm_efficiency[i], 4),
            "segment_priority": round(norm_segments[i], 4)
        }
        # Weighted composite score
        composite = (
            weights.expected_contribution * obj["expected_contribution"] +
            weights.inventory_suitability * obj["inventory_suitability"] +
            weights.stockout_exposure_reduction * obj["stockout_exposure_reduction"] +
            weights.cost_efficiency * obj["cost_efficiency"] +
            weights.segment_priority * obj["segment_priority"]
        )
        obj["composite_score"] = round(float(composite), 4)
        results.append(obj)

    return results

