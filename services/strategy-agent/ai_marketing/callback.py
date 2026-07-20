"""
strategy_agent 回调模块：
1. MarketingPlan 字典 → StrategyPackage 字典 的格式转换
2. 生成策略后回调 marketing_agent 推送
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional


# ==================== 配置 ====================

CALLBACK_ENABLED = os.environ.get("SA_CALLBACK_ENABLED", "1") == "1"
CALLBACK_URL = os.environ.get(
    "SA_CALLBACK_URL",
    "http://localhost:8080/api/v3/strategy/receive",
)
CALLBACK_TIMEOUT = int(os.environ.get("SA_CALLBACK_TIMEOUT", "10"))


# ==================== 映射常量 ====================

_PRODUCT_NAME_MAP = {
    "installment": "credit_card_installment",
    "coupon": "consumption_coupon",
    "travel": "travel_benefit",
}

_BENEFIT_TYPE_MAP = {
    "installment": "installment_fee_coupon",
    "coupon": "consumption_coupon_package",
    "travel": "travel_benefit_package",
}

_BENEFIT_NAME_MAP = {
    "installment": "分期手续费折扣券",
    "coupon": "消费券包",
    "travel": "商旅权益包",
}

_CHANNEL_NAME_MAP = {
    "app弹窗": "app_push",
    "app首页": "app_push",
    "push": "app_push",
    "短信": "sms",
    "企微": "wechat",
}


# ==================== 格式转换 ====================

def convert_to_strategy_package(plan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """将 MarketingPlan 字典转换为 StrategyPackage 字典"""
    try:
        campaign_id = plan.get("campaign_id", "")
        request_data = plan.get("request") or {}
        intent_data = plan.get("intent") or {}
        segments_data = plan.get("segments") or []
        channels_data = plan.get("channels") or []
        content_data = plan.get("content") or {}
        compliance_data = plan.get("compliance") or []
        experiment_data = plan.get("experiment") or {}

        product_key = intent_data.get("product") or request_data.get("product") or "installment"
        budget_wan = request_data.get("budget_wan") or 80

        campaign_metadata = {
            "campaign_id": campaign_id,
            "objective": intent_data.get("objective") or "提升转化与ROI",
            "product": _PRODUCT_NAME_MAP.get(product_key, product_key),
            "budget": float(budget_wan) * 10000.0,
            "start_time": None,
            "end_time": None,
        }

        audience_segments = _convert_segments(
            segments_data, plan.get("predicted_roi") or 0.0
        )

        benefit_rule = _convert_benefit_rule(product_key, intent_data, content_data)

        channel_routing = _convert_channel_routing(channels_data)

        content_brief = _convert_content_brief(content_data, intent_data)

        compliance_guard = _convert_compliance_guard(compliance_data, request_data)

        experiment_plan = _convert_experiment_plan(experiment_data)

        callback_config = {
            "feedback_url": "/api/v3/strategy/feedback",
            "report_interval": "hourly",
        }

        return {
            "campaign_metadata": campaign_metadata,
            "audience_segments": audience_segments,
            "benefit_rule": benefit_rule,
            "channel_routing": channel_routing,
            "content_brief": content_brief,
            "compliance_guard": compliance_guard,
            "experiment_plan": experiment_plan,
            "callback_config": callback_config,
        }
    except Exception as e:
        print(f"[callback] 格式转换失败: {e}")
        return None


def _convert_segments(
    segments_data: List[Dict[str, Any]], predicted_roi: float
) -> List[Dict[str, Any]]:
    if not segments_data:
        return [{
            "segment_id": "SEG001",
            "segment_name": "目标客群",
            "size": 0,
            "priority": 0.5,
            "features": [],
            "expected_conversion_rate": 0.0,
            "expected_roi": predicted_roi,
        }]

    total_value = sum(float(seg.get("expected_value_wan") or 0) for seg in segments_data) or 1.0
    result = []
    for idx, seg in enumerate(segments_data, 1):
        value_wan = float(seg.get("expected_value_wan") or 0)
        priority = round(value_wan / total_value, 4) if total_value > 0 else 0.5
        conversion_rate = float(seg.get("conversion_rate") or 0) / 100.0
        result.append({
            "segment_id": f"SEG{idx:03d}",
            "segment_name": seg.get("name") or f"客群{idx}",
            "size": int(seg.get("size") or 0),
            "priority": priority,
            "features": seg.get("reasons") or [],
            "expected_conversion_rate": round(conversion_rate, 4),
            "expected_roi": predicted_roi,
        })
    return result


def _convert_benefit_rule(
    product_key: str, intent_data: Dict[str, Any], content_data: Dict[str, Any]
) -> Dict[str, Any]:
    benefit_name = _BENEFIT_NAME_MAP.get(product_key, "专属权益")
    benefit_type = _BENEFIT_TYPE_MAP.get(product_key, product_key)

    constraints = intent_data.get("constraints") or []
    eligibility = [c for c in constraints if any(k in c for k in ["授权", "频控", "风险", "合规"])]
    if not eligibility:
        eligibility = ["marketing_consent=true", "risk_level != high"]

    return {
        "benefit_type": benefit_type,
        "benefit_name": benefit_name,
        "eligibility": eligibility,
        "limit": "每客户最多领取1次",
    }


def _convert_channel_routing(
    channels_data: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    if not channels_data:
        return [{
            "channel": "app_push",
            "budget_ratio": 1.0,
            "contact_order": 1,
            "retry_rule": "无",
        }]

    sorted_channels = sorted(
        channels_data,
        key=lambda c: float(c.get("budget_share") or 0),
        reverse=True,
    )
    result = []
    total_share = sum(float(c.get("budget_share") or 0) for c in sorted_channels) or 1.0

    for idx, ch in enumerate(sorted_channels, 1):
        raw_channel = ch.get("channel", "")
        channel_name = _CHANNEL_NAME_MAP.get(raw_channel.lower(), raw_channel)
        budget_ratio = float(ch.get("budget_share") or 0) / total_share if total_share > 0 else 0.0
        role = ch.get("role") or ""
        retry_rule = _build_retry_rule(role, channel_name)
        result.append({
            "channel": channel_name,
            "budget_ratio": round(budget_ratio, 4),
            "contact_order": idx,
            "retry_rule": retry_rule,
        })

    total = sum(r["budget_ratio"] for r in result)
    if total > 0 and abs(total - 1.0) > 0.001:
        for r in result:
            r["budget_ratio"] = round(r["budget_ratio"] / total, 4)
    return result


def _build_retry_rule(role: str, channel_name: str) -> str:
    if channel_name == "app_push":
        return "24小时未点击后切换短信"
    if channel_name == "sms":
        return "命中频控则跳过"
    if channel_name == "wechat":
        return "仅高价值客户触达"
    return role or "无"


def _convert_content_brief(
    content_data: Dict[str, Any], intent_data: Dict[str, Any]
) -> Dict[str, Any]:
    explain = content_data.get("explain") or ""
    core_message = intent_data.get("objective") or "提升转化与ROI"
    if "文案依据：" in explain:
        parts = explain.split("；")
        for part in parts:
            if part.startswith("文案依据："):
                core_message = part.replace("文案依据：", "").strip()
                break

    required_disclosure = ["活动规则以页面展示为准", "短信需包含退订方式"]
    if "合规处理：" in explain:
        parts = explain.split("；")
        compliance_part = ""
        for part in parts:
            if part.startswith("合规处理："):
                compliance_part = part.replace("合规处理：", "").strip()
                break
        if compliance_part:
            for item in compliance_part.split("、"):
                item = item.strip()
                if item and item not in required_disclosure:
                    required_disclosure.append(item)

    return {
        "core_message": core_message,
        "tone": "专业、克制、合规",
        "personalization_fields": ["customer_name", "available_benefit", "valid_period"],
        "required_disclosure": required_disclosure,
    }


def _convert_compliance_guard(
    compliance_data: List[Dict[str, Any]], request_data: Dict[str, Any]
) -> Dict[str, Any]:
    blocked_words = ["稳赚", "保证", "无条件", "最高收益", "无条件通过"]
    must_not_claim = ["承诺一定省钱", "承诺审批通过"]

    freq_level = int(request_data.get("frequency_level") or 2)
    freq_map = {
        1: "7天最多触达1次",
        2: "7天最多触达2次",
        3: "7天最多触达3次",
        4: "3天最多触达2次",
    }
    frequency_limit = freq_map.get(freq_level, "7天最多触达2次")

    for item in compliance_data:
        if isinstance(item, dict) and item.get("item") == "内容合规" and item.get("status") == "拦截":
            detail = item.get("detail") or ""
            if "命中：" in detail:
                words_str = detail.replace("命中：", "").strip()
                for w in words_str.split(","):
                    w = w.strip()
                    if w and w not in blocked_words:
                        blocked_words.append(w)

    return {
        "blocked_words": blocked_words,
        "must_not_claim": must_not_claim,
        "frequency_limit": frequency_limit,
        "age_restriction": 18,
    }


def _convert_experiment_plan(experiment_data: Dict[str, Any]) -> Dict[str, Any]:
    control_str = experiment_data.get("control_group") or "10%"
    try:
        control_ratio = float(str(control_str).replace("%", "").strip()) / 100.0
    except (ValueError, AttributeError):
        control_ratio = 0.1
    test_ratio = round(1.0 - control_ratio, 4)
    success_metrics = experiment_data.get("success_metrics") or [
        "conversion_rate", "roi", "complaint_rate"
    ]
    return {
        "control_group_ratio": round(control_ratio, 4),
        "test_group_ratio": test_ratio,
        "success_metrics": success_metrics,
    }


# ==================== 回调推送 ====================

def push_to_marketing_agent(plan_dict: Dict[str, Any]) -> bool:
    """
    将策略转换后推送到 marketing_agent。
    返回是否推送成功。
    """
    if not CALLBACK_ENABLED:
        print("[callback] 回调推送已禁用")
        return False

    strategy_package = convert_to_strategy_package(plan_dict)
    if not strategy_package:
        print("[callback] 格式转换失败，跳过推送")
        return False

    try:
        payload = json.dumps({"strategy": strategy_package}).encode("utf-8")
        req = urllib.request.Request(
            CALLBACK_URL,
            data=payload,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Content-Length": str(len(payload)),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=CALLBACK_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body)
            if result.get("success"):
                print(
                    f"[callback] 策略推送成功: campaign_id={result.get('campaign_id')}"
                )
                return True
            else:
                print(f"[callback] 策略推送失败: {result.get('message') or body}")
                return False
    except urllib.error.HTTPError as e:
        print(f"[callback] 推送 HTTP 错误: {e.code} {e.reason}")
        try:
            print(f"  响应: {e.read().decode('utf-8')[:300]}")
        except Exception:
            pass
        return False
    except Exception as e:
        print(f"[callback] 推送异常: {e}")
        return False
