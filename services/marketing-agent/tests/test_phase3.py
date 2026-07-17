"""
阶段三单元测试：渠道适配器 + Celery 任务
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.channel import (
    ChannelService,
    ChannelType,
    SendResult,
    MockAppPushAdapter,
    MockSmsAdapter,
    MockWechatAdapter,
)
from app.tasks.execution_tasks import execute_campaign_task, batch_dispatch_task


# ==================== Channel Service 测试 ====================

@pytest.mark.asyncio
async def test_channel_send_app_push():
    """测试 App Push 渠道发送"""
    service = ChannelService()
    result = await service.send(
        channel=ChannelType.APP_PUSH.value,
        customer_id="CUST001",
        content="测试推送内容",
    )

    assert result.success is True
    assert result.channel == "app_push"
    assert result.message_id is not None


@pytest.mark.asyncio
async def test_channel_send_sms():
    """测试短信渠道发送"""
    service = ChannelService()
    result = await service.send(
        channel=ChannelType.SMS.value,
        customer_id="CUST001",
        content="测试短信内容",
    )

    assert result.success is True
    assert result.channel == "sms"


@pytest.mark.asyncio
async def test_channel_send_unsupported():
    """测试不支持的渠道类型"""
    service = ChannelService()

    with pytest.raises(ValueError, match="不支持的渠道类型"):
        await service.send(
            channel="email",
            customer_id="CUST001",
            content="测试内容",
        )


@pytest.mark.asyncio
async def test_channel_send_exception_handling():
    """测试渠道发送异常时返回失败结果而非抛出异常"""
    service = ChannelService()

    # 替换适配器为会抛异常的 Mock
    broken_adapter = AsyncMock()
    broken_adapter.send = AsyncMock(side_effect=ConnectionError("网络断开"))
    service.register_adapter("app_push", broken_adapter)

    result = await service.send(
        channel="app_push",
        customer_id="CUST001",
        content="测试内容",
    )

    assert result.success is False
    assert result.error_code == "CHANNEL_ERROR"
    assert "网络断开" in result.error_message


@pytest.mark.asyncio
async def test_register_custom_adapter():
    """测试注册自定义适配器"""
    service = ChannelService()

    class CustomAdapter(MockAppPushAdapter):
        async def send(self, customer_id, content, metadata):
            return SendResult(success=True, channel="custom", message_id="custom_001")

    service.register_adapter("custom", CustomAdapter())
    result = await service.send("custom", "CUST001", "测试")

    assert result.success is True
    assert result.channel == "custom"


# ==================== Celery Task 测试 ====================

@pytest.fixture
def sample_strategy_data():
    """策略包字典（可直接传给 Celery 任务）"""
    return {
        "campaign_metadata": {
            "campaign_id": "CMP20260715001",
            "objective": "提升信用卡分期转化",
            "product": "credit_card_installment",
            "budget": 800000,
            "start_time": "2026-07-20T09:00:00+08:00",
            "end_time": "2026-07-27T22:00:00+08:00",
        },
        "audience_segments": [{
            "segment_id": "SEG001", "segment_name": "测试客群", "size": 100,
            "priority": 0.9, "features": [], "expected_conversion_rate": 0.08, "expected_roi": 2.0,
        }],
        "benefit_rule": {
            "benefit_type": "coupon", "benefit_name": "折扣券",
            "eligibility": [], "limit": "每客户1次",
        },
        "channel_routing": [
            {"channel": "app_push", "budget_ratio": 0.5, "contact_order": 1, "retry_rule": "无"},
        ],
        "content_brief": {
            "core_message": "分期优惠", "tone": "专业",
            "personalization_fields": ["customer_name"],
            "required_disclosure": ["活动规则以页面展示为准"],
        },
        "compliance_guard": {
            "blocked_words": ["稳赚"], "must_not_claim": [], "frequency_limit": "7天最多触达2次",
        },
        "experiment_plan": {
            "control_group_ratio": 0.1, "test_group_ratio": 0.9, "success_metrics": ["roi"],
        },
        "callback_config": {"feedback_url": "/api/feedback", "report_interval": "hourly"},
    }


@pytest.fixture
def sample_customer():
    return {
        "customer_id": "CUST001",
        "profile": {
            "customer_name": "张三",
            "available_benefit": "5折券",
            "valid_period": "2026-07-27",
            "features": ["高消费"],
        },
    }


def test_execute_campaign_task_success(sample_strategy_data, sample_customer):
    """测试触达任务成功执行"""
    # Mock 所有外部依赖
    with patch("app.tasks.execution_tasks.frequency_service_sync_check") as mock_freq, \
         patch("app.tasks.execution_tasks.content_generator.generate", new=AsyncMock(return_value="生成的文案")), \
         patch("app.tasks.execution_tasks.channel_service.send", new=AsyncMock(
             return_value=SendResult(success=True, channel="app_push", message_id="msg_001")
         )):

        # Celery 任务在 eager 模式下同步执行
        execute_campaign_task.apply(args=[
            sample_strategy_data,
            sample_customer["customer_id"],
            sample_customer["profile"],
            "app_push",
        ])

        result = execute_campaign_task.apply(args=[
            sample_strategy_data,
            sample_customer["customer_id"],
            sample_customer["profile"],
            "app_push",
        ]).get()

        assert result["success"] is True
        assert result["message_id"] == "msg_001"
        assert result["campaign_id"] == "CMP20260715001"


def test_execute_campaign_task_frequency_exceeded(sample_strategy_data, sample_customer):
    """测试频控超限时任务跳过且不重试"""
    from app.services.frequency import FrequencyLimitExceeded

    with patch("app.tasks.execution_tasks.frequency_service_sync_check",
               side_effect=FrequencyLimitExceeded("超限")):

        result = execute_campaign_task.apply(args=[
            sample_strategy_data,
            sample_customer["customer_id"],
            sample_customer["profile"],
            "app_push",
        ]).get()

        assert result["success"] is False
        assert result["skipped"] is True
        assert result["skip_reason"] == "frequency_limit_exceeded"


def test_batch_dispatch_task(sample_strategy_data, sample_customer):
    """测试批量分发任务"""
    customer_list = [sample_customer] * 3  # 3个客户

    with patch("app.tasks.execution_tasks.execute_campaign_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="mock-task-id")

        result = batch_dispatch_task.apply(args=[
            sample_strategy_data,
            customer_list,
        ]).get()

        assert result["campaign_id"] == "CMP20260715001"
        # 3个客户 × 1个渠道 = 3个子任务
        assert result["dispatched_count"] == 3
        assert mock_delay.call_count == 3