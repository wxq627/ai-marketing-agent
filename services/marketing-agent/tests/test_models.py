"""
单元测试：验证 Pydantic 模型能正确解析 strategy_package_example.json
"""

import json
import pytest
from pathlib import Path
from app.models.strategy import StrategyPackage
from app.models.events import FeedbackEvent

def test_strategy_package_parsing():
    """测试策略包模型能正确解析示例 JSON"""
    example_path = Path(__file__).parent.parent / "contracts" / "examples" / "strategy_package_example.json"
    print(f"Testing with example file: {example_path}")

    with open(example_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 解析不应抛出异常
    strategy = StrategyPackage.model_validate(data)
    
    # 验证关键字段
    assert strategy.campaign_metadata.campaign_id == "CMP20260715001"
    assert strategy.campaign_metadata.objective == "提升信用卡分期转化"
    assert len(strategy.audience_segments) == 1
    assert strategy.audience_segments[0].segment_id == "SEG001"
    assert len(strategy.channel_routing) == 3
    assert "app_push" in strategy.channels


def test_feedback_event_parsing():
    """测试反馈事件模型能正确解析示例 JSON"""
    example_path = Path(__file__).parent.parent / "contracts" / "examples" / "feedback_example.json"
    
    with open(example_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 解析不应抛出异常
    feedback = FeedbackEvent.model_validate(data)
    
    # 验证关键字段
    assert feedback.campaign_id == "CMP20260715001"
    assert feedback.feedback_metrics.exposure_count == 50000
    assert feedback.feedback_metrics.conversion_count == 820
    assert len(feedback.channel_attribution) == 2


def test_strategy_package_helpers():
    """测试 StrategyPackage 的便捷方法"""
    example_path = Path(__file__).parent.parent / "contracts" / "examples" / "strategy_package_example.json"
    
    with open(example_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    strategy = StrategyPackage.model_validate(data)
    
    # 测试便捷属性
    assert strategy.campaign_id == "CMP20260715001"
    assert strategy.channels == ["app_push", "sms", "wechat"]
    
    # 测试便捷方法
    route = strategy.get_channel_route("app_push")
    assert route is not None
    assert route.budget_ratio == 0.5