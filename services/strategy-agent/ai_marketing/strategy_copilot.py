from __future__ import annotations

import csv
import json
import os
import re
from ast import literal_eval
from pathlib import Path
from typing import Any

from .llm_adapter import DEFAULT_MODEL, _extract_output_text, _load_local_deepseek_env, _send_deepseek_request


SERVICE_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
STRUCTURED_DATA_DIR = REPOSITORY_ROOT / "mock_data" / "structured"
POSTER_DIR = REPOSITORY_ROOT / "mock_data" / "unstructured" / "posters"
CAMPAIGN_MAPPING_PATH = SERVICE_DIR / "config" / "campaign_offer_mapping.csv"


CHANNEL_LABELS = {
    "app": "App Push",
    "sms": "短信",
    "wechat": "微信公众号",
    "email": "邮件",
    "phone": "电话外呼",
}


# These terms describe how the operator targeted the campaign, not what a customer
# should ever see in a marketing notification.
_INTERNAL_COPY_PATTERNS = (
    "预算",
    "高意图",
    "低风险",
    "中风险",
    "高风险",
    "高价值",
    "消费增长",
    "高活跃",
    "目标客群",
    "筛选条件",
    "风险等级",
    "人群标签",
    "策略",
    "投放",
    "转化率",
    "评分",
    "运营",
)


