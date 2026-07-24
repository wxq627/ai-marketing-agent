from __future__ import annotations

import argparse
import csv
import json
import math
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from joblib import dump
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler


SERVICE_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
STRUCTURED_DIR = REPOSITORY_ROOT / "mock_data" / "structured"
DEFAULT_OUTPUT_DIR = SERVICE_DIR / "artifacts" / "pd_risk_model"
HORIZON_DAYS = 180

FEATURE_COLUMNS = [
    "age",
    "income_level",
    "active_card_count",
    "max_credit_amount",
    "primary_card_level",
    "bill_amount_90d",
    "bill_amount_180d",
    "bill_count_180d",
    "average_bill_amount_180d",
    "utilization_proxy_90d",
    "overdue_bills_180d",
    "overdue_bills_365d",
    "min_payment_bills_180d",
]
CATEGORICAL_COLUMNS = {"income_level", "primary_card_level"}


@dataclass
class TimeSeries:
    times: list[datetime]
    sums: list[float]

    def window_sum(self, as_of: datetime, days: int) -> float:
        left = bisect_left(self.times, as_of - timedelta(days=days))
        right = bisect_left(self.times, as_of)
        return self.sums[right] - self.sums[left]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=None)


def build_series(events: dict[str, list[tuple[datetime, float]]]) -> dict[str, TimeSeries]:
    result: dict[str, TimeSeries] = {}
    for customer_id, rows in events.items():
        rows.sort(key=lambda item: item[0])
        times: list[datetime] = []
        sums = [0.0]
        for event_time, value in rows:
            times.append(event_time)
            sums.append(sums[-1] + value)
        result[customer_id] = TimeSeries(times=times, sums=sums)
    return result


def series_value(series: dict[str, TimeSeries], customer_id: str, as_of: datetime, days: int) -> float:
    item = series.get(customer_id)
    return item.window_sum(as_of, days) if item else 0.0


def customer_metadata() -> dict[str, dict[str, str | float]]:
    basic = {row["cust_id"]: row for row in read_csv(STRUCTURED_DIR / "customer_basic.csv")}
    cards_by_customer: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(STRUCTURED_DIR / "credit_card.csv"):
        cards_by_customer[row["cust_id"]].append(row)

    metadata: dict[str, dict[str, str | float]] = {}
    for customer_id, row in basic.items():
        active_cards = [card for card in cards_by_customer[customer_id] if card.get("card_status") == "正常"]
        primary = next((card for card in active_cards if card.get("is_primary") == "True"), active_cards[0] if active_cards else {})
        metadata[customer_id] = {
            "age": float(row.get("age") or 0.0),
            "income_level": row.get("income_level", "unknown"),
            "active_card_count": float(len(active_cards)),
            "max_credit_amount": max((float(card.get("credit_amount") or 0.0) for card in active_cards), default=0.0),
            "primary_card_level": primary.get("card_level", "unknown"),
        }
    return metadata


def build_training_rows() -> tuple[list[dict[str, str | float]], dict[str, int | str]]:
    card_to_customer = {
        row["card_no"]: row["cust_id"] for row in read_csv(STRUCTURED_DIR / "credit_card.csv")
    }
    bill_amount: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    bill_count: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    overdue: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    min_payment: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    future_overdue: dict[str, list[datetime]] = defaultdict(list)
    months: set[datetime] = set()
    all_dates: list[datetime] = []

    for row in read_csv(STRUCTURED_DIR / "bill_record.csv"):
        customer_id = card_to_customer.get(row.get("card_no", ""))
        if not customer_id:
            continue
        due_date = parse_date(row["due_date"])
        months.add(datetime(due_date.year, due_date.month, 1))
        all_dates.append(due_date)
        amount = max(0.0, float(row.get("bill_amount") or 0.0))
        bill_amount[customer_id].append((due_date, amount))
        bill_count[customer_id].append((due_date, 1.0))
        if row.get("payment_status") == "逾期":
            overdue[customer_id].append((due_date, 1.0))
            future_overdue[customer_id].append(due_date)
        if row.get("is_min_payment") == "True":
            min_payment[customer_id].append((due_date, 1.0))

    if not all_dates:
        raise ValueError("bill_record.csv contains no usable bill dates")
    observed_until = max(all_dates)
    metadata = customer_metadata()
    amount_series = build_series(bill_amount)
    count_series = build_series(bill_count)
    overdue_series = build_series(overdue)
    min_payment_series = build_series(min_payment)

    # Monthly snapshots avoid using a bill outcome to predict itself and preserve a clear 180-day future horizon.
    as_of_dates = [month for month in sorted(months) if month + timedelta(days=HORIZON_DAYS) <= observed_until]
    rows: list[dict[str, str | float]] = []
    for customer_id, profile in metadata.items():
        overdue_dates = sorted(future_overdue.get(customer_id, []))
        for as_of in as_of_dates:
            future_end = as_of + timedelta(days=HORIZON_DAYS)
            label = int(any(as_of <= due_date < future_end for due_date in overdue_dates))
            amount_90d = series_value(amount_series, customer_id, as_of, 90)
            amount_180d = series_value(amount_series, customer_id, as_of, 180)
            count_180d = series_value(count_series, customer_id, as_of, 180)
            max_credit = max(float(profile["max_credit_amount"]), 1.0)
            rows.append(
                {
                    "customer_id": customer_id,
                    "as_of": as_of.isoformat(sep=" "),
                    "y_pd_6m": label,
                    "age": float(profile["age"]),
                    "income_level": str(profile["income_level"]),
                    "active_card_count": float(profile["active_card_count"]),
                    "max_credit_amount": float(profile["max_credit_amount"]),
                    "primary_card_level": str(profile["primary_card_level"]),
                    "bill_amount_90d": amount_90d,
                    "bill_amount_180d": amount_180d,
                    "bill_count_180d": count_180d,
                    "average_bill_amount_180d": amount_180d / count_180d if count_180d else 0.0,
                    "utilization_proxy_90d": amount_90d / max_credit,
                    "overdue_bills_180d": series_value(overdue_series, customer_id, as_of, 180),
                    "overdue_bills_365d": series_value(overdue_series, customer_id, as_of, 365),
                    "min_payment_bills_180d": series_value(min_payment_series, customer_id, as_of, 180),
                }
            )
    return rows, {
        "training_rows": len(rows),
        "positive_rows": sum(int(row["y_pd_6m"]) for row in rows),
        "observed_until": observed_until.isoformat(sep=" "),
        "horizon_days": HORIZON_DAYS,
        "snapshot_count": len(as_of_dates),
    }


