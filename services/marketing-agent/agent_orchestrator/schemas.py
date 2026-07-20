"""
agent_orchestrator\schemas.py
功能描述: 策略包数据模型定义，基于JSON Schema契约实现
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
from datetime import datetime


class CampaignMetadata(BaseModel):
    campaign_id: str
    objective: str
    product: str
    budget: float
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class AudienceSegment(BaseModel):
    segment_id: str
    segment_name: str
    size: int
    priority: float
    features: Optional[List[str]] = None
    expected_conversion_rate: Optional[float] = None
    expected_roi: Optional[float] = None


class BenefitRule(BaseModel):
    benefit_type: str
    benefit_name: str
    eligibility: Optional[List[str]] = None
    limit: Optional[str] = None


class ChannelRoute(BaseModel):
    channel: str
    budget_ratio: float
    contact_order: Optional[int] = None
    retry_rule: Optional[str] = None


class ContentBrief(BaseModel):
    core_message: str
    tone: str
    personalization_fields: Optional[List[str]] = None
    required_disclosure: Optional[List[str]] = None


class ComplianceGuard(BaseModel):
    blocked_words: Optional[List[str]] = None
    must_not_claim: Optional[List[str]] = None
    frequency_limit: Optional[str] = None
    age_restriction: Optional[int] = None


class ExperimentPlan(BaseModel):
    control_group_ratio: Optional[float] = None
    test_group_ratio: Optional[float] = None
    success_metrics: Optional[List[str]] = None


class CallbackConfig(BaseModel):
    feedback_url: Optional[str] = None
    report_interval: Optional[str] = None


class StrategyPackage(BaseModel):
    campaign_metadata: CampaignMetadata
    audience_segments: List[AudienceSegment]
    benefit_rule: Optional[BenefitRule] = None
    channel_routing: List[ChannelRoute]
    content_brief: ContentBrief
    compliance_guard: ComplianceGuard
    experiment_plan: Optional[ExperimentPlan] = None
    callback_config: Optional[CallbackConfig] = None

    @field_validator('channel_routing')
    def validate_channel_routing(cls, v):
        total_ratio = sum(route.budget_ratio for route in v)
        if abs(total_ratio - 1.0) > 0.01:
            raise ValueError(f"渠道预算比例总和必须为1.0，当前为{total_ratio}")
        return v


class ExecutionPlan(BaseModel):
    trace_id: str
    campaign_id: str
    status: str = "pending"
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class DispatchResult(BaseModel):
    success: bool
    trace_id: str
    channel: str
    user_id: str
    content: str
    dispatched_at: datetime = Field(default_factory=datetime.now)
    error_message: Optional[str] = None


class TouchLog(BaseModel):
    oneid: str
    campaign_id: str
    channel: str
    touch_type: str
    content: str
    status: str
    trace_id: str
    created_at: datetime = Field(default_factory=datetime.now)