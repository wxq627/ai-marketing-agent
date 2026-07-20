from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SelectionResult:
    selected: list[dict[str, Any]]
    excluded: dict[str, int]
    budget_used: float
    expected_net_value: float
    expected_conversion_count: float
    channel_usage: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_candidate_count": len(self.selected),
            "budget_used": round(self.budget_used, 4),
            "expected_net_value": round(self.expected_net_value, 4),
            "expected_conversion_count": round(self.expected_conversion_count, 4),
            "channel_usage": dict(self.channel_usage),
            "excluded_by_constraint": dict(self.excluded),
        }


class BudgetConstrainedSelector:
    """Greedily choose the highest-value eligible candidates under hard constraints."""

    def select(
        self,
        candidates: list[dict[str, Any]],
        *,
        budget: float,
        minimum_net_value: float = 0.0,
        one_candidate_per_customer: bool = True,
    ) -> SelectionResult:
        if budget <= 0:
            raise ValueError("budget must be positive")
        ranked = sorted(
            candidates,
            key=lambda item: (
                float(item["strategy_value"]["value_density"]),
                float(item["strategy_value"]["expected_net_value"]),
            ),
            reverse=True,
        )
        selected: list[dict[str, Any]] = []
        excluded: Counter[str] = Counter()
        selected_customers: set[str] = set()
        channel_usage: Counter[str] = Counter()
        budget_used = 0.0
        expected_net_value = 0.0
        expected_conversion_count = 0.0

        for candidate in ranked:
            value = candidate["strategy_value"]
            net_value = float(value["expected_net_value"])
            cost = float(value["budget_cost"])
            customer_id = str(candidate["customer_id"])
            channel = str(candidate["channel"])
            capacity = int(candidate.get("channel_daily_capacity", 0) or 0)
            if net_value <= minimum_net_value:
                excluded["non_positive_expected_value"] += 1
                continue
            if one_candidate_per_customer and customer_id in selected_customers:
                excluded["customer_deduplicated"] += 1
                continue
            if capacity > 0 and channel_usage[channel] >= capacity:
                excluded["channel_capacity_reached"] += 1
                continue
            if budget_used + cost > budget:
                excluded["budget_exhausted"] += 1
                continue

            selected.append(candidate)
            selected_customers.add(customer_id)
            channel_usage[channel] += 1
            budget_used += cost
            expected_net_value += net_value
            expected_conversion_count += float(
                candidate["model_scores"]["probabilities"]["p_conversion"]
            )

        return SelectionResult(
            selected=selected,
            excluded=dict(excluded),
            budget_used=budget_used,
            expected_net_value=expected_net_value,
            expected_conversion_count=expected_conversion_count,
            channel_usage=dict(channel_usage),
        )
