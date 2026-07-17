"""
反馈事件数据模型。
严格对应 feedback_example.json 的结构，用于标准化 C 端行为数据的收集与回流。
"""

from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List


class ChannelAttribution(BaseModel):
    """渠道归因数据"""
    channel: str = Field(..., description="渠道类型")
    exposure_count: int = Field(..., description="曝光量")
    conversion_count: int = Field(..., description="转化量")
    cost: float = Field(..., description="渠道花费（元）")
    roi: float = Field(..., description="渠道 ROI")


class SegmentPerformance(BaseModel):
    """分片表现数据"""
    segment_id: str = Field(..., description="分片 ID")
    conversion_rate: float = Field(..., description="转化率")
    complaint_rate: float = Field(..., description="投诉率")
    recommendation: str = Field(..., description="策略建议")


class ConversationOutcome(BaseModel):
    """对话结果统计"""
    positive_intent_count: int = Field(..., description="正向意图次数")
    negative_intent_count: int = Field(..., description="负向意图次数")
    top_customer_questions: List[str] = Field(default_factory=list, description="客户高频问题")


class FeedbackMetrics(BaseModel):
    """反馈指标汇总"""
    exposure_count: int = Field(..., description="总曝光量")
    click_count: int = Field(..., description="总点击量")
    conversion_count: int = Field(..., description="总转化量")
    reject_count: int = Field(..., description="拒绝量")
    complaint_count: int = Field(..., description="投诉量")
    cost: float = Field(..., description="总花费（元）")
    revenue: float = Field(..., description="总收入（元）")
    roi: float = Field(..., description="总 ROI")


class FeedbackEvent(BaseModel):
    """
    反馈事件 - 项目三的输出契约。
    用于向 Strategy Agent 和 Knowledge Agent 回流行为与效果数据。
    """
    campaign_id: str = Field(..., description="活动 ID")
    feedback_metrics: FeedbackMetrics = Field(..., description="反馈指标汇总")
    channel_attribution: List[ChannelAttribution] = Field(default_factory=list, description="渠道归因")
    segment_performance: List[SegmentPerformance] = Field(default_factory=list, description="分片表现")
    conversation_outcome: Optional[ConversationOutcome] = Field(None, description="对话结果")
    generated_at: datetime = Field(default_factory=datetime.now, description="生成时间")

    @property
    def conversion_rate(self) -> float:
        """便捷计算转化率"""
        if self.feedback_metrics.exposure_count == 0:
            return 0.0
        return self.feedback_metrics.conversion_count / self.feedback_metrics.exposure_count


class CustomerActionEvent(BaseModel):
    """
    单条客户行为事件。
    用于实时收集单个客户的行为（曝光/点击/转化等），
    后续聚合为 FeedbackEvent。
    """
    customer_id: str = Field(..., description="客户唯一标识")
    campaign_id: str = Field(..., description="活动 ID")
    event_type: str = Field(..., description="事件类型: exposure / click / conversion / reject / complaint")
    channel: str = Field(..., description="触达渠道")
    timestamp: datetime = Field(default_factory=datetime.now, description="事件发生时间")
    metadata: Optional[dict] = Field(default=None, description="扩展字段")

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        allowed = {"exposure", "click", "conversion", "reject", "complaint"}
        if v not in allowed:
            raise ValueError(f"event_type 必须是 {allowed} 之一")
        return v