from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .intent import parse_intent
from .models import CampaignRequest


DEEPSEEK_CHAT_COMPLETIONS_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-v4-pro"
ALLOWED_PRODUCTS = {"installment", "coupon", "travel"}
ALLOWED_CHANNEL_MODES = {"omni", "app", "sms", "wechat"}
LOCAL_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


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
    """Parse an operator goal with DeepSeek, with deterministic fallback for local demos."""
    normalized_goal = goal.strip()
    if not normalized_goal:
        raise ValueError("goal is required")

    _load_local_deepseek_env()
    key = os.getenv("DEEPSEEK_API_KEY", "") if api_key is None else api_key
    model = os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)
    if not key:
        return _fallback_result(normalized_goal, defaults, "api_key_not_configured")

    try:
        response = (sender or _send_deepseek_request)(_build_deepseek_payload(normalized_goal, defaults, model), key)
        parsed = json.loads(_extract_output_text(response))
        if not isinstance(parsed, dict):
            raise ValueError("DeepSeek response must be a JSON object")
        request = _campaign_request_from_model(parsed, normalized_goal, defaults)
        return GoalParseResult(
            campaign_request=request,
            audience_hints=_string_list(parsed.get("audience_hints"), limit=5),
            constraints=_string_list(parsed.get("constraints"), limit=5),
            source="deepseek",
            model=model,
        )
    except HTTPError as exc:
        return _fallback_result(normalized_goal, defaults, f"deepseek_http_{exc.code}")
    except (URLError, TimeoutError):
        return _fallback_result(normalized_goal, defaults, "deepseek_network_or_timeout")
    except (ValueError, json.JSONDecodeError, TypeError, AttributeError):
        return _fallback_result(normalized_goal, defaults, "deepseek_response_validation_failed")


def _load_local_deepseek_env() -> None:
    """Load local DeepSeek settings without overriding process environment variables."""
    if not LOCAL_ENV_FILE.is_file():
        return
    try:
        lines = LOCAL_ENV_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        candidate = line.strip()
        if not candidate or candidate.startswith("#") or "=" not in candidate:
            continue
        name, value = candidate.split("=", 1)
        name = name.strip()
        if name not in {"DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_TIMEOUT_SECONDS"}:
            continue
        if name not in os.environ:
            os.environ[name] = value.strip().strip('"').strip("'")


def _build_deepseek_payload(goal: str, defaults: CampaignRequest, model: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You convert a bank marketing operator's goal into a constrained campaign request. "
                    "Return only one valid json object, with no markdown. "
                    "Use only product values installment, coupon, travel and channel_mode values omni, app, sms, wechat. "
                    "Use the supplied defaults when the operator does not specify budget, risk tolerance, or frequency. "
                    "When product_locked is true, keep the supplied default product exactly and do not infer another product. "
                    "Do not invent eligibility exceptions, customer counts, conversion results, financial promises, or compliance approvals. "
                    "The json object must exactly follow this example shape: "
                    '{"product":"installment","channel_mode":"omni","budget_wan":80,'
                    '"risk_level":2,"frequency_level":2,"audience_hints":["tag"],"constraints":["rule"]}.'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Operator goal: {goal}\n"
                    f"Defaults: product={defaults.product}, channel_mode={defaults.channel_mode}, "
                    f"budget_wan={defaults.budget_wan}, risk_level={defaults.risk_level}, "
                    f"frequency_level={defaults.frequency_level}, product_locked={defaults.product_locked}."
                ),
            },
        ],
        # Goal parsing is a bounded extraction task, so reasoning adds latency without value.
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "max_tokens": 500,
    }


def _send_deepseek_request(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    request = Request(
        DEEPSEEK_CHAT_COMPLETIONS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    timeout = float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "90"))
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_output_text(response: dict[str, Any]) -> str:
    choices = response.get("choices", [])
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and content.strip():
            return content
    raise ValueError("DeepSeek response did not include message content")


def _campaign_request_from_model(
    parsed: dict[str, Any], goal: str, defaults: CampaignRequest
) -> CampaignRequest:
    product = defaults.product if defaults.product_locked else parsed.get("product", defaults.product)
    channel_mode = parsed.get("channel_mode", defaults.channel_mode)
    budget_wan = parsed.get("budget_wan", defaults.budget_wan)
    risk_level = parsed.get("risk_level", defaults.risk_level)
    frequency_level = parsed.get("frequency_level", defaults.frequency_level)
    if product not in ALLOWED_PRODUCTS or channel_mode not in ALLOWED_CHANNEL_MODES:
        raise ValueError("DeepSeek response contained unsupported campaign options")
    if not isinstance(budget_wan, int) or not 1 <= budget_wan <= 200:
        raise ValueError("DeepSeek response contained invalid budget")
    if risk_level not in {1, 2, 3} or frequency_level not in {1, 2, 3, 4}:
        raise ValueError("DeepSeek response contained invalid campaign controls")
    return CampaignRequest(
        goal=goal,
        product=product,
        product_locked=defaults.product_locked,
        channel_mode=channel_mode,
        budget_wan=budget_wan,
        risk_level=risk_level,
        frequency_level=frequency_level,
    )


def _fallback_result(goal: str, defaults: CampaignRequest, reason: str) -> GoalParseResult:
    channel_mode = _infer_channel_mode(goal, defaults.channel_mode)
    budget_wan = _infer_budget_wan(goal, defaults.budget_wan)
    request = CampaignRequest(
        goal=goal,
        product=defaults.product,
        product_locked=defaults.product_locked,
        channel_mode=channel_mode,
        budget_wan=budget_wan,
        risk_level=defaults.risk_level,
        frequency_level=defaults.frequency_level,
    )
    intent = parse_intent(request)
    return GoalParseResult(
        campaign_request=CampaignRequest(
            goal=goal,
            product=intent.product,
            product_locked=defaults.product_locked,
            channel_mode=channel_mode,
            budget_wan=budget_wan,
            risk_level=request.risk_level,
            frequency_level=request.frequency_level,
        ),
        audience_hints=intent.target_signals,
        constraints=intent.constraints,
        source="fallback",
        fallback_reason=reason,
    )


def _infer_channel_mode(goal: str, default: str) -> str:
    if "短信" in goal:
        return "sms"
    if "微信" in goal or "公众号" in goal:
        return "wechat"
    if "app" in goal.lower() or "推送" in goal:
        return "app"
    return default


def _infer_budget_wan(goal: str, default: int) -> int:
    wan_match = re.search(r"(?:预算)?\s*(\d+(?:\.\d+)?)\s*万", goal)
    if wan_match:
        value = int(round(float(wan_match.group(1))))
        return value if 1 <= value <= 200 else default
    yuan_match = re.search(r"(?:预算)?\s*(\d{4,7})\s*元", goal)
    if yuan_match:
        value = int(round(int(yuan_match.group(1)) / 10000))
        return value if 1 <= value <= 200 else default
    return default


def _string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:limit]
