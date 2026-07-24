from __future__ import annotations

import hashlib
import math
from typing import Any


CONTROL_RATIO = 0.15
CONVERSION_PRIOR_RATE = 0.012
CONVERSION_PRIOR_STRENGTH = 35

# These are simulation assumptions, not observed online effects. They keep the
# offline feedback internally consistent with the selected channel and score.
CHANNEL_EFFECTS = {
    "app": {"open": 1.08, "click": 1.10, "conversion": 1.12, "unsubscribe": 0.90},
    "sms": {"open": 1.04, "click": 1.03, "conversion": 1.05, "unsubscribe": 1.05},
    "wechat": {"open": 1.06, "click": 1.08, "conversion": 1.09, "unsubscribe": 0.92},
    "email": {"open": 0.96, "click": 0.98, "conversion": 0.96, "unsubscribe": 0.94},
    "phone": {"open": 1.00, "click": 1.14, "conversion": 1.18, "unsubscribe": 1.02},
}
BASELINE_EFFECTS = {"open": 0.88, "click": 0.74, "conversion": 0.70, "unsubscribe": 0.92}


def simulate_strategy_feedback(
    *,
    campaign_id: str,
    selected_candidates: list[dict[str, Any]],
    operator_content: dict[str, str] | None = None,
    benefit_cost_trigger: str = "conversion",
) -> dict[str, Any]:
    """Create deterministic, offline A/B feedback for the current strategy draft.

    The simulation is deliberately aggregate-only. It mirrors the C-side
    aggregate callback contract without creating fake customer-level events.
    """
    content = operator_content or {}
    signature = _signature(campaign_id, selected_candidates, content)
    groups = {"treatment": _empty_group(), "control": _empty_group()}
    channel_breakdown: dict[str, dict[str, dict[str, float | int]]] = {}
    potential_uplifts: list[float] = []
    group_assignments, strata_summary = _assign_stratified_groups(signature, selected_candidates)

    for candidate in selected_candidates:
        channel = str(candidate.get("channel", "app"))
        group_name = group_assignments[_candidate_key(candidate)]
        probabilities = candidate.get("model_scores", {}).get("probabilities", {})
        treatment_probabilities = _outcome_probabilities(
            probabilities,
            channel=channel,
            has_edited_copy=bool(str(content.get(channel, "")).strip()),
            treatment=True,
        )
        control_probabilities = _outcome_probabilities(
            probabilities,
            channel=channel,
            has_edited_copy=False,
            treatment=False,
        )
        potential_uplifts.append(
            treatment_probabilities["conversion"] - control_probabilities["conversion"]
        )

        group = groups[group_name]
        actual_probabilities = treatment_probabilities if group_name == "treatment" else control_probabilities
        events = _simulate_events(signature, candidate, group_name, actual_probabilities)
        economics = _candidate_economics(
            candidate,
            probabilities,
            events,
            benefit_cost_trigger=benefit_cost_trigger,
        )
        modeled_economics = _candidate_economics(
            candidate,
            probabilities,
            _expected_events(actual_probabilities),
            benefit_cost_trigger=benefit_cost_trigger,
        )
        _accumulate_group(group, events, economics)
        _add_modeled_conversion_probability(group, actual_probabilities["conversion"])
        _add_modeled_economics(group, modeled_economics)

        channel_groups = channel_breakdown.setdefault(
            channel,
            {"treatment": _empty_group(), "control": _empty_group()},
        )
        _accumulate_group(channel_groups[group_name], events, economics)
        _add_modeled_conversion_probability(channel_groups[group_name], actual_probabilities["conversion"])
        _add_modeled_economics(channel_groups[group_name], modeled_economics)

    _finalize_group(groups["treatment"])
    _finalize_group(groups["control"])
    for values in channel_breakdown.values():
        _finalize_group(values["treatment"])
        _finalize_group(values["control"])

    observed = _difference_estimate(groups["treatment"], groups["control"])
    modeled_rate = sum(potential_uplifts) / max(len(potential_uplifts), 1)
    modeled_incremental_conversions = sum(potential_uplifts)
    experiment_id = f"SIM-{campaign_id}-{signature[:8]}"
    metrics = {
        "exposure_count": groups["treatment"]["exposure_count"],
        "open_count": groups["treatment"]["open_count"],
        "click_count": groups["treatment"]["click_count"],
        "conversion_count": groups["treatment"]["conversion_count"],
        "unsubscribe_count": groups["treatment"]["unsubscribe_count"],
        "complaint_count": groups["treatment"]["complaint_count"],
        "revenue_cny": groups["treatment"]["modeled_revenue_cny"],
        "marketing_cost_cny": groups["treatment"]["modeled_marketing_cost_cny"],
        "net_value_cny": groups["treatment"]["modeled_net_value_cny"],
    }
    return {
        "source": "offline_simulation",
        "label": "离线仿真 C 端反馈",
        "disclaimer": "基于历史响应模型、策略成本和固定随机种子的仿真结果，不代表真实线上投放表现。",
        "experiment": {
            "experiment_id": experiment_id,
            "status": "simulated",
            "design": "stratified_ab_baseline_touch",
            "treatment_label": "最终策略组",
            "control_label": "基线触达对照组",
            "control_ratio": CONTROL_RATIO,
            "stratification": ["channel", "kmeans_persona"],
            "strata_summary": strata_summary,
            "primary_metric": "conversion_rate",
            "secondary_metrics": ["click_rate", "net_value_cny", "unsubscribe_rate"],
        },
        "feedback_metrics": _round_numbers(metrics),
        "groups": {name: _round_numbers(group) for name, group in groups.items()},
        "channel_breakdown": {
            channel: {name: _round_numbers(group) for name, group in values.items()}
            for channel, values in channel_breakdown.items()
        },
        "uplift": {
            "method": "offline_two_response_uplift_estimate",
            "formula": "E[Y|T=1,X] - E[Y|T=0,X]",
            "modeled_incremental_conversion_rate": round(modeled_rate, 6),
            "modeled_incremental_conversions": round(modeled_incremental_conversions, 2),
            **observed,
        },
        "feedback_contract": {
            "endpoint": "/api/strategy/feedback",
            "event_type": "abtest_aggregate",
            "required_fields": [
                "campaign_id",
                "strategy_version",
                "event_time",
                "experiment.experiment_id",
                "experiment.group",
                "feedback_metrics.exposure_count",
                "feedback_metrics.click_count",
                "feedback_metrics.conversion_count",
                "feedback_metrics.unsubscribe_count",
                "feedback_metrics.revenue_cny",
                "feedback_metrics.marketing_cost_cny",
            ],
        },
    }


