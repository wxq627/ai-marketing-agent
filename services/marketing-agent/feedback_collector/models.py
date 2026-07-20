"""
feedback_collector\models.py
功能描述: 反馈事件和指标数据模型定义，基于marketing_feedback.schema.json和init.sql
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class FeedbackEvent(BaseModel):
    trace_id: str
    oneid: str
    campaign_id: Optional[str] = None
    event_type: str
    channel: Optional[str] = None
    detail: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


class FeedbackMetrics(BaseModel):
    exposure_count: int = 0
    click_count: int = 0
    conversion_count: int = 0
    reject_count: int = 0
    complaint_count: int = 0
    cost: float = 0.0
    revenue: float = 0.0
    roi: float = 0.0


class ChannelAttribution(BaseModel):
    channel: str
    exposure_count: int = 0
    click_count: int = 0
    conversion_count: int = 0
    cost: float = 0.0
    roi: float = 0.0


class SegmentPerformance(BaseModel):
    segment_id: str
    segment_name: Optional[str] = None
    conversion_rate: float = 0.0
    complaint_rate: float = 0.0
    recommendation: Optional[str] = None


class ConversationOutcome(BaseModel):
    positive_intent_count: int = 0
    negative_intent_count: int = 0
    top_customer_questions: List[str] = Field(default_factory=list)


class CampaignFeedback(BaseModel):
    campaign_id: str
    feedback_metrics: FeedbackMetrics = Field(default_factory=FeedbackMetrics)
    channel_attribution: List[ChannelAttribution] = Field(default_factory=list)
    segment_performance: List[SegmentPerformance] = Field(default_factory=list)
    conversation_outcome: ConversationOutcome = Field(default_factory=ConversationOutcome)


class ConversationSummary(BaseModel):
    conversation_id: str
    session_id: str
    oneid: str
    summary: str
    intent: Optional[str] = None
    sentiment: Optional[str] = None
    top_concerns: List[str] = Field(default_factory=list)
    recommended_action: Optional[str] = None
    generated_at: datetime = Field(default_factory=datetime.now)


class ReflowRecord(BaseModel):
    record_id: str
    source: str
    target: str
    data: Dict[str, Any]
    status: str = "pending"
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    processed_at: Optional[datetime] = None


class ReflowStatus(BaseModel):
    total_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    pending_count: int = 0
    last_processed_at: Optional[datetime] = None