def rows_to_features(rows: list[dict[str, str | float]]) -> list[dict[str, str | float]]:
    return [
        {
            column: str(row[column]) if column in CATEGORICAL_COLUMNS else float(row[column])
            for column in FEATURE_COLUMNS
        }
        for row in rows
    ]


def metrics_for(model: LogisticRegression, vectorizer: DictVectorizer, scaler: StandardScaler, rows: list[dict[str, str | float]]) -> dict[str, float | int]:
    labels = [int(row["y_pd_6m"]) for row in rows]
    matrix = scaler.transform(vectorizer.transform(rows_to_features(rows)))
    probabilities = model.predict_proba(matrix)[:, 1]
    positive_rate = sum(labels) / len(labels)
    top_count = max(1, math.ceil(len(rows) * 0.10))
    ranked = sorted(zip(probabilities, labels), reverse=True)[:top_count]
    top_rate = sum(label for _, label in ranked) / top_count
    return {
        "rows": len(rows),
        "positive_rate": round(positive_rate, 6),
        "roc_auc": round(float(roc_auc_score(labels, probabilities)), 6),
        "pr_auc": round(float(average_precision_score(labels, probabilities)), 6),
        "log_loss": round(float(log_loss(labels, probabilities)), 6),
        "top_decile_rate": round(top_rate, 6),
        "top_decile_lift": round(top_rate / positive_rate, 4) if positive_rate else 0.0,
    }


def train(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows, summary = build_training_rows()
    rows.sort(key=lambda row: str(row["as_of"]))
    train_end = int(len(rows) * 0.70)
    test_start = int(len(rows) * 0.85)
    train_rows = rows[:train_end]
    test_rows = rows[test_start:]
    train_labels = [int(row["y_pd_6m"]) for row in train_rows]
    test_labels = [int(row["y_pd_6m"]) for row in test_rows]
    if len(set(train_labels)) < 2 or len(set(test_labels)) < 2:
        raise ValueError("PD label has only one class after chronological split")

    vectorizer = DictVectorizer(sparse=True)
    train_matrix = vectorizer.fit_transform(rows_to_features(train_rows))
    scaler = StandardScaler(with_mean=False)
    train_matrix = scaler.fit_transform(train_matrix)
    # The six-month label already has a usable event rate. Keep natural class priors so
    # the emitted PD remains calibrated enough for an expected-loss calculation.
    model = LogisticRegression(max_iter=500, solver="lbfgs", random_state=42)
    model.fit(train_matrix, train_labels)
    metrics = metrics_for(model, vectorizer, scaler, test_rows)
    artifact = {
        "model": model,
        "vectorizer": vectorizer,
        "scaler": scaler,
        "feature_columns": FEATURE_COLUMNS,
        "label": "y_pd_6m",
        "model_name": "pd_6m_model",
        "horizon_days": HORIZON_DAYS,
        "training_window_end": str(train_rows[-1]["as_of"]),
    }
    dump(artifact, output_dir / "pd_6m_model.joblib")
    result = {"data_summary": summary, "model": {"artifact": "pd_6m_model.joblib", "metrics": metrics}}
    (output_dir / "training_metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    report = [
        "# PD Risk Modeling Report",
        "",
        "## Definition",
        "",
        "- Label: whether a customer has any overdue bill in the next 180 days.",
        "- Unit: customer monthly snapshot; all features are taken before the snapshot date.",
        "- Split: chronological 70% train / 15% validation gap / 15% held-out test.",
        "- Scope: a customer future-overdue proxy, not a causal post-conversion default probability.",
        "",
        "## Test Metrics",
        "",
        "| Test rows | Positive rate | ROC-AUC | PR-AUC | Log loss | Top-decile lift |",
        "|---:|---:|---:|---:|---:|---:|",
        "| {rows} | {positive_rate:.2%} | {roc_auc:.4f} | {pr_auc:.4f} | {log_loss:.4f} | {top_decile_lift:.2f} |".format(**metrics),
        "",
        "## Strategy Integration",
        "",
        "- When the PD artifact is available, strategy value uses p_conversion x PD_6M x expected_loss_per_default.",
        "- When it is unavailable, the existing risk-level rule remains the explicit fallback.",
    ]
    (output_dir / "training_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a six-month overdue PD risk model from bill records.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = train(args.output_dir)
    print(json.dumps(result["model"]["metrics"], ensure_ascii=False))
    print(f"PD artifacts written to {args.output_dir}")


if __name__ == "__main__":
    main()
