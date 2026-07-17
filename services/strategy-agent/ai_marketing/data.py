from __future__ import annotations

import random

from .models import Customer


def load_demo_customers(count: int = 1500, seed: int = 202707) -> list[Customer]:
    """Create deterministic synthetic customers for local demos and tests."""
    rng = random.Random(seed)
    customers: list[Customer] = []
    for idx in range(count):
        spend = max(300, rng.gauss(5200, 2600))
        dining = max(0, int(rng.gauss(9, 5)))
        travel = max(0, int(rng.gauss(2, 2)))
        online = max(0, int(rng.gauss(16, 8)))
        app_days = max(0, min(30, int(rng.gauss(18, 8))))
        usage = max(0.03, min(0.96, rng.betavariate(2.3, 3.2)))
        coupon_response = max(0.02, min(0.92, rng.betavariate(2.2, 3.6)))
        installment_history = rng.choices([0, 1, 2, 3], weights=[52, 28, 14, 6])[0]
        complaint_risk = max(0.005, min(0.35, rng.betavariate(1.4, 18)))
        recent_contacts = rng.choices([0, 1, 2, 3, 4], weights=[35, 28, 20, 12, 5])[0]
        consent = rng.random() > 0.08
        customers.append(
            Customer(
                customer_id=f"C{idx + 1:06d}",
                age=rng.randint(22, 62),
                city_tier=rng.choices([1, 2, 3, 4], weights=[28, 36, 24, 12])[0],
                monthly_spend=round(spend, 2),
                dining_txn=dining,
                travel_txn=travel,
                online_txn=online,
                credit_limit_usage=round(usage, 4),
                coupon_response=round(coupon_response, 4),
                installment_history=installment_history,
                app_active_days=app_days,
                recent_contacts=recent_contacts,
                complaint_risk=round(complaint_risk, 4),
                has_marketing_consent=consent,
            )
        )
    return customers