def _outcome_probabilities(
    raw: dict[str, Any],
    *,
    channel: str,
    has_edited_copy: bool,
    treatment: bool,
) -> dict[str, float]:
    base = {
        "open": _calibrated_probability(raw.get("p_open"), fallback=0.28, floor=0.03, scale=0.58, ceiling=0.72),
        "click": _calibrated_probability(raw.get("p_click"), fallback=0.055, floor=0.005, scale=0.25, ceiling=0.22),
        "conversion": _calibrated_probability(raw.get("p_conversion"), fallback=0.012, floor=0.002, scale=0.14, ceiling=0.09),
        "unsubscribe": _calibrated_probability(raw.get("p_unsubscribe"), fallback=0.004, floor=0.0005, scale=0.04, ceiling=0.025),
        "complaint": _calibrated_probability(raw.get("p_complaint"), fallback=0.0006, floor=0.0001, scale=0.25, ceiling=0.004),
    }
    if treatment:
        effect = CHANNEL_EFFECTS.get(channel, CHANNEL_EFFECTS["app"])
        copy_bonus = 0.008 if has_edited_copy else 0.0
        return {
            "open": _clamp(base["open"] * effect["open"] + copy_bonus),
            "click": _clamp(base["click"] * effect["click"] + copy_bonus * 0.65),
            "conversion": _clamp(base["conversion"] * effect["conversion"] + copy_bonus * 0.22),
            "unsubscribe": _clamp(base["unsubscribe"] * effect["unsubscribe"]),
            "complaint": _clamp(base["complaint"] * (1.04 if channel in {"sms", "phone"} else 0.94)),
        }
    return {
        "open": _clamp(base["open"] * BASELINE_EFFECTS["open"]),
        "click": _clamp(base["click"] * BASELINE_EFFECTS["click"]),
        "conversion": _clamp(base["conversion"] * BASELINE_EFFECTS["conversion"]),
        "unsubscribe": _clamp(base["unsubscribe"] * BASELINE_EFFECTS["unsubscribe"]),
        "complaint": _clamp(base["complaint"] * 0.90),
    }


