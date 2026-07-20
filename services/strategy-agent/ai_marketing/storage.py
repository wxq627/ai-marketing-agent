from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
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
