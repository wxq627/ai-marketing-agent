# Historical Response Modeling V2

## Purpose

V2 retrains the four marketing-response models after Project A rebuilt `contact_history.csv` and `campaign_attribution.csv` from the same feature-driven generation process. The training row remains one delivered touch:

```text
customer x campaign/offer x channel x touch_time
```

The attribution table now matches the touch-history table on `touch_id`, `cust_id`, `campaign_id`, and `channel` at 100%. This makes the conversion label usable for training.

## Data Contract Changes

- `sent` is now a successful delivery record and is retained as a negative example for open and click labels.
- Per-touch cost is read from `channel_config.csv` when the V2 touch-history extract does not contain a `cost` field.
- `bounced` records remain excluded.
- All features are reconstructed using information available before `touch_time`.

## V1 and V2 Comparison

| Model | V1 ROC-AUC | V2 ROC-AUC | V2 Top-decile Lift | Decision use in the MVP |
|---|---:|---:|---:|---|
| Open | 0.4884 | 0.6494 | 1.33 | Channel visibility signal |
| Click | 0.4933 | 0.6346 | 1.51 | Content and offer-interest signal |
| Conversion | 0.5111 | 0.6183 | 1.63 | Primary positive value signal |
| Unsubscribe | 0.5039 | 0.5806 | 1.77 | Contact-fatigue penalty and suppression signal |

The figures come from a chronological 70% train, 15% validation gap, and 15% held-out test split. V2 has not reached production-model quality; it is a behavior-consistent simulated-data model for the project demo.

## V2 Test Metrics

| Model | Test rows | Positive rate | PR-AUC | Log loss |
|---|---:|---:|---:|---:|
| Open | 9,546 | 62.34% | 0.7472 | 0.6557 |
| Click | 15,882 | 43.26% | 0.5616 | 0.6604 |
| Conversion | 9,095 | 24.82% | 0.3399 | 0.5441 |
| Unsubscribe | 15,882 | 12.27% | 0.1674 | 0.4321 |

## Next Integration Step

For each eligible `customer x product x channel` candidate, the Strategy Agent should call the V2 artifacts and return:

```text
p_open, p_click, p_conversion, p_unsubscribe, model_version
```

The first strategy-value implementation should use conversion as the positive-value signal and unsubscribe as the customer-experience penalty. Open and click provide channel and content evidence but must not be multiplied again into a conversion probability that is already modeled at the delivered-touch level.

```text
strategy_value
= p_conversion x product_margin
- channel_cost
- p_unsubscribe x unsubscribe_loss
```

Product margin, benefit trigger cost, risk loss, LTV, channel capacity, and frequency constraints remain separate policy inputs. They should not be fabricated by the response model.
