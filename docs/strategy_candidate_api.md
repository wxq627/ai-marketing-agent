# Strategy Candidate API

## Purpose

This API creates the strategy candidate pool before ranking and budget allocation.
One eligible record represents one `customer x product x channel` combination.
It is the input to the later `StrategyScore(customer, product, channel)` calculation.

## Endpoint

`POST /api/strategy/candidates/real-data`

Example request:

```json
{
  "customer_limit": 200,
  "sample_limit": 100,
  "include_blocked": true
}
```

`customer_limit` limits the number of source customers for a demo run. Set it to `null` to process all available customers. `sample_limit` limits the number of returned records; the full count remains available in `summary`.

## Candidate generation logic

1. Read customer, consent, contact-history, product, benefit and channel data.
2. Apply customer-level compliance and frequency rules.
3. Apply product-level eligibility rules, including age, income, credit, card level and special conditions.
4. Retain only channels allowed for the customer.
5. Output the remaining product-channel combinations with cost, historical channel metrics and benefit identifiers.

## Main response fields

```json
{
  "summary": {
    "eligible_candidate_count": 0,
    "eligible_candidate_by_channel": {
      "app_push": 0
    },
    "top_blocked_reason_codes": []
  },
  "candidate_sample": [
    {
      "candidate_status": "ELIGIBLE",
      "oneid": "UID000001",
      "product_id": "PROD_STANDARD_N",
      "benefit_ids": ["BEN_SPD_003"],
      "channel": "app_push",
      "contact_cost": 0.02,
      "channel_avg_open_rate": 0.18,
      "channel_avg_click_rate": 0.06
    }
  ],
  "blocked_sample": []
}
```

`blocked_sample` is returned only when `include_blocked` is true. Its `reason_codes` are designed for operations review and audit explanations.
