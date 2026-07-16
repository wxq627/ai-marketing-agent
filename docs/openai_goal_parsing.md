# OpenAI Goal Parsing

The Strategy Agent can parse an operator's natural-language campaign goal before generating a plan.

## Setup

Set the key in the terminal that starts the Strategy Agent. Do not commit keys to Git.

```powershell
$env:OPENAI_API_KEY = "your_api_key"
$env:OPENAI_MODEL = "gpt-4o-mini"
python app.py
```

Without `OPENAI_API_KEY`, the service remains usable and falls back to the local rule parser.

## Request

```text
POST /api/strategy/parse-goal
```

```json
{
  "goal": "Target high-spend customers with installment interest. Budget 200,000 RMB, prefer App and keep risk low.",
  "product": "installment",
  "channel_mode": "omni",
  "budget_wan": 20,
  "risk_level": 1,
  "frequency_level": 2
}
```

The response contains a validated `campaign_request`, audience hints, constraints, and the source (`openai` or `fallback`).

## Safety Boundary

OpenAI only converts the operator goal into campaign parameters. Customer eligibility, consent, frequency caps, risk filtering, product eligibility, customer selection, and budget enforcement remain deterministic Strategy Agent logic.
