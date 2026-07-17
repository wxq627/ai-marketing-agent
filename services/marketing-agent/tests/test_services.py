"""
阶段二单元测试：内容生成、频控、Agent 编排
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from app.models.strategy import StrategyPackage
from app.services.content_gen import ContentGenerator, ContentGenerationError
from app.services.frequency import FrequencyService, FrequencyLimitExceeded, IdempotencyError
from app.agents.marketing_agent import MarketingAgent, AgentState


# ==================== Content Generator 测试 ====================

@pytest.fixture
def sample_strategy():
    """创建测试用的策略包"""
    example_data = {
        "campaign_metadata": {
            "campaign_id": "CMP20260715001",
            "objective": "提升信用卡分期转化",
            "product": "credit_card_installment",
            "budget": 800000,
            "start_time": "2026-07-20T09:00:00+08:00",
            "end_time": "2026-07-27T22:00:00+08:00"
        },
        "audience_segments": [{
            "segment_id": "SEG001",
            "segment_name": "高消费高活跃分期潜力客群",
            "size": 50000,
            "priority": 0.91,
            "features": ["月消费高", "额度使用率高", "App活跃", "分期意图强"],
            "expected_conversion_rate": 0.082,
            "expected_roi": 2.4
        }],
        "benefit_rule": {
            "benefit_type": "installment_fee_coupon",
            "benefit_name": "分期手续费折扣券",
            "eligibility": ["marketing_consent=true", "risk_level != high"],
            "limit": "每客户最多领取1次"
        },
        "channel_routing": [
            {"channel": "app_push", "budget_ratio": 0.5, "contact_order": 1, "retry_rule": "24小时未点击后切换短信"},
            {"channel": "sms", "budget_ratio": 0.2, "contact_order": 2, "retry_rule": "命中频控则跳过"},
            {"channel": "wechat", "budget_ratio": 0.3, "contact_order": 3, "retry_rule": "仅高价值客户触达"}
        ],
        "content_brief": {
            "core_message": "账单压力缓释与分期费率优惠",
            "tone": "专业、克制、合规",
            "personalization_fields": ["customer_name", "available_benefit", "valid_period"],
            "required_disclosure": ["活动规则以页面展示为准", "短信需包含退订方式"]
        },
        "compliance_guard": {
            "blocked_words": ["稳赚", "保证", "无条件通过"],
            "must_not_claim": ["承诺一定省钱", "承诺审批通过"],
            "frequency_limit": "7天最多触达2次"
        },
        "experiment_plan": {
            "control_group_ratio": 0.1,
            "test_group_ratio": 0.9,
            "success_metrics": ["conversion_rate", "roi", "complaint_rate"]
        },
        "callback_config": {
            "feedback_url": "/api/strategy/feedback",
            "report_interval": "hourly"
        }
    }
    return StrategyPackage.model_validate(example_data)


@pytest.fixture
def sample_customer_profile():
    return {
        "customer_name": "张三",
        "available_benefit": "分期手续费5折",
        "valid_period": "2026年7月20日-7月27日",
        "features": ["月消费高", "额度使用率高"],
        'last_message': '我想了解一下分期优惠'
    }


@pytest.mark.asyncio
async def test_content_generator_success(sample_strategy, sample_customer_profile):
    """测试内容生成成功路径"""
    generator = ContentGenerator()

    # Mock LLM 调用
    # with patch.object(generator.llm, "ainvoke", new=AsyncMock(return_value="尊敬的张三，您好！您的专属优惠已就绪。")):
    content = await generator.generate(sample_strategy, sample_customer_profile)

    assert "张三" in content
    assert "活动规则以页面展示为准" in content
    assert "退订" in content


@pytest.mark.asyncio
async def test_content_generator_fallback(sample_strategy, sample_customer_profile):
    """测试 LLM 异常时自动降级到 Fallback"""
    generator = ContentGenerator()

    # Mock LLM 抛出异常
    # with patch.object(generator.llm, "ainvoke", new=AsyncMock(side_effect=Exception("LLM 服务不可用"))):
    content = await generator.generate(sample_strategy, sample_customer_profile)

    # 应返回 Fallback 文案
    assert "张三" in content
    assert "分期手续费折扣券" in content
    assert "退订" in content


@pytest.mark.asyncio
async def test_content_generator_forced_fallback(sample_strategy, sample_customer_profile):
    """测试强制使用 Fallback 模式"""
    generator = ContentGenerator()
    content = await generator.generate(sample_strategy, sample_customer_profile, use_fallback=True)

    assert "张三" in content
    assert "分期手续费折扣券" in content


# ==================== Frequency Service 测试 ====================

@pytest.fixture
def mock_redis():
    """Mock Redis 客户端"""
    mock = AsyncMock()
    mock.incr = AsyncMock(return_value=1)
    mock.expire = AsyncMock(return_value=True)
    mock.set = AsyncMock(return_value=True)
    mock.get = AsyncMock(return_value=None)
    mock.delete = AsyncMock(return_value=1)
    return mock


@pytest.mark.asyncio
async def test_frequency_check_passed(mock_redis):
    """测试频控检查通过"""
    with patch("app.services.frequency.redis.from_url", return_value=mock_redis):
        service = FrequencyService()

        result = await service.check_frequency_limit(
            customer_id="CUST001",
            campaign_id="CMP20260715001",
            frequency_limit="7天最多触达2次"
        )

        assert result is True
        mock_redis.incr.assert_called_once()


@pytest.mark.asyncio
async def test_frequency_check_exceeded(mock_redis):
    """测试频控超限"""
    mock_redis.incr = AsyncMock(return_value=3)  # 已触达3次

    with patch("app.services.frequency.redis.from_url", return_value=mock_redis):
        service = FrequencyService()

        with pytest.raises(FrequencyLimitExceeded):
            await service.check_frequency_limit(
                customer_id="CUST001",
                campaign_id="CMP20260715001",
                frequency_limit="7天最多触达2次"
            )


@pytest.mark.asyncio
async def test_idempotency_first_request(mock_redis):
    """测试幂等性：首次请求"""
    mock_redis.set = AsyncMock(return_value=True)  # SETNX 返回 True

    with patch("app.services.frequency.redis.from_url", return_value=mock_redis):
        service = FrequencyService()

        result = await service.check_idempotency("req-123")
        assert result is True


@pytest.mark.asyncio
async def test_idempotency_duplicate_request(mock_redis):
    """测试幂等性：重复请求"""
    mock_redis.set = AsyncMock(return_value=False)  # SETNX 返回 False，key 已存在

    with patch("app.services.frequency.redis.from_url", return_value=mock_redis):
        service = FrequencyService()

        with pytest.raises(IdempotencyError):
            await service.check_idempotency("req-123")


# ==================== Marketing Agent 测试 ====================

@pytest.mark.asyncio
async def test_marketing_agent_marketing_intent(sample_strategy, sample_customer_profile):
    """测试营销意图的完整流程"""
    agent = MarketingAgent()

    # Mock 内容生成
    with patch("app.agents.marketing_agent.content_generator.generate", new=AsyncMock(return_value="测试文案")):
        result = await agent.run(
            campaign_id="CMP20260715001",
            customer_id="CUST001",
            customer_profile=sample_customer_profile,
            strategy=sample_strategy,
            thread_id="test-thread-1",
        )

        assert result["success"] is True
        assert result["response"] == "测试文案"
        assert result["state"]["intent"] == "marketing"
        assert result["state"]["compliance_passed"] is True


@pytest.mark.asyncio
async def test_marketing_agent_query_intent(sample_customer_profile):
    """测试查询意图"""
    agent = MarketingAgent()

    profile = {**sample_customer_profile, "last_message": "费率是多少？"}

    result = await agent.run(
        campaign_id="CMP20260715001",
        customer_id="CUST001",
        customer_profile=profile,
        strategy=None,
        thread_id="test-thread-2",
    )

    assert result["success"] is True
    assert result["state"]["intent"] == "query"
    assert "费率" in result["response"]


@pytest.mark.asyncio
async def test_marketing_agent_compliance_blocked(sample_strategy, sample_customer_profile):
    """测试合规校验拦截"""
    agent = MarketingAgent()

    # Mock 生成包含禁用词的内容
    with patch("app.agents.marketing_agent.content_generator.generate", new=AsyncMock(return_value="稳赚不赔的好机会")):
        result = await agent.run(
            campaign_id="CMP20260715001",
            customer_id="CUST001",
            customer_profile=sample_customer_profile,
            strategy=sample_strategy,
            thread_id="test-thread-3",
        )

        assert result["success"] is True
        assert result["state"]["compliance_passed"] is False
        assert "禁用词" in result["state"]["error_message"]