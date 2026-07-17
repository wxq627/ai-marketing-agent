# Stage 2 Real Data Run

The Strategy Agent can evaluate Project A's local desensitized CSV data before the Knowledge Agent API is available.

## Endpoint

```text
POST /api/strategy/eligibility/real-data
```

```json
{
  "campaign_id": "CMP_REAL_001",
  "target_product": "installment",
  "evaluation_time": "2026-07-17T12:00:00+08:00"
}
```

The endpoint reads the Project A customer profile, consent, contact history, and channel configuration files. It returns an eligibility summary and the first 20 decisions. Send `"include_decisions": true` only when the full decision list is required.

## Temporary Local Adapter

`ai_marketing/local_knowledge_data.py` is a local CSV adapter. When Project A exposes the Knowledge Agent API, replace only this adapter's data-loading step. The eligibility engine and its output contract remain unchanged.
