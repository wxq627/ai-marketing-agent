# Stage 3.2 Real Data Strategy Generation

The local Strategy Agent now runs the full decision flow against Project A data:

```text
natural-language goal -> goal parsing -> eligibility -> scoring -> audience segments
-> channel allocation -> B-to-C strategy package
```

## Endpoint

```text
POST /api/strategy/generate/real-data
```

```json
{
  "goal": "Improve installment conversion with a low-risk campaign.",
  "product": "installment",
  "channel_mode": "omni",
  "budget_wan": 20,
  "risk_level": 1,
  "frequency_level": 2,
  "evaluation_time": "2026-07-17T12:00:00+08:00"
}
```

The response contains a plan and a B-to-C strategy package. The package includes only the customers selected after scoring, not every customer who passed eligibility.

Channel budget shares use the Project A channel cost and average click-rate fields. Customer scores use Project A consumption, credit, activity, installment contribution, consent, risk, and contact history fields.
