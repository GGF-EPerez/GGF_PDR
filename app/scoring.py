from __future__ import annotations

from statistics import mean
from typing import List, Tuple

from app.models import PricePoint


def calculate_acquisition_score(
    pricing_history: List[PricePoint],
    estimated_price: float | None,
    has_recent_docs: bool,
) -> Tuple[float, list[str]]:
    """Simple 0-100 score for screening acquisition targets.

    Heuristics (toy example):
    - better score if long-term growth exists but is not overheated
    - slight penalty if no recent record activity is available
    - slight bonus when estimate is above historical average (momentum)
    """

    notes: list[str] = []
    if not pricing_history:
        return 20.0, ["Insufficient pricing history."]

    first = pricing_history[0].amount
    last = pricing_history[-1].amount
    total_growth = (last - first) / first if first > 0 else 0.0

    yoy_changes = []
    for prev, curr in zip(pricing_history, pricing_history[1:]):
        yoy_changes.append((curr.amount - prev.amount) / prev.amount if prev.amount > 0 else 0.0)

    avg_yoy = mean(yoy_changes) if yoy_changes else 0.0

    score = 50.0
    score += min(max(total_growth * 40.0, -20.0), 30.0)
    score += min(max((0.08 - abs(avg_yoy - 0.05)) * 100.0, -10.0), 10.0)

    if has_recent_docs:
        score += 5.0
        notes.append("Recent record activity present.")
    else:
        score -= 5.0
        notes.append("No recent record activity found.")

    if estimated_price is not None:
        hist_avg = mean([p.amount for p in pricing_history])
        if estimated_price > hist_avg:
            score += 5.0
            notes.append("Current estimate is above 10-year average.")
        else:
            notes.append("Current estimate is at/below 10-year average.")

    notes.append(f"10-year total growth: {total_growth:.1%}.")
    notes.append(f"Average YoY change: {avg_yoy:.1%}.")

    score = max(0.0, min(100.0, score))
    return round(score, 2), notes