def _assign_stratified_groups(
    signature: str,
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Keep treatment/control comparable within channel and KMeans persona strata."""
    strata: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for candidate in candidates:
        channel = str(candidate.get("channel", "app"))
        persona = candidate.get("kmeans_persona", {})
        cluster = str(persona.get("cluster_code", "C0")) if isinstance(persona, dict) else "C0"
        strata.setdefault((channel, cluster), []).append(candidate)

    assignments: dict[str, str] = {}
    summary: list[dict[str, Any]] = []
    for (channel, cluster), rows in sorted(strata.items()):
        ranked = sorted(rows, key=lambda row: _uniform(signature, _candidate_key(row), "stratified_group"))
        if len(ranked) <= 1:
            control_count = 0
        else:
            control_count = min(len(ranked) - 1, max(1, round(len(ranked) * CONTROL_RATIO)))
        for index, candidate in enumerate(ranked):
            assignments[_candidate_key(candidate)] = "control" if index < control_count else "treatment"
        summary.append(
            {
                "channel": channel,
                "persona": cluster,
                "sample_count": len(ranked),
                "control_count": control_count,
                "treatment_count": len(ranked) - control_count,
            }
        )
    return assignments, summary


def _simulate_events(
    signature: str,
    candidate: dict[str, Any],
    group: str,
    probabilities: dict[str, float],
) -> dict[str, int]:
    key = _candidate_key(candidate)
    opened = _bernoulli(probabilities["open"], signature, key, group, "open")
    click_given_open = _clamp(probabilities["click"] / max(probabilities["open"], 0.02))
    clicked = opened and _bernoulli(click_given_open, signature, key, group, "click")
    conversion_given_click = _clamp(probabilities["conversion"] / max(probabilities["click"], 0.004))
    converted = clicked and _bernoulli(conversion_given_click, signature, key, group, "conversion")
    return {
        "exposure_count": 1,
        "open_count": int(opened),
        "click_count": int(clicked),
        "conversion_count": int(converted),
        "unsubscribe_count": int(_bernoulli(probabilities["unsubscribe"], signature, key, group, "unsubscribe")),
        "complaint_count": int(_bernoulli(probabilities["complaint"], signature, key, group, "complaint")),
    }


def _expected_events(probabilities: dict[str, float]) -> dict[str, float]:
    return {
        "exposure_count": 1.0,
        "open_count": probabilities["open"],
        "click_count": probabilities["click"],
        "conversion_count": probabilities["conversion"],
        "unsubscribe_count": probabilities["unsubscribe"],
        "complaint_count": probabilities["complaint"],
    }


def _candidate_economics(
    candidate: dict[str, Any],
    probabilities: dict[str, Any],
    events: dict[str, float],
    *,
    benefit_cost_trigger: str,
) -> dict[str, float]:
    value = candidate.get("strategy_value", {})
    breakdown = value.get("breakdown", {})
    p_conversion = max(_probability(probabilities.get("p_conversion"), fallback=0.012), 0.001)
    p_click = max(_probability(probabilities.get("p_click"), fallback=0.055), 0.001)
    immediate_revenue = float(breakdown.get("immediate_revenue", 0.0))
    ltv_increment = float(breakdown.get("ltv_increment", 0.0))
    credit_loss = float(breakdown.get("credit_expected_loss", 0.0))
    contact_cost = float(breakdown.get("contact_cost", candidate.get("contact_cost", 0.0)) or 0.0)
    benefit_expected_cost = float(breakdown.get("benefit_expected_cost", 0.0))
    unsubscribe_loss = float(breakdown.get("unsubscribe_expected_loss", 0.0))
    complaint_loss = float(breakdown.get("complaint_expected_loss", 0.0))
    trigger = benefit_cost_trigger
    trigger_probability = p_click if trigger == "click" else p_conversion
    return {
        "revenue_cny": events["conversion_count"] * (immediate_revenue + ltv_increment) / p_conversion,
        "contact_cost_cny": events["exposure_count"] * contact_cost,
        "benefit_cost_cny": (events["click_count"] if trigger == "click" else events["conversion_count"])
        * benefit_expected_cost / trigger_probability,
        "credit_loss_cny": events["conversion_count"] * credit_loss / p_conversion,
        "unsubscribe_loss_cny": events["unsubscribe_count"] * unsubscribe_loss / max(_probability(probabilities.get("p_unsubscribe"), fallback=0.004), 0.001),
        "complaint_loss_cny": events["complaint_count"] * complaint_loss / max(_probability(probabilities.get("p_complaint"), fallback=0.0006), 0.0001),
    }


def _empty_group() -> dict[str, float | int]:
    return {
        "exposure_count": 0,
        "open_count": 0,
        "click_count": 0,
        "conversion_count": 0,
        "unsubscribe_count": 0,
        "complaint_count": 0,
        "revenue_cny": 0.0,
        "contact_cost_cny": 0.0,
        "benefit_cost_cny": 0.0,
        "credit_loss_cny": 0.0,
        "unsubscribe_loss_cny": 0.0,
        "complaint_loss_cny": 0.0,
        "marketing_cost_cny": 0.0,
        "net_value_cny": 0.0,
        "open_rate": 0.0,
        "click_rate": 0.0,
        "conversion_rate": 0.0,
        "conversion_rate_modeled": 0.0,
        "modeled_conversion_probability_sum": 0.0,
        "modeled_revenue_cny": 0.0,
        "modeled_contact_cost_cny": 0.0,
        "modeled_benefit_cost_cny": 0.0,
        "modeled_credit_loss_cny": 0.0,
        "modeled_unsubscribe_loss_cny": 0.0,
        "modeled_complaint_loss_cny": 0.0,
        "modeled_marketing_cost_cny": 0.0,
        "modeled_net_value_cny": 0.0,
        "unsubscribe_rate": 0.0,
        "complaint_rate": 0.0,
    }


def _accumulate_group(group: dict[str, float | int], events: dict[str, int], economics: dict[str, float]) -> None:
    for name, value in events.items():
        group[name] = int(group[name]) + value
    for name, value in economics.items():
        group[name] = float(group[name]) + value


def _add_modeled_conversion_probability(group: dict[str, float | int], probability: float) -> None:
    group["modeled_conversion_probability_sum"] = float(group["modeled_conversion_probability_sum"]) + probability


def _add_modeled_economics(group: dict[str, float | int], economics: dict[str, float]) -> None:
    for name, value in economics.items():
        group[f"modeled_{name}"] = float(group[f"modeled_{name}"]) + value


def _finalize_group(group: dict[str, float | int]) -> None:
    exposure = max(int(group["exposure_count"]), 1)
    group["marketing_cost_cny"] = float(group["contact_cost_cny"]) + float(group["benefit_cost_cny"])
    group["net_value_cny"] = (
        float(group["revenue_cny"])
        - float(group["marketing_cost_cny"])
        - float(group["credit_loss_cny"])
        - float(group["unsubscribe_loss_cny"])
        - float(group["complaint_loss_cny"])
    )
    for name in ("open", "click", "conversion", "unsubscribe", "complaint"):
        group[f"{name}_rate"] = int(group[f"{name}_count"]) / exposure
    group["conversion_rate_smoothed"] = _smoothed_rate(
        int(group["conversion_count"]),
        exposure,
        prior_rate=CONVERSION_PRIOR_RATE,
        prior_strength=CONVERSION_PRIOR_STRENGTH,
    )
    group["conversion_rate_modeled"] = float(group.pop("modeled_conversion_probability_sum", 0.0)) / exposure
    group["modeled_marketing_cost_cny"] = (
        float(group["modeled_contact_cost_cny"]) + float(group["modeled_benefit_cost_cny"])
    )
    group["modeled_net_value_cny"] = (
        float(group["modeled_revenue_cny"])
        - float(group["modeled_marketing_cost_cny"])
        - float(group["modeled_credit_loss_cny"])
        - float(group["modeled_unsubscribe_loss_cny"])
        - float(group["modeled_complaint_loss_cny"])
    )


def _difference_estimate(treatment: dict[str, float | int], control: dict[str, float | int]) -> dict[str, float | bool]:
    treatment_n = max(int(treatment["exposure_count"]), 1)
    control_n = max(int(control["exposure_count"]), 1)
    treatment_rate = float(treatment["conversion_rate"])
    control_rate = float(control["conversion_rate"])
    uplift = treatment_rate - control_rate
    smoothed_treatment_rate = float(treatment.get("conversion_rate_smoothed", treatment_rate))
    smoothed_control_rate = float(control.get("conversion_rate_smoothed", control_rate))
    smoothed_uplift = smoothed_treatment_rate - smoothed_control_rate
    modeled_treatment_rate = float(treatment.get("conversion_rate_modeled", smoothed_treatment_rate))
    modeled_control_rate = float(control.get("conversion_rate_modeled", smoothed_control_rate))
    modeled_group_uplift = modeled_treatment_rate - modeled_control_rate
    pooled = (int(treatment["conversion_count"]) + int(control["conversion_count"])) / (treatment_n + control_n)
    standard_error = math.sqrt(max(pooled * (1 - pooled) * (1 / treatment_n + 1 / control_n), 1e-12))
    z_score = uplift / standard_error
    p_value = math.erfc(abs(z_score) / math.sqrt(2))
    independent_error = math.sqrt(
        max(
            treatment_rate * (1 - treatment_rate) / treatment_n
            + control_rate * (1 - control_rate) / control_n,
            1e-12,
        )
    )
    incremental_conversions = uplift * treatment_n
    incremental_net_value = float(treatment["net_value_cny"]) - (
        float(control["net_value_cny"]) / control_n * treatment_n
    )
    modeled_incremental_net_value = float(treatment["modeled_net_value_cny"]) - (
        float(control["modeled_net_value_cny"]) / control_n * treatment_n
    )
    return {
        "observed_incremental_conversion_rate": round(uplift, 6),
        "relative_conversion_lift": round(uplift / max(control_rate, 0.0001), 4),
        "observed_incremental_conversions": round(incremental_conversions, 2),
        "smoothed_incremental_conversion_rate": round(smoothed_uplift, 6),
        "smoothed_incremental_conversions": round(smoothed_uplift * treatment_n, 2),
        "modeled_group_incremental_conversion_rate": round(modeled_group_uplift, 6),
        "modeled_group_incremental_conversions": round(modeled_group_uplift * treatment_n, 2),
        "incremental_net_value_cny": round(incremental_net_value, 2),
        "modeled_group_incremental_net_value_cny": round(modeled_incremental_net_value, 2),
        "confidence_interval_low": round(uplift - 1.96 * independent_error, 6),
        "confidence_interval_high": round(uplift + 1.96 * independent_error, 6),
        "p_value_reference": round(p_value, 6),
        "minimum_group_sample": min(treatment_n, control_n),
        "statistical_reference_passed": bool(
            treatment_n >= 100 and control_n >= 100 and p_value < 0.05 and uplift > 0
        ),
    }


def _smoothed_rate(successes: int, total: int, *, prior_rate: float, prior_strength: float) -> float:
    """Stabilize low-volume demo reporting without altering raw event counts."""
    return (successes + prior_rate * prior_strength) / (max(total, 0) + prior_strength)


def _signature(campaign_id: str, candidates: list[dict[str, Any]], content: dict[str, str]) -> str:
    content_material = [f"{key}={value}" for key, value in sorted(content.items())]
    material = "|".join(
        [campaign_id, *sorted(_candidate_key(candidate) for candidate in candidates), *content_material]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _candidate_key(candidate: dict[str, Any]) -> str:
    return "|".join(
        [
            str(candidate.get("candidate_id", "")),
            str(candidate.get("customer_unique_id") or candidate.get("oneid") or candidate.get("customer_id", "")),
            str(candidate.get("channel", "")),
        ]
    )


def _uniform(*parts: str) -> float:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big") / 2**64


def _bernoulli(probability: float, *parts: str) -> bool:
    return _uniform(*parts) < probability


def _probability(value: Any, *, fallback: float) -> float:
    try:
        return _clamp(float(value))
    except (TypeError, ValueError):
        return fallback


def _calibrated_probability(
    value: Any,
    *,
    fallback: float,
    floor: float,
    scale: float,
    ceiling: float,
) -> float:
    return min(ceiling, floor + _probability(value, fallback=fallback) * scale)


def _clamp(value: float) -> float:
    return max(0.0, min(value, 0.999))


def _round_numbers(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _round_numbers(item) for key, item in value.items()}
    if isinstance(value, float):
        return round(value, 4)
    return value
