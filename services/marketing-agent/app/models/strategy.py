"""
Strategy Package 数据模型。
严格对应 contracts/examples/strategy_package_example.json 的结构。
这是整个项目三的"输入契约"，所有后续逻辑都基于此。
"""

from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List


class CampaignMetadata(BaseModel):
    """活动元数据"""
    campaign_id: str = Field(..., description="活动唯一标识")
    objective: str = Field(..., description="营销目标")
    product: str = Field(..., description="产品名称/编码")
    budget: float = Field(..., description="总预算（元）")
    start_time: datetime = Field(..., description="活动开始时间")
    end_time: datetime = Field(..., description="活动结束时间")

    @field_validator("campaign_id")
    @classmethod
    def validate_campaign_id(cls, v: str) -> str:
        if not v.startswith("CMP"):
            raise ValueError("campaign_id 必须以 'CMP' 开头")
        return v


class AudienceSegment(BaseModel):
    """客群分片定义"""
    segment_id: str = Field(..., description="分片唯一标识")
    segment_name: str = Field(..., description="分片名称")
    size: int = Field(..., description="客群规模")
    priority: float = Field(..., ge=0, le=1, description="优先级权重 0-1")
    features: List[str] = Field(default_factory=list, description="客群特征标签")
    expected_conversion_rate: float = Field(..., ge=0, le=1, description="预期转化率")
    expected_roi: float = Field(..., gt=0, description="预期 ROI")

    @field_validator("segment_id")
    @classmethod
    def validate_segment_id(cls, v: str) -> str:
        if not v.startswith("SEG"):
            raise ValueError("segment_id 必须以 'SEG' 开头")
        return v


class BenefitRule(BaseModel):
    """权益规则"""
    benefit_type: str = Field(..., description="权益类型编码")
    benefit_name: str = Field(..., description="权益名称")
    eligibility: List[str] = Field(default_factory=list, description="领取资格表达式")
    limit: str = Field(..., description="领取限制说明")


class ChannelRoute(BaseModel):
    """渠道路由规则"""
    channel: str = Field(..., description="渠道类型: app_push / sms / wechat / call")
    budget_ratio: float = Field(..., ge=0, le=1, description="预算占比")
    contact_order: int = Field(..., gt=0, description="触达顺序")
    retry_rule: str = Field(..., description="重试/降级规则")

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        allowed = {"app_push", "sms", "wechat", "call"}
        if v not in allowed:
            raise ValueError(f"channel 必须是 {allowed} 之一")
        return v


class ContentBrief(BaseModel):
    """内容简报"""
    core_message: str = Field(..., description="核心传达信息")
    tone: str = Field(..., description="文案语气风格")
    personalization_fields: List[str] = Field(default_factory=list, description="个性化字段")
    required_disclosure: List[str] = Field(default_factory=list, description="必须披露的合规信息")


class ComplianceGuard(BaseModel):
    """合规护栏"""
    blocked_words: List[str] = Field(default_factory=list, description="禁用词列表")
    must_not_claim: List[str] = Field(default_factory=list, description="禁止承诺内容")
    frequency_limit: str = Field(..., description="频控规则描述")


class ExperimentPlan(BaseModel):
    """实验方案"""
    control_group_ratio: float = Field(..., ge=0, le=1, description="对照组占比")
    test_group_ratio: float = Field(..., ge=0, le=1, description="实验组占比")
    success_metrics: List[str] = Field(default_factory=list, description="成功指标")

    @field_validator("control_group_ratio", "test_group_ratio")
    @classmethod
    def validate_ratios(cls, v: float) -> float:
        if v < 0 or v > 1:
            raise ValueError("ratio 必须在 0-1 之间")
        return v


class CallbackConfig(BaseModel):
    """回调配置"""
    feedback_url: str = Field(..., description="反馈接收 URL")
    report_interval: str = Field(..., description="报告间隔: hourly / daily")


class StrategyPackage(BaseModel):
    """
    策略包 - 项目三的完整输入契约。
    对应 Strategy Agent 下发的完整策略包结构。
    """
    campaign_metadata: CampaignMetadata = Field(..., description="活动元数据")
    audience_segments: List[AudienceSegment] = Field(..., description="目标客群分片")
    benefit_rule: BenefitRule = Field(..., description="权益规则")
    channel_routing: list[ChannelRoute] = Field(..., description="渠道路由配置")
    content_brief: ContentBrief = Field(..., description="内容简报")
    compliance_guard: ComplianceGuard = Field(..., description="合规护栏")
    experiment_plan: ExperimentPlan = Field(..., description="实验方案")
    callback_config: CallbackConfig = Field(..., description="回调配置")

    @property
    def campaign_id(self) -> str:
        """便捷访问 campaign_id"""
        return self.campaign_metadata.campaign_id

    @property
    def channels(self) -> list[str]:
        """便捷获取所有渠道列表"""
        return [route.channel for route in self.channel_routing]

    def get_channel_route(self, channel: str) -> Optional[ChannelRoute]:
        """根据渠道类型获取路由配置"""
        for route in self.channel_routing:
            if route.channel == channel:
                return route
        return None