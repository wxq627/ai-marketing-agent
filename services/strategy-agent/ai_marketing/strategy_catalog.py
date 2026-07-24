from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .storage import PlanRepository


def export_published_strategy_catalog(repo: PlanRepository, output_path: Path) -> dict[str, Any]:
    """Export active strategy publications as a C-consumable static catalog."""
    customers: dict[str, dict[str, Any]] = {}
    strategies: dict[str, dict[str, Any]] = {}
    publications = repo.list_publications(status="published", limit=500)

    for publication in publications:
        strategy_version = str(publication["strategy_version"])
        package = repo.get_published_package(strategy_version)
        if package is None:
            continue

        metadata = package.get("campaign_metadata", {})
        benefit_rule = package.get("benefit_rule", {})
        campaign_id = str(publication["campaign_id"])
        product = str(publication["product"])
        benefit_name = str(benefit_rule.get("benefit_name") or product)
        constraints = package.get("audience_delivery_constraints", {}).get(
            "customer_channel_constraints", []
        )

        segments = {
            str(item.get("segment_id", "")): {
                "strategy": item.get("strategy", {}),
            }
            for item in package.get("audience_segments", [])
            if item.get("segment_id")
        }
        strategies[strategy_version] = {
            "strategy_version": strategy_version,
            "campaign_id": campaign_id,
            "product": product,
            "objective": metadata.get("objective", ""),
            "effective_from": publication.get("effective_from"),
            "effective_to": publication.get("effective_to"),
            "benefit_rule": benefit_rule,
            "compliance_guard": package.get("compliance_guard", {}),
            "segments": segments,
        }

        for constraint in constraints:
            oneid = str(constraint.get("oneid", "")).strip()
            if not oneid:
                continue
            segment_id = str(constraint.get("segment_id", ""))
            entry = customers.setdefault(oneid, {"assignments": []})
            entry["assignments"].append(
                {
                    "strategy_version": strategy_version,
                    "segment_id": segment_id,
                    "persona_name": constraint.get("persona_name", ""),
                    "allowed_channels": constraint.get("allowed_channels", []),
                    "score": float(constraint.get("expected_net_value", 0) or 0),
                }
            )

    for entry in customers.values():
        entry["assignments"].sort(key=lambda item: item["score"], reverse=True)

    catalog = {
        "schema_version": "1.1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "strategy-agent",
        "publication_count": len(publications),
        "customer_count": len(customers),
        "strategies": strategies,
        "customers": customers,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "path": str(output_path),
        "publication_count": len(publications),
        "customer_count": len(customers),
        "generated_at": catalog["generated_at"],
    }
