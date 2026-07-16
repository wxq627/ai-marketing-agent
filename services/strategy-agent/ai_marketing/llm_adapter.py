from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .intent import parse_intent
from .models import CampaignRequest


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-4o-mini"
ALLOWED_PRODUCTS = {"installment", "coupon", "travel"}
ALLOWED_CHANNEL_MODES = {"omni", "app", "sms"}


@dataclass(frozen=True)
class GoalParseResult:
    campaign_request: CampaignRequest
    audience_hints: list[str]
    constraints: list[str]
    source: str
    model: str | None = None
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_request": asdict(self.campaign_request),
            "audience_hints": self.audience_hints,
            "constraints": self.constraints,
            "source": self.source,
            "model": self.model,
            "fallback_reason": self.fallback_reason,
        }


def parse_campaign_goal(
    goal: str,
    defaults: CampaignRequest,
    *,
    api_key: str | None = None,
    sender: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
) -> GoalParseResult:
    """Parse an operator goal with OpenAI, with deterministic fallback for local demos."""
    normalized_goal = goal.strip()
    if not normalized_goal:
        raise ValueError("goal is required")

    key = os.getenv("OPENAI_API_KEY", "") if api_key is None else api_key
    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    if not key:
        return _fallback_result(normalized_goal, defaults, "api_key_not_configured")

    try:
        response = (sender or _send_openai_request)(_build_openai_payload(normalized_goal, defaults, model), key)
        parsed = json.loads(_extract_output_text(response))
        request = _campaign_request_from_model(parsed, normalized_goal, defaults)
        return GoalParseResult(
            campaign_request=request,
            audience_hints=_string_list(parsed.get("audience_hints"), limit=5),
            constraints=_string_list(parsed.get("constraints"), limit=5),
            source="openai",
            model=model,
        )
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return _fallback_result(normalized_goal, defaults, "openai_request_failed")


def _build_openai_payload(goal: str, defaults: CampaignRequest, model: str) -> dict[str, Any]:
    return {
        "model": model,
        "instructions": (
            "You convert a bank marketing operator's goal into a constrained campaign request. "
            "Use only the allowed products and channel modes in the JSON schema. "
            "Use the supplied defaults when the operator does not specify budget, risk tolerance, or frequency. "
            "Do not invent eligibility exceptions, customer counts, conversion results, financial promises, or compliance approvals."
        ),
        "input": (
            f"Operator goal: {goal}\n"
            f"Defaults: product={defaults.product}, channel_mode={defaults.channel_mode}, "
            f"budget_wan={defaults.budget_wan}, risk_level={defaults.risk_level}, "
            f"frequency_level={defaults.frequency_level}."
        ),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "campaign_goal_parse",
                "strict": True,
                "schema": _goal_parse_schema(),
            }
        },
    }


def _goal_parse_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "product": {"type": "string", "enum": sorted(ALLOWED_PRODUCTS)},
            "channel_mode": {"type": "string", "enum": sorted(ALLOWED_CHANNEL_MODES)},
            "budget_wan": {"type": "integer", "minimum": 1, "maximum": 200},
            "risk_level": {"type": "integer", "enum": [1, 2, 3]},
            "frequency_level": {"type": "integer", "enum": [1, 2, 3, 4]},
            "audience_hints": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            "constraints": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        },
        "required": [
            "product",
            "channel_mode",
            "budget_wan",
            "risk_level",
            "frequency_level",
            "audience_hints",
            "constraints",
        ],
    }


def _send_openai_request(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    request = Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "15"))
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_output_text(response: dict[str, Any]) -> str:
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    raise ValueError("OpenAI response did not include output_text")


def _campaign_request_from_model(
    parsed: dict[str, Any], goal: str, defaults: CampaignRequest
) -> CampaignRequest:
    product = parsed.get("product", defaults.product)
    channel_mode = parsed.get("channel_mode", defaults.channel_mode)
    budget_wan = parsed.get("budget_wan", defaults.budget_wan)
    risk_level = parsed.get("risk_level", defaults.risk_level)
    frequency_level = parsed.get("frequency_level", defaults.frequency_level)
    if product not in ALLOWED_PRODUCTS or channel_mode not in ALLOWED_CHANNEL_MODES:
        raise ValueError("OpenAI response contained unsupported campaign options")
    if not isinstance(budget_wan, int) or not 1 <= budget_wan <= 200:
        raise ValueError("OpenAI response contained invalid budget")
    if risk_level not in {1, 2, 3} or frequency_level not in {1, 2, 3, 4}:
        raise ValueError("OpenAI response contained invalid campaign controls")
    return CampaignRequest(
        goal=goal,
        product=product,
        channel_mode=channel_mode,
        budget_wan=budget_wan,
        risk_level=risk_level,
        frequency_level=frequency_level,
    )


def _fallback_result(goal: str, defaults: CampaignRequest, reason: str) -> GoalParseResult:
    request = CampaignRequest(
        goal=goal,
        product=defaults.product,
        channel_mode=defaults.channel_mode,
        budget_wan=defaults.budget_wan,
        risk_level=defaults.risk_level,
        frequency_level=defaults.frequency_level,
    )
    intent = parse_intent(request)
    return GoalParseResult(
        campaign_request=CampaignRequest(
            goal=goal,
            product=intent.product,
            channel_mode=request.channel_mode,
            budget_wan=request.budget_wan,
            risk_level=request.risk_level,
            frequency_level=request.frequency_level,
        ),
        audience_hints=intent.target_signals,
        constraints=intent.constraints,
        source="fallback",
        fallback_reason=reason,
    )


def _string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:limit]
