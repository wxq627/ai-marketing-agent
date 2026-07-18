# First-Round Historical Response Modeling

## Purpose

This delivery builds a reproducible offline training pipeline for historical marketing response modeling. Its row grain is one delivered marketing touch:

```text
customer x campaign/offer x channel x touch_time
```

The pipeline uses only features available before `touch_time`, then creates four labels for the marketing funnel:

| Label | Definition |
|---|---|
| `y_open` | `1` when the final status is `opened` or `clicked`; only used on channels with observable open events. |
| `y_click` | `1` when the final status is `clicked`. |
| `y_conversion` | `1` when the same `touch_id` has `converted=True` within the campaign's 14-day attribution window. |
| `y_unsubscribe` | `1` when the final status is `unsubscribed`. |

`sent` and `bounced` touches are excluded from the model population because they do not confirm successful delivery.

## Added Artifacts

- `services/strategy-agent/config/campaign_offer_mapping.csv`
  - Maps all 25 historical campaigns to strategy-object type, offer scope, benefit category, cost proxy, objective, and attribution window.
  - Every row is labelled `rule_based_mock`; it is an explicit demo mapping rather than a claimed production product attribution table.
- `services/strategy-agent/scripts/train_historical_response_models.py`
  - Reconstructs pre-touch features from timestamped transactions, app events, bills, and earlier marketing contacts.
  - Builds `marketing_touch_training_v1.csv` locally, trains four chronological logistic-regression baseline models, and writes model artifacts and metrics under `services/strategy-agent/artifacts/historical_modeling_v1/`.

## Run

```powershell
cd C:\Users\15531\Documents\Codex\2026-07-13\ni\outputs\ai-marketing-agent\services\strategy-agent
C:\Python314\python.exe scripts\train_historical_response_models.py
```

The generated training dataset, model files, JSON metrics, and Markdown report are intentionally ignored by Git.

## First Run Result

The first run produced 91,819 delivered marketing-touch training rows from the local A-side history. The chronological held-out test metrics are close to random:

| Model | Test ROC-AUC | Top-decile lift |
|---|---:|---:|
| Open | 0.4884 | 0.98 |
| Click | 0.4933 | 1.00 |
| Conversion | 0.5111 | 0.96 |
| Unsubscribe | 0.5039 | 1.08 |

This is an expected and honest outcome for the current mock data. In `generate_supplementary.py`, contact channel, customer, campaign, and final status are generated largely by independent random sampling. In `generate_attribution.py`, attribution is generated only for historical clicked touches by matching later transactions. Therefore the current labels have almost no learnable relationship to the available pre-touch features.

The pipeline is still useful: it verifies the data joins, prevents time leakage, establishes model inputs and labels, and provides the exact data contract required for future feedback.

## Decision for the Current MVP

Do not replace the existing rule-based strategy score with these first-round model probabilities. Continue to use:

```text
compliance rules + KMeans personas + explainable strategy score + budget constraints
```

Use the four-model pipeline as the demonstrated offline-learning capability. It becomes decision-grade only after receiving behavior-consistent historical data or behavior-consistent simulated feedback.

## Next Data Requirement

The future C-side simulator must emit one event per strategy decision, not only campaign-level aggregates. It should preserve:

```text
decision_id, touch_id, oneid, campaign_id, product_id, benefit_id, channel,
strategy_time, exposed, opened, clicked, converted, conversion_amount,
unsubscribed, complaint, event_time, treatment_or_control
```

For useful simulated learning, outcome probabilities must depend on pre-touch features. For example, product-intent match and app activity can increase open/click/conversion probabilities, while recent contact frequency and complaint risk can increase unsubscribe probability. A control-group flag is additionally required before an uplift model can be trained.
