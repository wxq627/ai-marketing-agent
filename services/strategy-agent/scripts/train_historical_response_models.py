from __future__ import annotations

import argparse
import csv
import json
import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from joblib import dump
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler


SERVICE_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
STRUCTURED_DIR = REPOSITORY_ROOT / "mock_data" / "structured"
MAPPING_PATH = SERVICE_DIR / "config" / "campaign_offer_mapping.csv"
DEFAULT_OUTPUT_DIR = SERVICE_DIR / "artifacts" / "historical_modeling_v1"

DELIVERED_STATUSES = {"sent", "delivered", "opened", "clicked", "unsubscribed"}
OPEN_MEASURABLE_CHANNELS = {"APP Push", "掌上生活APP内消息", "微信公众号", "邮件"}


@dataclass
class TimeSeries:
    times: list[datetime]
    sums: list[float]

    def window_sum(self, as_of: datetime, days: int) -> float:
        left = bisect_left(self.times, as_of - timedelta(days=days))
        right = bisect_left(self.times, as_of)
        return self.sums[right] - self.sums[left]


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_series(events: dict[str, list[tuple[datetime, float]]]) -> dict[str, TimeSeries]:
    result: dict[str, TimeSeries] = {}
    for key, rows in events.items():
        rows.sort(key=lambda item: item[0])
        times: list[datetime] = []
        sums = [0.0]
        for event_time, value in rows:
            times.append(event_time)
            sums.append(sums[-1] + value)
        result[key] = TimeSeries(times=times, sums=sums)
    return result


def series_value(series_by_customer: dict[str, TimeSeries], customer_id: str, as_of: datetime, days: int) -> float:
    series = series_by_customer.get(customer_id)
    return series.window_sum(as_of, days) if series else 0.0


def load_customer_features() -> dict[str, dict[str, str | float]]:
    basic = {row["cust_id"]: row for row in read_csv(STRUCTURED_DIR / "customer_basic.csv")}
    cards_by_customer: dict[str, list[dict[str, str]]] = defaultdict(list)
    for card in read_csv(STRUCTURED_DIR / "credit_card.csv"):
        cards_by_customer[card["cust_id"]].append(card)

    features: dict[str, dict[str, str | float]] = {}
    for customer_id, row in basic.items():
        cards = cards_by_customer.get(customer_id, [])
        active_cards = [card for card in cards if card["card_status"] == "正常"]
        max_credit = max((float(card["credit_amount"]) for card in active_cards), default=0.0)
        features[customer_id] = {
            "age": float(row["age"]),
            "city": row["city"],
            "occupation": row["occupation"],
            "income_level": row["income_level"],
            "education": row["education"],
            "active_card_count": float(len(active_cards)),
            "max_credit_amount": max_credit,
        }
    return features


def load_channel_costs() -> dict[str, float]:
    """Read canonical channel costs when the touch-history extract omits a per-touch cost column."""
    return {
        row["channel_name"]: float(row["cost_per_send"])
        for row in read_csv(STRUCTURED_DIR / "channel_config.csv")
    }


