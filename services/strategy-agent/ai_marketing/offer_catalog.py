from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .local_knowledge_data import STRUCTURED_DATA_DIR


@dataclass(frozen=True)
class ProductOffer:
    product_id: str
    product_name: str
    target_income: str
    selling_points: list[str]
    benefit_ids: list[str]
    benefit_names: list[str]
    required_income: str
    min_age: int
    max_age: int
    required_card_level: str
    min_credit: float
    special_conditions: str


class OfferCatalog:
    def __init__(self, structured_dir: Path | None = None) -> None:
        self.structured_dir = structured_dir or STRUCTURED_DATA_DIR
        self._offers: list[ProductOffer] | None = None

    def offers(self) -> list[ProductOffer]:
        if self._offers is None:
            self._offers = self._load_offers()
        return self._offers

    def get(self, product_id: str) -> ProductOffer | None:
        normalized = product_id.strip()
        return next((offer for offer in self.offers() if offer.product_id == normalized), None)

    def _load_offers(self) -> list[ProductOffer]:
        products = {row["product_id"]: row for row in _read_csv(self.structured_dir / "product_catalog.csv")}
        benefits = {row["benefit_id"]: row for row in _read_csv(self.structured_dir / "benefit_catalog.csv")}
        eligibility = {row["product_id"]: row for row in _read_csv(self.structured_dir / "product_eligibility.csv")}
        mapping: dict[str, list[str]] = {}
        for row in _read_csv(self.structured_dir / "product_benefit_mapping.csv"):
            mapping.setdefault(row["product_id"], []).append(row["benefit_id"])

        offers: list[ProductOffer] = []
        for product_id, product in products.items():
            rule = eligibility.get(product_id, {})
            benefit_ids = mapping.get(product_id, [])
            offers.append(
                ProductOffer(
                    product_id=product_id,
                    product_name=product.get("product_name", product_id),
                    target_income=product.get("target_income", ""),
                    selling_points=_split_values(product.get("key_selling_points", "")),
                    benefit_ids=benefit_ids,
                    benefit_names=[benefits[item].get("benefit_name", item) for item in benefit_ids if item in benefits],
                    required_income=rule.get("required_income", ""),
                    min_age=_as_int(rule.get("min_age")),
                    max_age=_as_int(rule.get("max_age"), default=99),
                    required_card_level=rule.get("required_card_level", ""),
                    min_credit=_as_float(rule.get("min_credit")),
                    special_conditions=rule.get("special_conditions", ""),
                )
            )
        return offers


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _split_values(value: str) -> list[str]:
    return [item.strip() for item in value.replace("\uff0c", ",").split(",") if item.strip()]


def _as_int(value: str | None, *, default: int = 0) -> int:
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default


def _as_float(value: str | None) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
