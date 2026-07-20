"""
feedback_collector\collector.py
功能描述: 反馈采集器，处理API-C4（用户交互事件）和API-C5（对话摘要）接口
"""

import json
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from .models import FeedbackEvent, CampaignFeedback, FeedbackMetrics, ChannelAttribution
from common.logger import logger
from common.errors import FeedbackError


class FeedbackCollector:
    def __init__(self):
        self._events: List[FeedbackEvent] = []
        self._event_file_path = Path("./logs/feedback_events.json")
        self._campaign_feedback_cache: Dict[str, CampaignFeedback] = {}

    def collect_event(self, trace_id: str, oneid: str, event_type: str,
                      campaign_id: Optional[str] = None, channel: Optional[str] = None,
                      detail: Optional[Dict[str, Any]] = None) -> FeedbackEvent:
        event = FeedbackEvent(
            trace_id=trace_id,
            oneid=oneid,
            campaign_id=campaign_id,
            event_type=event_type,
            channel=channel,
            detail=detail or {},
            timestamp=datetime.now()
        )

        self._events.append(event)
        self._update_campaign_metrics(event)
        self._persist_event(event)

        logger.info(f"反馈事件采集成功: event_type={event_type}, trace_id={trace_id}, oneid={oneid}")
        return event

    def collect_user_interaction(self, trace_id: str, oneid: str, interaction_type: str,
                                 campaign_id: Optional[str] = None, channel: Optional[str] = None,
                                 detail: Optional[Dict[str, Any]] = None) -> FeedbackEvent:
        valid_types = ["click", "reject", "complaint", "view", "share"]
        if interaction_type not in valid_types:
            raise FeedbackError(f"无效的用户交互类型: {interaction_type}, 有效类型: {valid_types}")

        return self.collect_event(
            trace_id=trace_id,
            oneid=oneid,
            event_type=f"user_{interaction_type}",
            campaign_id=campaign_id,
            channel=channel,
            detail=detail
        )

    def collect_delivery_event(self, trace_id: str, oneid: str, delivery_status: str,
                               campaign_id: Optional[str] = None, channel: Optional[str] = None,
                               detail: Optional[Dict[str, Any]] = None) -> FeedbackEvent:
        valid_status = ["delivered", "failed", "opened", "converted"]
        if delivery_status not in valid_status:
            raise FeedbackError(f"无效的投递状态: {delivery_status}, 有效状态: {valid_status}")

        return self.collect_event(
            trace_id=trace_id,
            oneid=oneid,
            event_type=f"delivery_{delivery_status}",
            campaign_id=campaign_id,
            channel=channel,
            detail=detail
        )

    def _update_campaign_metrics(self, event: FeedbackEvent):
        if not event.campaign_id:
            return

        if event.campaign_id not in self._campaign_feedback_cache:
            self._campaign_feedback_cache[event.campaign_id] = CampaignFeedback(campaign_id=event.campaign_id)

        feedback = self._campaign_feedback_cache[event.campaign_id]

        if event.event_type == "delivery_delivered":
            feedback.feedback_metrics.exposure_count += 1
        elif event.event_type == "user_click":
            feedback.feedback_metrics.click_count += 1
        elif event.event_type == "delivery_converted":
            feedback.feedback_metrics.conversion_count += 1
        elif event.event_type == "user_reject":
            feedback.feedback_metrics.reject_count += 1
        elif event.event_type == "user_complaint":
            feedback.feedback_metrics.complaint_count += 1

        if event.channel:
            attribution = next((a for a in feedback.channel_attribution if a.channel == event.channel), None)
            if not attribution:
                attribution = ChannelAttribution(channel=event.channel)
                feedback.channel_attribution.append(attribution)

            if event.event_type == "delivery_delivered":
                attribution.exposure_count += 1
            elif event.event_type == "user_click":
                attribution.click_count += 1
            elif event.event_type == "delivery_converted":
                attribution.conversion_count += 1

        self._recalculate_roi(feedback.feedback_metrics)
        for attr in feedback.channel_attribution:
            self._recalculate_roi(attr)

    def _recalculate_roi(self, metrics: FeedbackMetrics):
        if metrics.cost > 0:
            metrics.roi = round(metrics.revenue / metrics.cost, 2) if metrics.revenue > 0 else 0.0
        else:
            metrics.roi = 0.0

    def _persist_event(self, event: FeedbackEvent):
        self._event_file_path.parent.mkdir(parents=True, exist_ok=True)

        events_data = []
        if self._event_file_path.exists():
            try:
                with open(self._event_file_path, 'r', encoding='utf-8') as f:
                    events_data = json.load(f)
            except json.JSONDecodeError:
                events_data = []

        events_data.append(event.model_dump())

        with open(self._event_file_path, 'w', encoding='utf-8') as f:
            json.dump(events_data, f, ensure_ascii=False, indent=2, default=str)

    def get_campaign_feedback(self, campaign_id: str) -> Optional[CampaignFeedback]:
        return self._campaign_feedback_cache.get(campaign_id)

    def get_all_campaign_feedbacks(self) -> List[CampaignFeedback]:
        return list(self._campaign_feedback_cache.values())

    def get_events_by_oneid(self, oneid: str) -> List[FeedbackEvent]:
        return [e for e in self._events if e.oneid == oneid]

    def get_events_by_trace_id(self, trace_id: str) -> List[FeedbackEvent]:
        return [e for e in self._events if e.trace_id == trace_id]

    def get_event_stats(self) -> Dict[str, Any]:
        event_type_counts = {}
        for event in self._events:
            event_type_counts[event.event_type] = event_type_counts.get(event.event_type, 0) + 1

        return {
            "total_events": len(self._events),
            "campaigns_tracked": len(self._campaign_feedback_cache),
            "event_type_distribution": event_type_counts
        }


feedback_collector = FeedbackCollector()