def load_pre_touch_series() -> tuple[
    dict[str, TimeSeries],
    dict[str, TimeSeries],
    dict[str, TimeSeries],
    dict[str, TimeSeries],
    dict[str, TimeSeries],
    dict[str, TimeSeries],
]:
    card_to_customer = {
        row["card_no"]: row["cust_id"] for row in read_csv(STRUCTURED_DIR / "credit_card.csv")
    }
    transaction_spend: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    transaction_count: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for row in read_csv(STRUCTURED_DIR / "transaction_log.csv"):
        if row["txn_type"] != "消费" or float(row["amount"]) <= 0:
            continue
        customer_id = card_to_customer.get(row["card_no"])
        if customer_id:
            event_time = parse_time(row["timestamp"])
            transaction_spend[customer_id].append((event_time, float(row["amount"])))
            transaction_count[customer_id].append((event_time, 1.0))

    open_to_customer = {
        row["id_value"]: row["oneid"]
        for row in read_csv(STRUCTURED_DIR / "id_mapping.csv")
        if row["id_type"] == "open_id"
    }
    oneid_to_customer = {
        row["oneid"]: row["id_value"]
        for row in read_csv(STRUCTURED_DIR / "id_mapping.csv")
        if row["id_type"] == "cust_id"
    }
    app_event_count: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    app_search_count: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for row in read_csv(STRUCTURED_DIR / "app_events.csv"):
        oneid = open_to_customer.get(row["open_id"])
        customer_id = oneid_to_customer.get(oneid, "")
        if customer_id:
            event_time = parse_time(row["timestamp"])
            app_event_count[customer_id].append((event_time, 1.0))
            if row["event_type"] == "搜索" or row["search_keyword"].strip():
                app_search_count[customer_id].append((event_time, 1.0))

    bill_overdue_count: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    bill_min_payment_count: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for row in read_csv(STRUCTURED_DIR / "bill_record.csv"):
        customer_id = card_to_customer.get(row["card_no"])
        if not customer_id:
            continue
        due_date = parse_time(row["due_date"])
        if row["payment_status"] == "逾期":
            bill_overdue_count[customer_id].append((due_date, 1.0))
        if row["is_min_payment"] == "True":
            bill_min_payment_count[customer_id].append((due_date, 1.0))

    return (
        build_series(transaction_spend),
        build_series(transaction_count),
        build_series(app_event_count),
        build_series(app_search_count),
        build_series(bill_overdue_count),
        build_series(bill_min_payment_count),
    )


def load_contact_history() -> tuple[list[dict[str, str]], dict[str, TimeSeries], dict[str, TimeSeries], dict[str, TimeSeries]]:
    contacts = [
        row
        for row in read_csv(STRUCTURED_DIR / "contact_history.csv")
        if row["contact_type"] == "marketing" and row["campaign_id"]
    ]
    all_counts: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    clicked_counts: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    unsubscribe_counts: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for row in contacts:
        event_time = parse_time(row["contact_time"])
        customer_id = row["cust_id"]
        all_counts[customer_id].append((event_time, 1.0))
        if row["status"] == "clicked":
            clicked_counts[customer_id].append((event_time, 1.0))
        if row["status"] == "unsubscribed":
            unsubscribe_counts[customer_id].append((event_time, 1.0))
    contacts.sort(key=lambda row: row["contact_time"])
    return contacts, build_series(all_counts), build_series(clicked_counts), build_series(unsubscribe_counts)


def load_attribution() -> dict[str, dict[str, str | float | bool]]:
    records: dict[str, dict[str, str | float | bool]] = {}
    for row in read_csv(STRUCTURED_DIR / "campaign_attribution.csv"):
        touch_id = row["touch_id"]
        existing = records.get(touch_id)
        converted = row["converted"] == "True"
        amount = float(row["conversion_amount"] or 0.0)
        if existing is None or amount > float(existing["conversion_amount"]):
            records[touch_id] = {
                "converted": converted,
                "conversion_amount": amount,
                "conversion_time": row["conversion_time"],
            }
    return records


def load_mapping() -> dict[str, dict[str, str]]:
    mapping = {row["campaign_id"]: row for row in read_csv(MAPPING_PATH)}
    campaign_count = len(read_csv(STRUCTURED_DIR / "campaign_catalog.csv"))
    if len(mapping) != campaign_count:
        raise ValueError(f"Expected {campaign_count} campaign mappings, found {len(mapping)}")
    return mapping


