# B-C Strategy Serving Contract

## Purpose

The operator console generates a draft. A draft becomes available to the C-side
agent only after an operator publishes it. The C-side agent never reads the
operator web page and never assumes that the most recently generated draft is
effective.

## Lifecycle

```text
generate plan -> save draft -> publish -> strategy_version -> C-side query -> feedback
```

Published versions are immutable. Multiple published campaigns can be active at
the same time when their products or audiences differ. An operator can archive
a version to remove it from C-side serving.

## Operator APIs

### Publish a generated plan

```text
POST /api/strategy/publications
```

```json
{
  "campaign_id": "CMP_...",
  "effective_from": "2026-07-20 10:00:00",
  "effective_to": "2026-08-20 23:59:59"
}
```

`effective_from` defaults to the publish time. The response includes a stable
version such as `STR_CMP_..._001`.

### List or archive versions

```text
GET  /api/strategy/publications?status=published
POST /api/strategy/publications/archive
```

```json
{"strategy_version": "STR_CMP_..._001"}
```

## C-side API

```text
GET /api/strategy/customers/{oneid}/published-context?product=installment
```

The response returns only the active published contexts for that customer. Each
context includes the strategy version, campaign, audience segment, policy
direction, benefit rule, applicable channel constraints, and compliance guard.
It does not expose the full customer list or operator-only data.

The existing C-side endpoints also contain `published_strategy_context`:

```text
GET  /api/strategy/customers/{oneid}/recommendations
POST /api/strategy/decision
```

For a chat decision, C should pass `oneid`, `user_intent`, optional
`product_id`, and a short `conversation_summary`. The strategy context tells C
what it may recommend and how it should describe the offer; C remains
responsible for the final conversational answer.

## Demo Notes

The MVP uses SQLite at `services/strategy-agent/data/marketing_demo.sqlite3`.
For production, replace this repository implementation with a managed database
and add service authentication, authorization, auditing, and encrypted storage.