def review_strategy(
    *,
    goal: str,
    configuration: dict[str, Any],
    channel_metrics: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Give operators a bounded, explainable review before running optimization."""
    context = _context(goal, configuration, channel_metrics)
    response = _ask_json(
        system=(
            "You are an AI copilot for a financial marketing operator. Review a proposed strategy, "
            "but do not make financial promises or claim a model result that was not supplied. "
            "Return JSON only with summary, opportunities, risks, pending_questions, actions. "
            "Return no more than three items in total across all lists, and keep every item to one concise Chinese sentence. Pending questions must be decision inputs "
            "that materially change the strategy, not generic questions. Actions must be a concrete adjustment "
            "the operator can make in the configuration. Refer to supplied cost evidence when useful."
        ),
        user=f"Strategy context:\n{json.dumps(context, ensure_ascii=False)}",
    )
    if response:
        return {
            "source": "deepseek",
            "model": os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL),
            "summary": _text(response.get("summary")),
            "opportunities": _text_list(response.get("opportunities")),
            "risks": _text_list(response.get("risks")),
            "pending_questions": _text_list(response.get("pending_questions")),
            "actions": _text_list(response.get("actions")),
            "evidence": _evidence(configuration, channel_metrics),
        }
    return _fallback_review(configuration, channel_metrics)


def answer_follow_up(
    *,
    question: str,
    suggestion: str,
    configuration: dict[str, Any],
    channel_metrics: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not question.strip():
        raise ValueError("question is required")
    context = _context("", configuration, channel_metrics)
    response = _ask_json(
        system=(
            "You are an AI copilot for a financial marketing operator. Answer one follow-up question "
            "about the supplied strategy and evidence. Return JSON only: {\"answer\":\"...\"}. "
            "Be concise, explain assumptions, and do not promise outcomes."
        ),
        user=(
            f"Strategy context:\n{json.dumps(context, ensure_ascii=False)}\n"
            f"Suggestion being questioned: {suggestion}\nQuestion: {question}"
        ),
    )
    if response and _text(response.get("answer")):
        return {"source": "deepseek", "answer": _text(response.get("answer"))}
    return {
        "source": "fallback",
        "answer": _fallback_answer(question, configuration, channel_metrics),
    }


def draft_channel_content(
    *,
    configuration: dict[str, Any],
    channels: list[str],
) -> dict[str, Any]:
    selected_channels = [channel for channel in channels if channel in CHANNEL_LABELS]
    if not selected_channels:
        selected_channels = ["app", "sms"]
    campaign_brief = _campaign_brief(configuration)
    response = _ask_json(
        system=(
            "You draft natural, compliant Chinese financial marketing copy. Return JSON only with a "
            "content object whose keys are the supplied channel codes. Write as a customer would actually "
            "receive it, never as an internal strategy report. Never mention or paraphrase budget, customer "
            "segments, high intent, risk level, scoring, age filters, targeting rules, or operator instructions. "
            "Do not promise approval, guaranteed savings, or invented numbers. The campaign brief is the only source "
            "of the activity topic, benefits, rules, validity, and call to action. The audience creative brief may only "
            "adjust tone and must never replace the campaign topic or benefits. Every channel draft must explicitly name the supplied campaign_name. Each channel must be materially different: app is one natural, "
            "concise 25-55 Chinese-character notification with a light action, without a forced line break; sms is under 70 Chinese "
            "characters and includes an opt-out reminder; wechat has a headline and two concise paragraphs; email "
            "has a subject and a complete body; phone is a natural spoken invitation. Mention conditions and validity "
            "only as a brief neutral reminder."
        ),
        user=(
            f"Configuration: {json.dumps(_content_context(configuration), ensure_ascii=False)}\n"
            f"Channels: {selected_channels}"
        ),
    )
    content = response.get("content") if response else None
    if isinstance(content, dict):
        sanitized = {channel: _text(content.get(channel)) for channel in selected_channels}
        sanitized = {
            channel: _normalize_channel_copy(channel, copy, configuration)
            for channel, copy in sanitized.items()
        }
        if (
            all(sanitized.values())
            and not any(_contains_internal_strategy_text(copy) for copy in sanitized.values())
            and all(_mentions_campaign(copy, campaign_brief) for copy in sanitized.values())
        ):
            return {"source": "deepseek", "content": sanitized}
    return {"source": "fallback", "content": _fallback_content(configuration, selected_channels)}


def _ask_json(*, system: str, user: str) -> dict[str, Any] | None:
    _load_local_deepseek_env()
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return None
    payload = {
        "model": os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "max_tokens": 700,
    }
    try:
        value = json.loads(_extract_output_text(_send_deepseek_request(payload, api_key)))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _context(goal: str, configuration: dict[str, Any], channel_metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "operator_goal": goal.strip(),
        "configuration": _content_context(configuration),
        "channel_evidence": _evidence(configuration, channel_metrics),
    }


def _content_context(configuration: dict[str, Any]) -> dict[str, Any]:
    campaign_brief = _campaign_brief(configuration)
    return {
        "campaign_name": campaign_brief["campaign_name"],
        "campaign_brief": campaign_brief,
        "audience_creative_brief": _audience_creative_brief(configuration),
        "channels": _selected_channels(_text(configuration.get("channel_mode"))),
        "compliance_reminder": "活动以页面展示的适用条件和有效期为准",
    }


def _evidence(configuration: dict[str, Any], channel_metrics: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = []
    for channel in _selected_channels(_text(configuration.get("channel_mode"))):
        canonical = "app_push" if channel == "app" else channel
        metrics = channel_metrics.get(canonical, {})
        evidence.append(
            {
                "channel": CHANNEL_LABELS[channel],
                "cost_per_send": metrics.get("cost_per_send"),
                "daily_capacity": metrics.get("daily_capacity"),
            }
        )
    return evidence


def _fallback_review(configuration: dict[str, Any], channel_metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    channels = _selected_channels(_text(configuration.get("channel_mode")))
    opportunities = ["先以合规候选池和预期净价值筛选名单，再由运营确认投放节奏。"]
    risks: list[str] = []
    pending_questions: list[str] = []
    actions = ["确认活动、客群、预算与渠道后，再生成可发布策略。"]
    if not channels:
        pending_questions.append("尚未限定投放渠道，是否允许系统在全部合规渠道中优化？")
    if "phone" in channels:
        phone_cost = channel_metrics.get("phone", {}).get("cost_per_send", 0)
        risks.append(f"电话外呼单次成本约为 {phone_cost} 元，建议保留小规模覆盖试投并观察后续反馈。")
    if len(channels) > 1 and bool(configuration.get("channel_coverage_trial")):
        opportunities.append("已开启多渠道覆盖试投，可同时保留渠道样本并比较后续增量表现。")
    if _target_segments(configuration) == ["auto"]:
        pending_questions.append("目标客群仍为自动圈选，是否需要优先限定高价值或高意图人群？")
    if not risks:
        risks.append("策略效果仍需以实际反馈验证，当前结果是基于历史响应和价值规则的预测。")
    return {
        "source": "fallback",
        "model": None,
        "summary": "AI 已完成策略预审，建议在生成前确认约束与文案。",
        "opportunities": opportunities[:3],
        "risks": risks[:3],
        "pending_questions": pending_questions[:3],
        "actions": actions[:3],
        "evidence": _evidence(configuration, channel_metrics),
    }


def _fallback_answer(question: str, configuration: dict[str, Any], channel_metrics: dict[str, dict[str, Any]]) -> str:
    if "电话" in question:
        cost = channel_metrics.get("phone", {}).get("cost_per_send", 0)
        return f"电话外呼的单次成本约为 {cost} 元，适合在已授权且高价值或高意图人群中做小规模试投；其余预算仍由价值优化器分配。"
    if "渠道" in question:
        return "渠道只是候选范围；最终是否入选还会受到客户授权、频控、容量、预测响应与预期净价值共同约束。"
    if "客群" in question:
        return "可先用目标客群约束缩小候选池，再由模型与价值公式在该范围内排序，避免只按单一标签投放。"
    return "当前建议基于预算、渠道成本、合规约束和运营配置生成。你可以修改任一配置后点击“AI 重新评估”，比较新的建议。"


def _fallback_content(configuration: dict[str, Any], channels: list[str]) -> dict[str, str]:
    campaign_brief = _campaign_brief(configuration)
    campaign = campaign_brief["campaign_name"]
    style = _audience_creative_brief(configuration)
    hook = _copy_hook(campaign_brief, style)
    action = campaign_brief["cta_text"] or "查看详情"
    app_benefit = _copy_benefit(campaign_brief, item_limit=2, character_limit=42)
    short_benefit = _copy_benefit(campaign_brief, item_limit=1, character_limit=26)
    long_benefit = _copy_benefit(campaign_brief, item_limit=3, character_limit=90)
    templates = {
        "app": f"{hook}，{app_benefit}。打开 App {action}。",
        "sms": f"【信用卡服务】{campaign}已上线，{short_benefit}。打开App{action}，回复TD退订。",
        "wechat": (
            f"{campaign}｜权益上新\n\n"
            f"{long_benefit}。{action}，了解参与方式。\n\n"
            "活动适用条件及有效期以页面展示为准。"
        ),
        "email": (
            f"主题：{campaign}活动权益已上线\n\n"
            "您好：\n"
            f"{long_benefit}。我们已将本次活动的参与方式整理在活动页中，欢迎按需查看。\n\n"
            "具体适用条件、费用说明及有效期以页面展示为准。"
        ),
        "phone": (
            f"您好，这里是信用卡服务。{campaign}活动已经上线，{short_benefit}。"
            f"现在方便用一分钟{action}并了解活动适用条件吗？"
        ),
    }
    return {channel: templates[channel] for channel in channels}


def _normalize_channel_copy(channel: str, copy: str, configuration: dict[str, Any]) -> str:
    """Reject internal-sounding copy and keep each channel close to its real format."""
    normalized = re.sub(r"[ \t]+", " ", copy.replace("\r", "").strip())
    if not normalized or _contains_internal_strategy_text(normalized):
        return ""
    if channel == "app":
        return _ensure_app_copy(normalized, configuration)
    if channel == "sms":
        if len(normalized) > 70 or "退订" not in normalized:
            return ""
    elif channel == "wechat" and ("\n" not in normalized or len(normalized) < 35):
        return ""
    elif channel == "email" and ("主题" not in normalized or len(normalized) < 45):
        return ""
    elif channel == "phone" and (len(normalized) < 25 or len(normalized) > 100):
        return ""
    return normalized


def _ensure_app_copy(copy: str, configuration: dict[str, Any]) -> str:
    """App Push should read like a brief notification, not an internal campaign brief."""
    normalized = copy.strip()
    if 20 <= len(normalized) <= 85:
        return normalized
    return _fallback_content(configuration, ["app"])["app"]


def _contains_internal_strategy_text(copy: str) -> bool:
    if any(pattern in copy for pattern in _INTERNAL_COPY_PATTERNS):
        return True
    return bool(re.search(r"\d+(?:\.\d+)?\s*万(?:元)?", copy))


def _audience_creative_brief(configuration: dict[str, Any]) -> dict[str, str]:
    """Use audience filters for tone only; campaign data owns the activity proposition."""
    filters = configuration.get("operator_filters")
    filters = filters if isinstance(filters, dict) else {}
    segments = set(_target_segments(configuration))
    age_max = _as_optional_int(filters.get("age_max"))
    age_min = _as_optional_int(filters.get("age_min"))

    young = "young_new" in segments or (age_max is not None and age_max <= 32)
    premium = "high_value" in segments or "high" in set(filters.get("value_levels", []))
    quiet = "dormant" in segments or "sleep" in set(filters.get("lifecycle_stages", []))
    if young:
        tone = "年轻轻快，简洁有活力，可使用上新、福利、去看看等自然表达"
        tone_key = "young"
    elif premium:
        tone = "克制有品质，强调专属体验与从容安排，不使用夸张促销词"
        tone_key = "premium"
    elif quiet:
        tone = "温和、低打扰，以重新发现权益为主，不制造紧迫感"
        tone_key = "quiet"
    else:
        tone = "自然、可信、简洁，像日常服务提醒"
        tone_key = "neutral"

    if age_min is not None and age_min >= 45 and tone_key == "neutral":
        tone, tone_key = "稳重清晰，突出实用权益与规则透明", "mature"
    return {"tone": tone, "tone_key": tone_key}


def _copy_hook(campaign_brief: dict[str, Any], style: dict[str, str]) -> str:
    campaign = str(campaign_brief["campaign_name"])
    if style["tone_key"] == "young":
        return f"{campaign}福利上新啦"
    if style["tone_key"] == "premium":
        return f"{campaign}专享权益已上线"
    if style["tone_key"] == "quiet":
        return f"好久不见，{campaign}来了"
    return f"{campaign}活动已上线"


def _copy_benefit(
    campaign_brief: dict[str, Any],
    *,
    item_limit: int = 2,
    character_limit: int = 60,
) -> str:
    highlights = [str(item).strip() for item in campaign_brief.get("benefit_highlights", []) if str(item).strip()]
    if highlights:
        return _truncate_text("；".join(highlights[:item_limit]), character_limit)
    return "本期活动权益已为你准备好"


def _mentions_campaign(copy: str, campaign_brief: dict[str, Any]) -> bool:
    campaign_name = _text(campaign_brief.get("campaign_name"))
    return bool(campaign_name and campaign_name in copy)


def _campaign_brief(configuration: dict[str, Any]) -> dict[str, Any]:
    """Consolidate Project A's campaign catalog, benefit pool, and poster introduction for copywriting."""
    campaign_id = _text(configuration.get("campaign_id"))
    catalog = _read_csv_by_key(STRUCTURED_DATA_DIR / "campaign_catalog.csv", "campaign_id")
    mapping = _read_csv_by_key(CAMPAIGN_MAPPING_PATH, "campaign_id")
    benefits = _read_csv_by_key(STRUCTURED_DATA_DIR / "benefit_catalog.csv", "benefit_id")
    catalog_entry = catalog.get(campaign_id, {})
    poster = _poster_for_campaign(campaign_id)
    mapping_entry = mapping.get(campaign_id, {})

    campaign_name = _text(poster.get("activity_name")) or _text(catalog_entry.get("campaign_name"))
    campaign_name = campaign_name or _text(configuration.get("campaign_name")) or "本期活动"
    benefit_ids = _split_pipe_values(mapping_entry.get("primary_benefit_ids", ""))
    benefit_names = [
        _text(benefits[benefit_id].get("benefit_name"))
        for benefit_id in benefit_ids
        if benefit_id in benefits and _text(benefits[benefit_id].get("benefit_name"))
    ]
    poster_rules = poster.get("rules_summary")
    catalog_rules = _rule_highlights(catalog_entry.get("rules", ""))
    highlights = _deduplicate_texts(
        [str(item) for item in poster_rules] if isinstance(poster_rules, list) else []
    )
    if not highlights:
        highlights = _deduplicate_texts(catalog_rules + benefit_names)

    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "headline": _text(poster.get("sub_title")) or _text(poster.get("main_title")),
        "benefit_highlights": highlights[:3],
        "benefit_names": benefit_names[:3],
        "validity": _validity_text(poster, catalog_entry),
        "cta_text": _text(poster.get("cta_text")),
        "source": "project1_campaign_catalog_and_poster",
    }