def make_feature_row(
    *,
    contact: dict[str, str],
    mapping: dict[str, str],
    customer: dict[str, str | float],
    spend: dict[str, TimeSeries],
    transaction_count: dict[str, TimeSeries],
    app_events: dict[str, TimeSeries],
    app_searches: dict[str, TimeSeries],
    overdue: dict[str, TimeSeries],
    min_payment: dict[str, TimeSeries],
    previous_contacts: dict[str, TimeSeries],
    previous_clicks: dict[str, TimeSeries],
    previous_unsubscribes: dict[str, TimeSeries],
    attribution: dict[str, dict[str, str | float | bool]],
    channel_costs: dict[str, float],
    observed_until: datetime,
) -> dict[str, str | float | int]:
    touch_time = parse_time(contact["contact_time"])
    customer_id = contact["cust_id"]
    historical_contacts_30d = series_value(previous_contacts, customer_id, touch_time, 30)
    historical_clicks_90d = series_value(previous_clicks, customer_id, touch_time, 90)
    historical_contacts_90d = series_value(previous_contacts, customer_id, touch_time, 90)
    attribution_record = attribution.get(contact["contact_id"])
    converted = bool(attribution_record and attribution_record["converted"])
    conversion_time = parse_time(str(attribution_record["conversion_time"])) if converted else None
    window_days = int(mapping["attribution_window_days"])
    converted_in_window = bool(converted and conversion_time and conversion_time <= touch_time + timedelta(days=window_days))
    conversion_observed = touch_time + timedelta(days=window_days) <= observed_until
    status = contact["status"]

    row: dict[str, str | float | int] = {
        "touch_id": contact["contact_id"],
        "cust_id": customer_id,
        "campaign_id": contact["campaign_id"],
        "channel": contact["channel"],
        "touch_time": touch_time.isoformat(sep=" "),
        "age": customer.get("age", 0.0),
        "city": customer.get("city", "unknown"),
        "occupation": customer.get("occupation", "unknown"),
        "income_level": customer.get("income_level", "unknown"),
        "education": customer.get("education", "unknown"),
        "active_card_count": customer.get("active_card_count", 0.0),
        "max_credit_amount": customer.get("max_credit_amount", 0.0),
        "strategy_object_type": mapping["strategy_object_type"],
        "product_scope": mapping["product_scope"],
        "benefit_category": mapping["benefit_category"],
        "objective": mapping["objective"],
        "benefit_unit_cost_proxy": float(mapping["benefit_unit_cost_proxy"]),
        "touch_cost": float(contact.get("cost") or channel_costs.get(contact["channel"], 0.0)),
        "touch_hour": float(touch_time.hour),
        "touch_weekday": float(touch_time.weekday()),
        "touch_month": float(touch_time.month),
        "spend_7d": series_value(spend, customer_id, touch_time, 7),
        "spend_30d": series_value(spend, customer_id, touch_time, 30),
        "spend_90d": series_value(spend, customer_id, touch_time, 90),
        "txn_count_30d": series_value(transaction_count, customer_id, touch_time, 30),
        "txn_count_90d": series_value(transaction_count, customer_id, touch_time, 90),
        "app_events_7d": series_value(app_events, customer_id, touch_time, 7),
        "app_events_30d": series_value(app_events, customer_id, touch_time, 30),
        "app_searches_30d": series_value(app_searches, customer_id, touch_time, 30),
        "marketing_contacts_7d": series_value(previous_contacts, customer_id, touch_time, 7),
        "marketing_contacts_30d": historical_contacts_30d,
        "marketing_clicks_90d": historical_clicks_90d,
        "historical_click_rate_90d": historical_clicks_90d / historical_contacts_90d if historical_contacts_90d else 0.0,
        "historical_unsubscribes_90d": series_value(previous_unsubscribes, customer_id, touch_time, 90),
        "overdue_bills_180d": series_value(overdue, customer_id, touch_time, 180),
        "min_payment_bills_180d": series_value(min_payment, customer_id, touch_time, 180),
        "open_label_available": int(contact["channel"] in OPEN_MEASURABLE_CHANNELS),
        "conversion_observed": int(conversion_observed),
        "y_open": int(status in {"opened", "clicked"}),
        "y_click": int(status == "clicked"),
        "y_conversion": int(converted_in_window),
        "y_unsubscribe": int(status == "unsubscribed"),
        "conversion_amount": float(attribution_record["conversion_amount"]) if converted_in_window else 0.0,
        "mapping_source": mapping["mapping_source"],
        # channel-strategy v3 features
        "app_active_days": float(contact.get("app_active_days", 0) or 0),
        "contact_preference": str(contact.get("contact_preference", "未知") or "未知"),
    }
    return row


