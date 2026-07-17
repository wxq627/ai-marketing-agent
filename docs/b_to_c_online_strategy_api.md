# B to C Online Strategy API

## Shared rules

- C only sends `oneid` and the current interaction context. It must not send or store raw customer profile data.
- B reads customer, consent, intent, behavior, product, benefit, and eligibility data locally for the demo.
- A `404` means the `oneid` is unknown. A response with no recommendations means the customer is not eligible for personalized marketing.

## 1. Agent home recommendations

```text
GET /api/strategy/customers/{oneid}/recommendations?scene=agent_home&limit=5
```

Example:

```text
GET /api/strategy/customers/UID000001/recommendations?scene=agent_home&limit=5
```

Response fields:

```json
{
  "oneid": "UID000001",
  "scene": "agent_home",
  "strategy_version": "online_personalization_v1",
  "recommendations": [
    {
      "rank": 1,
      "recommendation_id": "...",
      "product_id": "PROD_STANDARD_N",
      "benefit_id": "BEN_SPD_003",
      "title": "product name",
      "subtitle": "benefit summary",
      "reason": "short personalized reason",
      "persona_name": "persona name",
      "segment_id": "SEG003",
      "action": "view offer",
      "allowed_channels": ["in_app"],
      "strategy": {
        "offer_direction": "...",
        "content_direction": "..."
      }
    }
  ]
}
```

C renders `title`, `subtitle`, `reason`, and `action` as an offer card. `product_id` is used to open a product detail page or to start a product-specific conversation.

## 2. Chat strategy decision

```text
POST /api/strategy/decision
Content-Type: application/json
```

Request:

```json
{
  "oneid": "UID000001",
  "scene": "chat",
  "user_intent": "customer wants to understand installment fees",
  "product_id": "INSTALLMENT",
  "conversation_summary": "customer is comparing installment options",
  "touchpoint": "in_app"
}
```

Response:

```json
{
  "oneid": "UID000001",
  "scene": "chat",
  "should_recommend": true,
  "persona_name": "persona name",
  "segment_id": "SEG003",
  "next_best_action": "recommended next action",
  "recommended_product_id": "INSTALLMENT",
  "recommended_benefit_id": "INSTALLMENT_FEE_COUPON",
  "offer_direction": "...",
  "content_direction": "...",
  "allowed_channels": ["in_app"],
  "compliance_notes": ["..."]
}
```

C answers product facts with the Knowledge Agent. It uses this response only to decide whether to recommend, what to recommend, and which content direction to follow.
