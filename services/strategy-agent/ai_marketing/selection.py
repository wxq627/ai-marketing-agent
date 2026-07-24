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
    channel_coverage: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_candidate_count": len(self.selected),
            "budget_used": round(self.budget_used, 4),
            "expected_net_value": round(self.expected_net_value, 4),
            "expected_conversion_count": round(self.expected_conversion_count, 4),
            "channel_usage": dict(self.channel_usage),
            "channel_coverage": self.channel_coverage,
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
        coverage_channels: list[str] | None = None,
        minimum_channel_trial_count: int = 0,
    ) -> SelectionResult:
        if budget <= 0:
            raise ValueError("budget must be positive")
        if minimum_channel_trial_count < 0:
            raise ValueError("minimum_channel_trial_count must not be negative")
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
        selected_customer_ids: set[str] = set()
        channel_usage: Counter[str] = Counter()
        budget_used = 0.0
        expected_net_value = 0.0
        expected_conversion_count = 0.0
        selected_candidate_ids: set[str] = set()

        requested_coverage_channels = list(dict.fromkeys(coverage_channels or []))
        coverage_selected: Counter[str] = Counter()
        coverage_candidates = Counter(
            str(candidate.get("channel", "")) for candidate in candidates
        )

        def try_select(candidate: dict[str, Any]) -> bool:
            nonlocal budget_used, expected_net_value, expected_conversion_count
            candidate_id = str(candidate.get("candidate_id", ""))
            if candidate_id in selected_candidate_ids:
                return False
            value = candidate["strategy_value"]
            net_value = float(value["expected_net_value"])
            cost = float(value["budget_cost"])
            customer_unique_id = str(candidate.get("customer_unique_id") or candidate["customer_id"])
            channel = str(candidate["channel"])
            capacity = int(candidate.get("channel_daily_capacity", 0) or 0)
            if net_value <= minimum_net_value:
                excluded["non_positive_expected_value"] += 1
                return False
            if one_candidate_per_customer and customer_unique_id in selected_customer_ids:
                excluded["customer_deduplicated"] += 1
                return False
            if capacity > 0 and channel_usage[channel] >= capacity:
                excluded["channel_capacity_reached"] += 1
                return False
            if budget_used + cost > budget:
                excluded["budget_exhausted"] += 1
                return False

            selected.append(candidate)
            selected_candidate_ids.add(candidate_id)
            selected_customer_ids.add(customer_unique_id)
            channel_usage[channel] += 1
            budget_used += cost
            expected_net_value += net_value
            expected_conversion_count += float(
                candidate["model_scores"]["probabilities"]["p_conversion"]
            )
            return True

        # Reserve a small, economically viable trial sample for every explicitly requested channel.
        if requested_coverage_channels and minimum_channel_trial_count:
            for channel in requested_coverage_channels:
                channel_ranked = (candidate for candidate in ranked if candidate["channel"] == channel)
                for candidate in channel_ranked:
                    if coverage_selected[channel] >= minimum_channel_trial_count:
                        break
                    if try_select(candidate):
                        coverage_selected[channel] += 1

        for candidate in ranked:
            try_select(candidate)

        unmet_channels = [
            channel
            for channel in requested_coverage_channels
            if coverage_selected[channel] < minimum_channel_trial_count
        ]
        channel_coverage = {
            "enabled": bool(requested_coverage_channels and minimum_channel_trial_count),
            "minimum_trial_count_per_channel": minimum_channel_trial_count,
            "requested_channels": requested_coverage_channels,
            "eligible_candidate_counts": {
                channel: coverage_candidates[channel] for channel in requested_coverage_channels
            },
            "trial_selected_counts": {
                channel: coverage_selected[channel] for channel in requested_coverage_channels
            },
            "unmet_channels": unmet_channels,
        }

        return SelectionResult(
            selected=selected,
            excluded=dict(excluded),
            budget_used=budget_used,
            expected_net_value=expected_net_value,
            expected_conversion_count=expected_conversion_count,
            channel_usage=dict(channel_usage),
            channel_coverage=channel_coverage,
        )
