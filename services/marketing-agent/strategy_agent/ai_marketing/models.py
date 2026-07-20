from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Customer:
    customer_id: str
    age: int
    city_tier: int
    monthly_spend: float
    dining_txn: int
    travel_txn: int
    online_txn: int
    credit_limit_usage: float
    coupon_response: float
    installment_history: int
    app_active_days: int
    recent_contacts: int
    complaint_risk: float
    has_marketing_consent: bool


@dataclass(frozen=True)
class CampaignRequest:
    goal: str
    product: str = "installment"
    channel_mode: str = "omni"
    budget_wan: int = 80
    risk_level: int = 2
    frequency_level: int = 2


@dataclass(frozen=True)
class ParsedIntent:
    product: str
    objective: str
    target_signals: list[str]
    constraints: list[str]
    risk_level: int
    frequency_level: int


@dataclass(frozen=True)
class CustomerScore:
    customer: Customer
    response_prob: float
    conversion_prob: float
    expected_value: float
    risk_penalty: float
    segment: str
    reasons: list[str]


@dataclass(frozen=True)
class SegmentRecommendation:
    name: str
    size: int
    avg_score: float
    conversion_rate: float
    expected_value_wan: float
    reasons: list[str]


@dataclass(frozen=True)
class ChannelPlan:
    channel: str
    budget_share: float
    expected_reach: int
    role: str


@dataclass(frozen=True)
class ComplianceCheck:
    item: str
    status: str
    detail: str


@dataclass(frozen=True)
class MarketingPlan:
    campaign_id: str
    request: CampaignRequest
    intent: ParsedIntent
    audience_size: int
    predicted_uplift: float
    predicted_roi: float
    segments: list[SegmentRecommendation]
    channels: list[ChannelPlan]
    content: dict[str, str]
    compliance: list[ComplianceCheck]
    experiment: dict[str, Any]
    effect_forecast: dict[str, float]
    next_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