def build_training_data(output_dir: Path) -> tuple[Path, dict[str, int | str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    customers = load_customer_features()
    spend, transaction_count, app_events, app_searches, overdue, min_payment = load_pre_touch_series()
    contacts, previous_contacts, previous_clicks, previous_unsubscribes = load_contact_history()
    attribution = load_attribution()
    mapping = load_mapping()
    channel_costs = load_channel_costs()
    observed_until = max(parse_time(row["contact_time"]) for row in contacts)

    output_path = output_dir / "marketing_touch_training_v1.csv"
    fieldnames: list[str] | None = None
    row_count = 0
    excluded_status_count = 0
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer: csv.DictWriter | None = None
        for contact in contacts:
            if contact["status"] not in DELIVERED_STATUSES:
                excluded_status_count += 1
                continue
            customer = customers.get(contact["cust_id"])
            campaign_mapping = mapping.get(contact["campaign_id"])
            if customer is None or campaign_mapping is None:
                continue
            row = make_feature_row(
                contact=contact,
                mapping=campaign_mapping,
                customer=customer,
                spend=spend,
                transaction_count=transaction_count,
                app_events=app_events,
                app_searches=app_searches,
                overdue=overdue,
                min_payment=min_payment,
                previous_contacts=previous_contacts,
                previous_clicks=previous_clicks,
                previous_unsubscribes=previous_unsubscribes,
                attribution=attribution,
                channel_costs=channel_costs,
                observed_until=observed_until,
            )
            if writer is None:
                fieldnames = list(row)
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
            writer.writerow(row)
            row_count += 1

    if fieldnames is None:
        raise ValueError("No eligible delivered marketing contacts found")
    summary = {
        "training_rows": row_count,
        "excluded_bounced_rows": excluded_status_count,
        "observed_until": observed_until.isoformat(sep=" "),
        "mapping_count": len(mapping),
    }
    (output_dir / "training_data_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path, summary


FEATURE_COLUMNS = [
    "age", "city", "occupation", "income_level", "education", "active_card_count", "max_credit_amount",
    "campaign_id", "channel", "strategy_object_type", "product_scope", "benefit_category", "objective",
    "benefit_unit_cost_proxy", "touch_cost", "touch_hour", "touch_weekday", "touch_month",
    "spend_7d", "spend_30d", "spend_90d", "txn_count_30d", "txn_count_90d",
    "app_events_7d", "app_events_30d", "app_searches_30d", "marketing_contacts_7d",
    "marketing_contacts_30d", "marketing_clicks_90d", "historical_click_rate_90d",
    "historical_unsubscribes_90d", "overdue_bills_180d", "min_payment_bills_180d",
    "app_active_days", "contact_preference",
]
CATEGORICAL_COLUMNS = {
    "city", "occupation", "income_level", "education", "campaign_id", "channel",
    "strategy_object_type", "product_scope", "benefit_category", "objective",
    "contact_preference",
}


def rows_to_features(rows: list[dict[str, str]]) -> list[dict[str, str | float]]:
    features: list[dict[str, str | float]] = []
    for row in rows:
        item: dict[str, str | float] = {}
        for column in FEATURE_COLUMNS:
            item[column] = row[column] if column in CATEGORICAL_COLUMNS else float(row[column])
        features.append(item)
    return features


def metrics_for(
    model: LogisticRegression,
    vectorizer: DictVectorizer,
    scaler: StandardScaler,
    rows: list[dict[str, str]],
    label: str,
) -> dict[str, float | int]:
    values = [int(row[label]) for row in rows]
    test_matrix = scaler.transform(vectorizer.transform(rows_to_features(rows)))
    probabilities = model.predict_proba(test_matrix)[:, 1]
    positive_rate = sum(values) / len(values)
    top_count = max(1, math.ceil(len(rows) * 0.10))
    ranked = sorted(zip(probabilities, values), reverse=True)[:top_count]
    top_rate = sum(value for _, value in ranked) / top_count
    return {
        "rows": len(rows),
        "positive_rate": round(positive_rate, 6),
        "roc_auc": round(float(roc_auc_score(values, probabilities)), 6),
        "pr_auc": round(float(average_precision_score(values, probabilities)), 6),
        "log_loss": round(float(log_loss(values, probabilities)), 6),
        "top_decile_rate": round(top_rate, 6),
        "top_decile_lift": round(top_rate / positive_rate, 4) if positive_rate else 0.0,
    }


def train_model(
    *,
    rows: list[dict[str, str]],
    label: str,
    model_name: str,
    output_dir: Path,
) -> dict[str, object]:
    rows = sorted(rows, key=lambda row: row["touch_time"])
    train_end = int(len(rows) * 0.70)
    test_start = int(len(rows) * 0.85)
    train_rows = rows[:train_end]
    test_rows = rows[test_start:]
    train_labels = [int(row[label]) for row in train_rows]
    if len(set(train_labels)) < 2 or len({int(row[label]) for row in test_rows}) < 2:
        raise ValueError(f"{model_name} has only one label class after time split")

    vectorizer = DictVectorizer(sparse=True)
    train_matrix = vectorizer.fit_transform(rows_to_features(train_rows))
    scaler = StandardScaler(with_mean=False)
    train_matrix = scaler.fit_transform(train_matrix)
    model = LogisticRegression(max_iter=300, solver="lbfgs", random_state=42)
    model.fit(train_matrix, train_labels)
    metrics = metrics_for(model, vectorizer, scaler, test_rows, label)
    artifact_path = output_dir / f"{model_name}.joblib"
    dump(
        {
            "model": model,
            "vectorizer": vectorizer,
            "scaler": scaler,
            "feature_columns": FEATURE_COLUMNS,
            "label": label,
            "model_name": model_name,
            "training_window_end": train_rows[-1]["touch_time"],
        },
        artifact_path,
    )
    return {"label": label, "artifact": artifact_path.name, "metrics": metrics}


def write_report(output_dir: Path, summary: dict[str, int | str], model_results: dict[str, dict[str, object]]) -> None:
    lines = [
        "# First-Round Historical Response Modeling Report",
        "",
        "## Data Scope",
        "",
        f"- Delivered marketing contacts used for training: {summary['training_rows']}",
        f"- Bounced contacts excluded: {summary['excluded_bounced_rows']}",
        f"- Historical campaign mappings: {summary['mapping_count']}",
        f"- Latest observed touch time: {summary['observed_until']}",
        "- All models use a chronological 70% train / 15% validation gap / 15% test split.",
        "",
        "## Test Metrics",
        "",
        "| Model | Label | Rows | Positive rate | ROC-AUC | PR-AUC | Top-decile lift |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for name, result in model_results.items():
        metrics = result["metrics"]
        assert isinstance(metrics, dict)
        lines.append(
            "| {name} | {label} | {rows} | {positive_rate:.2%} | {roc_auc:.4f} | {pr_auc:.4f} | {top_decile_lift:.2f} |".format(
                name=name,
                label=result["label"],
                rows=metrics["rows"],
                positive_rate=metrics["positive_rate"],
                roc_auc=metrics["roc_auc"],
                pr_auc=metrics["pr_auc"],
                top_decile_lift=metrics["top_decile_lift"],
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- These models are trained on generated historical data and are suitable for demonstrating the decision pipeline, not for claiming production performance.",
            "- Conversion is labeled by a 14-day campaign attribution window. The model must use only features available before touch_time.",
            "- Open prediction is limited to channels with observable open events; SMS, phone, MMS, and direct mail are intentionally excluded from that label.",
            "- Future Marketing Agent feedback should use the same per-touch fields and append to the next training dataset version.",
            "",
        ]
    )
    (output_dir / "training_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and train the first historical marketing response models.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    training_path, summary = build_training_data(args.output_dir)
    rows = read_csv(training_path)
    model_rows: dict[str, tuple[str, Callable[[dict[str, str]], bool]]] = {
        "open_model": ("y_open", lambda row: row["open_label_available"] == "1"),
        "click_model": ("y_click", lambda row: True),
        "conversion_model": ("y_conversion", lambda row: row["conversion_observed"] == "1"),
        "unsubscribe_model": ("y_unsubscribe", lambda row: True),
    }
    results: dict[str, dict[str, object]] = {}
    for model_name, (label, selector) in model_rows.items():
        selected_rows = [row for row in rows if selector(row)]
        results[model_name] = train_model(
            rows=selected_rows,
            label=label,
            model_name=model_name,
            output_dir=args.output_dir,
        )
        print(f"Trained {model_name} with {len(selected_rows)} rows")
    write_report(args.output_dir, summary, results)
    (args.output_dir / "training_metrics.json").write_text(
        json.dumps({"data_summary": summary, "models": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Training artifacts written to {args.output_dir}")


if __name__ == "__main__":
    main()