def _poster_for_campaign(campaign_id: str) -> dict[str, Any]:
    if not campaign_id or not POSTER_DIR.exists():
        return {}
    for path in POSTER_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and _text(payload.get("campaign_id")) == campaign_id:
            return payload
    return {}


def _read_csv_by_key(path: Path, key: str) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row[key]: row
            for row in csv.DictReader(handle)
            if _text(row.get(key))
        }


def _rule_highlights(raw_rules: str) -> list[str]:
    if not raw_rules:
        return []
    try:
        value = literal_eval(raw_rules)
    except (SyntaxError, ValueError):
        return []
    if not isinstance(value, dict):
        return []
    highlights: list[str] = []
    for key, detail in value.items():
        if isinstance(detail, list):
            rendered = "、".join(str(item) for item in detail)
        else:
            rendered = str(detail)
        highlights.append(f"{key}{rendered}" if key and rendered else rendered)
    return highlights


def _validity_text(poster: dict[str, Any], catalog_entry: dict[str, str]) -> str:
    start = _text(poster.get("start_date")) or _text(catalog_entry.get("start_date"))
    end = _text(poster.get("end_date")) or _text(catalog_entry.get("end_date"))
    return f"{start}至{end}" if start and end else ""


def _split_pipe_values(value: str) -> list[str]:
    return [item.strip() for item in value.split("|") if item.strip()]


