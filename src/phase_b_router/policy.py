"""Pure decision-matrix routing policy, independent of LangGraph."""


def get_routing_decision(correlation_level: str, estimated_selectivity: float, thresholds_dict: dict) -> str:
    """Choose the safe route for a correlation tier and selectivity estimate.

    The threshold file stores explicit recall and latency danger intervals.
    The deadband margin is applied on both sides of each interval.
    """
    if correlation_level not in thresholds_dict:
        raise ValueError(f"Missing thresholds for correlation level: {correlation_level}")
    thresholds = thresholds_dict[correlation_level]
    margin = thresholds.get("margin", 0.01)
    for key in ("recall_danger_zones", "latency_danger_zones"):
        for start, end in thresholds.get(key, []):
            if start - margin <= estimated_selectivity <= end + margin:
                return "post-filter"
    return "pre-filter"
