from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .models import MarketingPlan


class PlanRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                create table if not exists marketing_plan (
                    campaign_id text primary key,
                    product text not null,
                    audience_size integer not null,
                    predicted_uplift real not null,
                    predicted_roi real not null,
                    payload text not null,
                    created_at text default current_timestamp
                )
                """
            )
            columns = {
                row[1] for row in conn.execute("pragma table_info(marketing_plan)").fetchall()
            }
            if "strategy_package" not in columns:
                conn.execute("alter table marketing_plan add column strategy_package text")
            conn.execute(
                """
                create table if not exists strategy_publication (
                    strategy_version text primary key,
                    campaign_id text not null,
                    product text not null,
                    status text not null,
                    effective_from text not null,
                    effective_to text,
                    strategy_package text not null,
                    created_at text not null,
                    published_at text
                )
                """
            )
            conn.execute(
                """
                create index if not exists idx_strategy_publication_active
                on strategy_publication (status, product, effective_from, effective_to)
                """
            )
            conn.execute(
                """
                create table if not exists strategy_feedback_event (
                    feedback_id integer primary key autoincrement,
                    strategy_version text,
                    campaign_id text,
                    oneid text,
                    channel text,
                    event_type text not null,
                    event_time text not null,
                    payload text not null,
                    created_at text not null
                )
                """
            )
            conn.execute(
                """
                create index if not exists idx_strategy_feedback_lookup
                on strategy_feedback_event (strategy_version, campaign_id, event_time)
                """
            )
            conn.execute(
                """
                create index if not exists idx_strategy_feedback_customer_channel
                on strategy_feedback_event (oneid, channel, event_time)
                """
            )
            conn.execute(
                """
                create table if not exists customer_campaign_channel_suppression (
                    oneid text not null,
                    campaign_id text not null,
                    channel text not null,
                    reason text not null,
                    created_at text not null,
                    primary key (oneid, campaign_id, channel)
                )
                """
            )

    def save(self, plan: MarketingPlan, strategy_package: dict[str, Any] | None = None) -> None:
        payload = json.dumps(plan.to_dict(), ensure_ascii=False)
        package_payload = json.dumps(strategy_package, ensure_ascii=False) if strategy_package else None
        with self._connection() as conn:
            conn.execute(
                """
                insert into marketing_plan
                (campaign_id, product, audience_size, predicted_uplift, predicted_roi, payload, strategy_package)
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(campaign_id) do update set
                    product=excluded.product,
                    audience_size=excluded.audience_size,
                    predicted_uplift=excluded.predicted_uplift,
                    predicted_roi=excluded.predicted_roi,
                    payload=excluded.payload,
                    strategy_package=coalesce(excluded.strategy_package, marketing_plan.strategy_package)
                """,
                (
                    plan.campaign_id,
                    plan.request.product,
                    plan.audience_size,
                    plan.predicted_uplift,
                    plan.predicted_roi,
                    payload,
                    package_payload,
                ),
            )

    def save_optimized_draft(
        self,
        *,
        campaign_id: str,
        strategy_package: dict[str, Any],
        selection_summary: dict[str, Any],
    ) -> None:
        """Save a value-optimized strategy package so it can use the normal publish lifecycle."""
        metadata = strategy_package.get("campaign_metadata", {})
        payload = json.dumps(
            {
                "source": "value_optimization",
                "campaign_id": campaign_id,
                "selection_summary": selection_summary,
            },
            ensure_ascii=False,
        )
        package_payload = json.dumps(strategy_package, ensure_ascii=False)
        budget_used = max(float(selection_summary.get("budget_used", 0) or 0), 0.01)
        predicted_roi = float(selection_summary.get("expected_net_value", 0) or 0) / budget_used
        selected_count = int(selection_summary.get("selected_candidate_count", 0) or 0)
        expected_conversion = float(selection_summary.get("expected_conversion_count", 0) or 0)
        predicted_uplift = expected_conversion / max(selected_count, 1)
        with self._connection() as conn:
            conn.execute(
                """
                insert into marketing_plan
                (campaign_id, product, audience_size, predicted_uplift, predicted_roi, payload, strategy_package)
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(campaign_id) do update set
                    product=excluded.product,
                    audience_size=excluded.audience_size,
                    predicted_uplift=excluded.predicted_uplift,
                    predicted_roi=excluded.predicted_roi,
                    payload=excluded.payload,
                    strategy_package=excluded.strategy_package
                """,
                (
                    campaign_id,
                    str(metadata.get("product", "")),
                    selected_count,
                    predicted_uplift,
                    predicted_roi,
                    payload,
                    package_payload,
                ),
            )

    def publish(
        self,
        campaign_id: str,
        *,
        effective_from: str | None = None,
        effective_to: str | None = None,
    ) -> dict[str, Any]:
        """Publish a saved strategy package as an immutable C-facing version."""
        start = _normalize_time(effective_from)
        end = _normalize_time(effective_to) if effective_to else None
        if end and end <= start:
            raise ValueError("effective_to must be later than effective_from")

        with self._connection() as conn:
            row = conn.execute(
                """
                select product, strategy_package
                from marketing_plan
                where campaign_id = ?
                """,
                (campaign_id,),
            ).fetchone()
            if row is None:
                raise KeyError("campaign_not_found")
            product, package_payload = row
            if not package_payload:
                raise ValueError("strategy_package_not_available_for_campaign")
            package = json.loads(package_payload)
            product = package.get("campaign_metadata", {}).get("product", product)
            next_number = conn.execute(
                "select count(*) from strategy_publication where campaign_id = ?",
                (campaign_id,),
            ).fetchone()[0] + 1
            version = f"STR_{campaign_id}_{next_number:03d}"
            published_at = _now()
            conn.execute(
                """
                insert into strategy_publication
                (strategy_version, campaign_id, product, status, effective_from, effective_to,
                 strategy_package, created_at, published_at)
                values (?, ?, ?, 'published', ?, ?, ?, ?, ?)
                """,
                (version, campaign_id, product, start, end, package_payload, published_at, published_at),
            )
        return self.get_publication(version) or {}

    def archive(self, strategy_version: str) -> dict[str, Any]:
        with self._connection() as conn:
            updated = conn.execute(
                """
                update strategy_publication
                set status = 'archived'
                where strategy_version = ? and status = 'published'
                """,
                (strategy_version,),
            ).rowcount
        if not updated:
            raise KeyError("published_strategy_not_found")
        return self.get_publication(strategy_version) or {}

    def get_publication(self, strategy_version: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                select strategy_version, campaign_id, product, status, effective_from, effective_to,
                       created_at, published_at
                from strategy_publication
                where strategy_version = ?
                """,
                (strategy_version,),
            ).fetchone()
        return _publication_metadata(row) if row else None

    def get_published_package(self, strategy_version: str) -> dict[str, Any] | None:
        """Return a complete package only when its version is published."""
        with self._connection() as conn:
            row = conn.execute(
                """
                select strategy_package
                from strategy_publication
                where strategy_version = ? and status = 'published'
                """,
                (strategy_version,),
            ).fetchone()
        if row is None:
            return None
        return _normalize_download_package(json.loads(row[0]))

    def list_publications(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        query = """
            select strategy_version, campaign_id, product, status, effective_from, effective_to,
                   created_at, published_at
            from strategy_publication
        """
        parameters: list[Any] = []
        if status:
            query += " where status = ?"
            parameters.append(status)
        query += " order by published_at desc, created_at desc limit ?"
        parameters.append(limit)
        with self._connection() as conn:
            rows = conn.execute(query, parameters).fetchall()
        return [_publication_metadata(row) for row in rows]

    def published_context_for_customer(
        self,
        *,
        customer_id: str,
        product: str | None = None,
        as_of: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return a minimal, customer-specific policy context for the C-side agent."""
        current_time = _normalize_time(as_of)
        with self._connection() as conn:
            rows = conn.execute(
                """
                select strategy_version, campaign_id, product, effective_from, effective_to, strategy_package
                from strategy_publication
                where status = 'published'
                  and effective_from <= ?
                  and (effective_to is null or effective_to > ?)
                order by published_at desc, created_at desc
                """,
                (current_time, current_time),
            ).fetchall()

        contexts: list[dict[str, Any]] = []
        for version, campaign_id, stored_product, start, end, package_payload in rows:
            if product and not _product_matches(product, stored_product):
                continue
            package = json.loads(package_payload)
            constraints = package.get("audience_delivery_constraints", {}).get(
                "customer_channel_constraints", []
            )
            customer_constraint = next(
                (item for item in constraints if item.get("customer_id") == customer_id),
                None,
            )
            if customer_constraint is None:
                continue
            segment_id = customer_constraint.get("segment_id", "")
            segment = next(
                (item for item in package.get("audience_segments", []) if item.get("segment_id") == segment_id),
                {},
            )
            contexts.append(
                {
                    "strategy_version": version,
                    "campaign_id": campaign_id,
                    "product": stored_product,
                    "objective": package.get("campaign_metadata", {}).get("objective", ""),
                    "effective_from": start,
                    "effective_to": end,
                    "segment_id": segment_id,
                    "persona_name": customer_constraint.get("persona_name", ""),
                    "allowed_channels": customer_constraint.get("allowed_channels", []),
                    "strategy": segment.get("strategy", {}),
                    "benefit_rule": package.get("benefit_rule", {}),
                    "compliance_guard": {
                        "frequency_limit": package.get("compliance_guard", {}).get("frequency_limit", ""),
                        "must_not_claim": package.get("compliance_guard", {}).get("must_not_claim", []),
                    },
                }
            )
        return contexts

    def save_feedback(self, feedback: dict[str, Any]) -> dict[str, Any]:
        """Persist a C-side delivery or conversion event for later review and retraining."""
        event_type = str(feedback.get("event_type", "aggregate_feedback")).strip() or "aggregate_feedback"
        event_time = _normalize_time(str(feedback.get("event_time", "")) or None)
        created_at = _now()
        payload = json.dumps(feedback, ensure_ascii=False)
        with self._connection() as conn:
            cursor = conn.execute(
                """
                insert into strategy_feedback_event
                (strategy_version, campaign_id, oneid, channel, event_type, event_time, payload, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _optional_string(feedback.get("strategy_version")),
                    _optional_string(feedback.get("campaign_id")),
                    _optional_string(feedback.get("oneid")),
                    _optional_string(feedback.get("channel")),
                    event_type,
                    event_time,
                    payload,
                    created_at,
                ),
            )
        return {
            "feedback_id": cursor.lastrowid,
            "event_type": event_type,
            "event_time": event_time,
            "stored": True,
        }

    def suppress_campaign(self, oneid: str, campaign_id: str, reason: str) -> None:
        """Mark a campaign as permanently suppressed for a customer (user_reject / unsubscribe)."""
        with self._connection() as conn:
            conn.execute(
                """
                create table if not exists customer_suppression (
                    oneid text not null,
                    campaign_id text not null,
                    reason text not null,
                    created_at text not null,
                    primary key (oneid, campaign_id)
                )
                """
            )
            conn.execute(
                """
                insert or ignore into customer_suppression (oneid, campaign_id, reason, created_at)
                values (?, ?, ?, ?)
                """,
                (oneid, campaign_id, reason, _now()),
            )

    def get_suppressed_campaigns(self, oneid: str) -> frozenset[str]:
        """Return legacy campaign-wide suppression records retained for historical compatibility."""
        with self._connection() as conn:
            conn.execute(
                """
                create table if not exists customer_suppression (
                    oneid text not null,
                    campaign_id text not null,
                    reason text not null,
                    created_at text not null,
                    primary key (oneid, campaign_id)
                )
                """
            )
            rows = conn.execute(
                "select campaign_id from customer_suppression where oneid = ?",
                (oneid,),
            ).fetchall()
        return frozenset(row[0] for row in rows)

    def suppress_campaign_channel(self, oneid: str, campaign_id: str, channel: str, reason: str) -> None:
        """Stop one campaign on one channel after an explicit channel-level unsubscribe."""
        with self._connection() as conn:
            conn.execute(
                """
                insert or ignore into customer_campaign_channel_suppression
                (oneid, campaign_id, channel, reason, created_at)
                values (?, ?, ?, ?, ?)
                """,
                (oneid, campaign_id, channel, reason, _now()),
            )

    def channel_delivery_state(
        self,
        oneid: str,
        campaign_id: str,
        channel: str,
        *,
        as_of: str | None = None,
        window_days: int = 7,
        max_unresponsive_touches: int = 3,
    ) -> dict[str, Any]:
        """Return whether a campaign can still be sent on a channel for one customer.

        Only explicit ``ignored`` events count as an unresponsive touch. A detail view,
        click, or conversion breaks that sequence because the customer has responded.
        """
        now = _parse_normalized_time(_normalize_time(as_of))
        lower_bound = (now - timedelta(days=window_days)).isoformat(sep=" ", timespec="seconds")
        with self._connection() as conn:
            suppressed = conn.execute(
                """
                select 1 from customer_campaign_channel_suppression
                where oneid = ? and campaign_id = ? and channel = ?
                """,
                (oneid, campaign_id, channel),
            ).fetchone()
            rows = conn.execute(
                """
                select event_type from strategy_feedback_event
                where oneid = ? and channel = ? and event_time >= ?
                order by event_time desc, feedback_id desc
                """,
                (oneid, channel, lower_bound),
            ).fetchall()

        unresponsive_touches = 0
        response_events = {"view_detail", "user_click", "clicked", "converted", "conversion"}
        for (event_type,) in rows:
            if event_type in response_events:
                break
            if event_type == "ignored":
                unresponsive_touches += 1

        if suppressed:
            return {
                "allowed": False,
                "reason": "campaign_channel_unsubscribed",
                "unresponsive_touches_7d": unresponsive_touches,
                "window_days": window_days,
                "max_unresponsive_touches": max_unresponsive_touches,
            }
        if unresponsive_touches >= max_unresponsive_touches:
            return {
                "allowed": False,
                "reason": "unresponsive_frequency_cap_reached",
                "unresponsive_touches_7d": unresponsive_touches,
                "window_days": window_days,
                "max_unresponsive_touches": max_unresponsive_touches,
            }
        return {
            "allowed": True,
            "reason": None,
            "unresponsive_touches_7d": unresponsive_touches,
            "window_days": window_days,
            "max_unresponsive_touches": max_unresponsive_touches,
        }

    def get_benefit_affinity(self, persona_name: str) -> dict[str, float]:
        """Aggregate detail-view/conversion feedback by benefit_category for a given persona.

        Returns a dict of {benefit_category: affinity_score} where higher = more positive signal.
        Neutral categories (no feedback) are omitted.
        """
        # Map campaign_id -> benefit_category
        campaign_mapping: dict[str, str] = {}
        csv_path = (
            Path(__file__).resolve().parent.parent / "config" / "campaign_offer_mapping.csv"
        )
        if csv_path.exists():
            import csv
            with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                campaign_mapping = {row["campaign_id"]: row.get("benefit_category", "")
                                    for row in csv.DictReader(handle)}

        with self._connection() as conn:
            rows = conn.execute(
                """
                select campaign_id, event_type, count(*) as cnt
                from strategy_feedback_event
                where campaign_id != '' and event_type in ('view_detail', 'user_click', 'clicked', 'converted')
                group by campaign_id, event_type
                """
            ).fetchall()

        # Aggregate by benefit_category
        cat_clicks: dict[str, float] = {}
        cat_total: dict[str, float] = {}
        for campaign_id, event_type, cnt in rows:
            category = campaign_mapping.get(campaign_id, "")
            if not category:
                continue
            cat_clicks[category] = cat_clicks.get(category, 0.0) + cnt
            cat_total[category] = cat_total.get(category, 0.0) + cnt

        return {cat: min(0.25, max(-0.25, cat_clicks[cat] / max(cat_total[cat], 1)))
                for cat in cat_total if cat_total[cat] > 0}

    def list_feedback(
        self,
        *,
        strategy_version: str | None = None,
        campaign_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        query = """
            select feedback_id, strategy_version, campaign_id, oneid, channel, event_type,
                   event_time, payload, created_at
            from strategy_feedback_event
        """
        clauses: list[str] = []
        parameters: list[Any] = []
        if strategy_version:
            clauses.append("strategy_version = ?")
            parameters.append(strategy_version)
        if campaign_id:
            clauses.append("campaign_id = ?")
            parameters.append(campaign_id)
        if clauses:
            query += " where " + " and ".join(clauses)
        query += " order by event_time desc, feedback_id desc limit ?"
        parameters.append(limit)
        with self._connection() as conn:
            rows = conn.execute(query, parameters).fetchall()
        return [
            {
                "feedback_id": row[0],
                "strategy_version": row[1],
                "campaign_id": row[2],
                "oneid": row[3],
                "channel": row[4],
                "event_type": row[5],
                "event_time": row[6],
                "payload": json.loads(row[7]),
                "created_at": row[8],
            }
            for row in rows
        ]

    def list_recent(self, limit: int = 10) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                select campaign_id, product, audience_size, predicted_uplift, predicted_roi, created_at
                from marketing_plan
                order by created_at desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "campaign_id": row[0],
                "product": row[1],
                "audience_size": row[2],
                "predicted_uplift": row[3],
                "predicted_roi": row[4],
                "created_at": row[5],
            }
            for row in rows
        ]