def _deduplicate_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = _text(value)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _truncate_text(value: str, character_limit: int) -> str:
    if len(value) <= character_limit:
        return value
    return f"{value[: max(1, character_limit - 1)].rstrip('，；、 ')}…"


def _as_optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _selected_channels(channel_mode: str) -> list[str]:
    if not channel_mode or channel_mode == "omni":
        return []
    return [part for part in channel_mode.split("_") if part in CHANNEL_LABELS]


def _target_segments(configuration: dict[str, Any]) -> list[str]:
    raw = configuration.get("target_segments")
    if isinstance(raw, list):
        values = list(dict.fromkeys(_text(item) for item in raw if _text(item)))
        if values:
            return ["auto"] if "auto" in values else values
    value = _text(configuration.get("target_segment"))
    return [value] if value else ["auto"]


def _audience_phrase(target_segments: list[str]) -> str:
    labels = {
        "high_value": "核心价值客户",
        "high_intent": "高意图客户",
        "dormant": "待唤醒客户",
        "young_new": "年轻或新户客户",
        "high_activity": "高活跃客户",
        "spend_growth": "消费增长客户",
        "benefit_sensitive": "权益敏感客户",
        "low_risk": "低风险可转化客户",
    }
    if target_segments == ["auto"]:
        return "目标客户"
    return "、".join(labels.get(segment, "目标客户") for segment in target_segments)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)][:3]
