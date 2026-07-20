from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import MarketingPlan


class PlanRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
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

    def save(self, plan: MarketingPlan) -> None:
        payload = json.dumps(plan.to_dict(), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                insert or replace into marketing_plan
                (campaign_id, product, audience_size, predicted_uplift, predicted_roi, payload)
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.campaign_id,
                    plan.request.product,
                    plan.audience_size,
                    plan.predicted_uplift,
                    plan.predicted_roi,
                    payload,
                ),
            )

    def list_recent(self, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
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
