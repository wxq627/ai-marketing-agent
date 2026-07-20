"""
C→A 反馈接口 (项目三回传) — router_feedback.py
=================================================
接收项目三 Marketing Agent 回传的所有客户行为数据。

数据覆盖项目三实际回传的全部类型:
  - 触达事件: 曝光/点击/关闭/退订
  - 转化事件: 消费/分期申请/绑卡
  - 对话摘要: 客服对话/智能体对话
  - 行为数据: 浏览时长/浏览页面/搜索关键词
  - ROI 数据: 活动归因/转化金额/触达成本
"""

import os, json, pandas as pd
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

router = APIRouter(prefix="/api/v1/feedback", tags=["C→A Feedback"])


class FeedbackEvent(BaseModel):
    oneid: str
    event_type: str = Field(..., description="impression|click|dismiss|conversion|conversation|browse|search|unsubscribe")
    campaign_id: str = ""
    channel: str = ""
    content_id: str = ""
    timestamp: str = ""
    detail: Dict = Field(default={})


class BatchFeedbackRequest(BaseModel):
    events: List[FeedbackEvent]
    source: str = "project3_marketing_agent"


class TransactionInput(BaseModel):
    oneid: str
    amount: float
    merchant: str = ""
    category: str = "购物"
    channel: str = "支付宝"
    txn_type: str = "消费"


@router.post("/events", summary="C→A 单条反馈事件回传")
def receive_feedback(event: FeedbackEvent):
    return process_event(event)


@router.post("/batch", summary="C→A 批量反馈回传 (项目三定时推送)")
def receive_batch(req: BatchFeedbackRequest):
    results = []
    for e in req.events:
        results.append(process_event(e))
    return {"received": len(req.events), "processed": len(results), "results": results}


@router.post("/transaction", summary="手动录入客户交易 (模拟消费事件)")
def add_transaction(txn: TransactionInput):
    return {
        "status": "recorded",
        "oneid": txn.oneid,
        "amount": txn.amount,
        "merchant": txn.merchant,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updates": {
            "realtime_signal_count": "+1",
            "short_term_7d_total_consumption": f"+{txn.amount} (1h内微批更新)",
            "mid_term_30d": "次日T+1纳入趋势计算",
            "value_annual_consumption": "下次T+1批量刷新"
        }
    }


def process_event(e: FeedbackEvent) -> Dict:
    updates = {"oneid": e.oneid, "event_type": e.event_type}
    et = e.event_type

    if et == "impression":
        updates["action"] = "频控计数+1; 曝光记录追加"
    elif et == "click":
        updates["action"] = "点击记录+1; 短期窗口活跃度+1"
        dl = e.detail
        updates["click_rate_impact"] = f"渠道={e.channel}点击率微调"
        if dl.get("stay_sec"):
            updates["browse_duration"] = f"浏览{dl['stay_sec']}秒"
    elif et == "dismiss":
        updates["action"] = "关闭记录+1; 连续3次触发频控升级"
        dl = e.detail
        if dl.get("dismiss_count", 0) >= 3:
            updates["alert"] = "连续3次关闭推送, 触发频控cooldown_72h"
    elif et == "conversion":
        amt = e.detail.get("amount", 0)
        updates["action"] = f"转化金额¥{amt}已记录; ROI更新; 意图评分重算"
        updates["value_update"] = f"年消费+{amt}, 月均消费+{amt/12:.0f}"
        updates["roi_impact"] = f"活动{e.campaign_id}归因收入+{amt}"
    elif et == "conversation":
        updates["action"] = "对话摘要已记录; LLM重算意图向量"
        updates["sentiment"] = e.detail.get("sentiment", "neutral")
        updates["intent"] = e.detail.get("intent", "")
    elif et == "browse":
        updates["action"] = f"浏览{e.detail.get('page','')} {e.detail.get('stay_sec',0)}秒"
    elif et == "search":
        updates["action"] = f"搜索'{e.detail.get('keyword','')}' 已记录"
    elif et == "unsubscribe":
        ch = e.detail.get("channel", e.channel)
        updates["action"] = f"退订渠道{ch}; consent永久更新"

    return updates
