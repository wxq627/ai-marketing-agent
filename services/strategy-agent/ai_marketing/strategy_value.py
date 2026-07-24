from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SERVICE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = SERVICE_DIR / "config" / "strategy_value_policy.json"
CAMPAIGN_MAPPING_PATH = SERVICE_DIR / "config" / "campaign_offer_mapping.csv"


@dataclass(frozen=True)
class StrategyValue:
    candidate_id: str
    expected_net_value: float
    budget_cost: float
    value_density: float
    p_long_term: float
    breakdown: dict[str, float | str]
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "expected_net_value": self.expected_net_value,
            "budget_cost": self.budget_cost,
            "value_density": self.value_density,
            "p_long_term": self.p_long_term,
            "breakdown": self.breakdown,
            "policy_version": self.policy_version,
        }


class StrategyValueCalculator:
    """Convert model probabilities and business economics into expected net value."""

    def __init__(
        self,
        *,
        policy_path: Path | None = None,
        campaign_mapping_path: Path | None = None,
    ) -> None:
        self.policy = _load_json(policy_path or CONFIG_PATH)
        self.campaign_mapping = _load_campaign_mapping(campaign_mapping_path or CAMPAIGN_MAPPING_PATH)

    def score(self, candidate: dict[str, Any]) -> StrategyValue:
        probabilities = candidate.get("model_scores", {}).get("probabilities")
        if not isinstance(probabilities, dict):
            raise ValueError("candidate requires available historical model probabilities")
        campaign_id = str(candidate.get("campaign_id", ""))
        mapping = self.campaign_mapping.get(campaign_id)
        if mapping is None:
            raise ValueError(f"unknown campaign_id: {campaign_id}")

        p_click = _probability(probabilities.get("p_click"))
        p_conversion = _probability(probabilities.get("p_conversion"))
        p_unsubscribe = _probability(probabilities.get("p_unsubscribe"))
        profile = candidate.get("economic_profile", {})
        object_type = mapping.get("strategy_object_type", "benefit")
        economics = self.policy["strategy_object_economics"].get(
            object_type, self.policy["strategy_object_economics"]["benefit"]
        )
        annual_fee = float(candidate.get("annual_fee", 0.0)) if object_type == "card_upgrade" else 0.0
        baseline_ltv = self._estimate_ltv(profile, annual_fee)
        retention_rate = float(economics["long_term_retention_rate"])
        p_long_term = p_conversion * retention_rate * (1 - p_unsubscribe)
        immediate_revenue = p_conversion * float(economics["margin_per_conversion"])
        ltv_increment = p_long_term * baseline_ltv * float(economics["ltv_increment_rate"])

        benefit_cost_proxy = float(mapping.get("benefit_unit_cost_proxy", 0.0) or 0.0)
        trigger_probability = p_click if economics["benefit_cost_trigger"] == "click" else p_conversion
        benefit_expected_cost = trigger_probability * benefit_cost_proxy
        contact_cost = float(candidate.get("contact_cost", 0.0) or 0.0)

        risk_level = str(profile.get("risk_level", "low")).lower()
        risk_policy = self.policy["risk"]
        pd_result = candidate.get("pd_risk_score", {})
        pd_from_model = _pd_probability(pd_result)
        default_given_conversion = (
            pd_from_model
            if pd_from_model is not None
            else float(risk_policy["default_probability_given_conversion"].get(risk_level, 0.015))
        )
        expected_credit_loss = (
            p_conversion * default_given_conversion * float(risk_policy["expected_loss_per_default"])
        )
        complaint_probability = _clamp(float(profile.get("complaint_risk", 0.0) or 0.0))
        complaint_expected_loss = complaint_probability * float(risk_policy["complaint_loss"])
        unsubscribe_expected_loss = (
            p_unsubscribe * baseline_ltv * float(risk_policy["unsubscribe_ltv_loss_factor"])
        )

        budget_cost = contact_cost + benefit_expected_cost
        expected_net_value = (
            immediate_revenue
            + ltv_increment
            - budget_cost
            - unsubscribe_expected_loss
            - complaint_expected_loss
            - expected_credit_loss
        )
        breakdown = {
            "immediate_revenue": round(immediate_revenue, 4),
            "ltv_increment": round(ltv_increment, 4),
            "contact_cost": round(contact_cost, 4),
            "benefit_expected_cost": round(benefit_expected_cost, 4),
            "unsubscribe_expected_loss": round(unsubscribe_expected_loss, 4),
            "complaint_expected_loss": round(complaint_expected_loss, 4),
            "credit_expected_loss": round(expected_credit_loss, 4),
            "pd_6m": round(default_given_conversion, 6),
            "pd_source": "pd_risk_model" if pd_from_model is not None else "risk_level_fallback",
            "baseline_ltv": round(baseline_ltv, 4),
        }
        return StrategyValue(
            candidate_id=str(candidate["candidate_id"]),
            expected_net_value=round(expected_net_value, 4),
            budget_cost=round(budget_cost, 4),
            value_density=round(expected_net_value / max(budget_cost, 0.01), 4),
            p_long_term=round(p_long_term, 6),
            breakdown=breakdown,
            policy_version=str(self.policy["policy_version"]),
        )

    def _estimate_ltv(self, profile: dict[str, Any], annual_fee: float) -> float:
        ltv_policy = self.policy["ltv"]
        monthly_spend = max(0.0, float(profile.get("monthly_spend", 0.0) or 0.0))
        months = float(ltv_policy["horizon_months"])
        recurring_margin = monthly_spend * months * float(ltv_policy["interchange_margin_rate"])
        fee_margin = annual_fee * (months / 12) * float(ltv_policy["annual_fee_margin_rate"])
        value_level = str(profile.get("value_level", "medium")).lower()
        risk_level = str(profile.get("risk_level", "low")).lower()
        value_multiplier = float(ltv_policy["value_level_multiplier"].get(value_level, 1.0))
        risk_multiplier = float(ltv_policy["risk_level_multiplier"].get(risk_level, 0.82))
        return max(
            float(ltv_policy["minimum_ltv"]),
            (recurring_margin + fee_margin) * value_multiplier * risk_multiplier,
        )


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _load_campaign_mapping(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["campaign_id"]: row for row in csv.DictReader(handle)}


def _probability(value: object) -> float:
    return _clamp(float(value or 0.0))


def _pd_probability(pd_result: object) -> float | None:
    if not isinstance(pd_result, dict) or not pd_result.get("model_available"):
        return None
    value = pd_result.get("pd_6m")
    if value is None:
        return None
    return _probability(value)


def _clamp(value: float) -> float:
    return max(0.0, min(value, 1.0))
