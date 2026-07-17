from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


SERVICE_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SERVICE_DIR))

from ai_marketing.eligibility import filter_to_eligible_customers
from ai_marketing.knowledge_adapter import customers_from_knowledge_insight
from ai_marketing.local_knowledge_data import LocalKnowledgeData
from ai_marketing.models import CampaignRequest
from ai_marketing.orchestrator import MarketingDecisionEngine
from ai_marketing.persona import FEATURE_NAMES, build_persona_feature_rows
from ai_marketing.recommender import filter_priority_candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate KMeans K with real Project One data.")
    parser.add_argument("--min-k", type=int, default=2)
    parser.add_argument("--max-k", type=int, default=8)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=REPOSITORY_ROOT / "docs" / "kmeans_k_selection_report.md",
    )
    args = parser.parse_args()
    if args.min_k < 2 or args.max_k < args.min_k:
        raise ValueError("K must satisfy 2 <= min_k <= max_k")

    insight = LocalKnowledgeData().build_customer_insight(
        campaign_id="K_SELECTION_REPORT",
        target_product="installment",
        evaluation_time="2026-07-17T12:00:00+08:00",
    )
    engine = MarketingDecisionEngine()
    eligibility = engine.assess_knowledge_insight(insight)
    eligible_payload = filter_to_eligible_customers(insight, eligibility)
    request = CampaignRequest(goal="KMeans K selection", product="installment", budget_wan=20)
    candidates = filter_priority_candidates(customers_from_knowledge_insight(eligible_payload), request)
    features = build_persona_feature_rows(candidates, request.product)
    scaled = StandardScaler().fit_transform(features)

    rows = evaluate_k_values(scaled, args.min_k, args.max_k)
    report = build_report(
        rows=rows,
        candidate_count=len(candidates),
        total_customer_count=len(insight["customers"]),
        eligible_count=eligibility.eligible_count,
        feature_rows=features,
    )
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(report, encoding="utf-8")
    print(f"Report written to {args.report_path}")
    for row in rows:
        print(
            f"K={row['k']} inertia={row['inertia']:.2f} "
            f"silhouette={row['silhouette']:.4f} min_cluster={row['min_cluster_size']}"
        )


def evaluate_k_values(scaled_features, min_k: int, max_k: int) -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []
    sample_size = min(2000, len(scaled_features))
    for k in range(min_k, max_k + 1):
        model = KMeans(n_clusters=k, n_init=20, random_state=42)
        labels = model.fit_predict(scaled_features)
        counts = Counter(int(label) for label in labels)
        rows.append(
            {
                "k": k,
                "inertia": float(model.inertia_),
                "silhouette": float(
                    silhouette_score(scaled_features, labels, sample_size=sample_size, random_state=42)
                ),
                "min_cluster_size": min(counts.values()),
                "max_cluster_size": max(counts.values()),
            }
        )

    for index, row in enumerate(rows):
        if index == 0:
            row["inertia_drop"] = 0.0
        else:
            previous = float(rows[index - 1]["inertia"])
            row["inertia_drop"] = (previous - float(row["inertia"])) / previous
    return rows


def build_report(
    *,
    rows: list[dict[str, float | int]],
    candidate_count: int,
    total_customer_count: int,
    eligible_count: int,
    feature_rows: list[list[float]],
) -> str:
    operational_rows = [row for row in rows if 3 <= int(row["k"]) <= 6]
    recommended = max(operational_rows or rows, key=lambda row: float(row["silhouette"]))
    elbow = _elbow_candidate(rows)
    zero_variance_features = [
        name
        for index, name in enumerate(FEATURE_NAMES)
        if len({round(row[index], 12) for row in feature_rows}) <= 1
    ]
    table_rows = "\n".join(
        "| {k} | {inertia:.2f} | {drop:.2%} | {silhouette:.4f} | {minimum} | {maximum} |".format(
            k=int(row["k"]),
            inertia=float(row["inertia"]),
            drop=float(row["inertia_drop"]),
            silhouette=float(row["silhouette"]),
            minimum=int(row["min_cluster_size"]),
            maximum=int(row["max_cluster_size"]),
        )
        for row in rows
    )
    zero_variance_note = "无" if not zero_variance_features else "、".join(zero_variance_features)
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    return f"""# KMeans 选 K 报告

生成时间：{now}

## 结论

本轮建议采用 **K={int(recommended['k'])}**。

- 在适合运营落地的 K=3~6 范围内，它的轮廓系数最高，为 **{float(recommended['silhouette']):.4f}**。
- 肘部法则的拐点候选为 **K={int(elbow['k'])}**：此后惯性下降开始明显放缓。
- 最小簇规模为 **{int(recommended['min_cluster_size'])}**，可支持各群独立投放和实验。

最终选择不只依赖单一数学指标：轮廓系数决定分群质量，肘部法则避免过度切分，运营上再限制 K 不超过 6 以保证策略可解释和可执行。

## 数据范围

| 项目 | 数量 |
|---|---:|
| A 端原始客户 | {total_customer_count} |
| 阶段二合规通过客户 | {eligible_count} |
| 进入 KMeans 的候选客户 | {candidate_count} |

聚类特征：{"、".join(FEATURE_NAMES)}。

## 指标结果

轮廓系数在 2,000 人随机固定样本上计算，随机种子为 42；惯性值在全量候选客户上计算。

| K | 惯性值 Inertia | 相对下降 | 轮廓系数 | 最小簇规模 | 最大簇规模 |
|---:|---:|---:|---:|---:|---:|
{table_rows}

## 使用说明

1. 当前生产策略仍以 K={int(recommended['k'])} 为默认值；代码中的簇数应与本报告同步更新。
2. 每次意图特征、行为窗口或数据版本明显变化后，重新运行本脚本。
3. 零方差特征：{zero_variance_note}。这类特征在本轮不区分客户，后续应补充有效数据或暂时移除。
4. 选 K 后仍需人工检查每群的规模、画像差异和策略差异，不能只看分数。
"""


def _elbow_candidate(rows: list[dict[str, float | int]]) -> dict[str, float | int]:
    drops = [float(row["inertia_drop"]) for row in rows[1:]]
    threshold = sum(drops) / len(drops) if drops else 0.0
    return next((row for row in rows[1:] if float(row["inertia_drop"]) <= threshold), rows[-1])


if __name__ == "__main__":
    main()