def _publication_metadata(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "strategy_version": row[0],
        "campaign_id": row[1],
        "product": row[2],
        "status": row[3],
        "effective_from": row[4],
        "effective_to": row[5],
        "created_at": row[6],
        "published_at": row[7],
    }


def _normalize_download_package(package: dict[str, Any]) -> dict[str, Any]:
    """Make historical published packages consumable by the current C-side schema."""
    benefit_rule = package.get("benefit_rule")
    if not isinstance(benefit_rule, dict):
        return package

    product = str(package.get("campaign_metadata", {}).get("product", "")).lower()
    benefit_category = str(benefit_rule.get("benefit_category", "活动"))
    defaults = {
        "credit_card_installment": ("installment_fee_coupon", "分期手续费优惠"),
        "card_upgrade": ("card_upgrade_benefit", "卡等级升级权益"),
        "customer_activation": ("activation_reward", "客户激活权益"),
    }
    benefit_type, benefit_name = defaults.get(
        product,
        ("campaign_benefit", f"{benefit_category}活动权益"),
    )
    benefit_rule.setdefault("benefit_type", benefit_type)
    benefit_rule.setdefault("benefit_name", benefit_name)
    benefit_rule.setdefault("limit", "每客户在活动有效期内最多使用1次")
    return package


def _product_matches(requested_product: str, stored_product: str) -> bool:
    aliases = {
        "installment": "credit_card_installment",
        "coupon": "coupon_package",
        "travel": "travel_benefit",
    }
    normalized = requested_product.strip().lower()
    normalized = aliases.get(normalized, normalized)
    return normalized == stored_product.strip().lower()


def _normalize_time(value: str | None) -> str:
    if not value:
        return _now()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError as exc:
        raise ValueError("time must be ISO-8601 compatible") from exc
    return parsed.isoformat(sep=" ", timespec="seconds")


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def _parse_normalized_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _optional_string(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
