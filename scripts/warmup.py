"""Block until Cube has built its pre-aggregations, so the first demo query is already fast.

Usage: python scripts/warmup.py [--cube-url http://localhost:4000] [--timeout 600]
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import httpx
import jwt

QUERIES = [
    {"measures": ["balances.total_deposits", "balances.casa_ratio", "balances.nim"], "dimensions": ["balances.branch"],
     "timeDimensions": [{"dimension": "balances.business_date", "granularity": "month", "dateRange": ["2024-10-01", "2026-12-31"]}]},
    {"measures": ["loans.npl_ratio"], "dimensions": ["loans.branch", "loans.sector"],
     "timeDimensions": [{"dimension": "loans.business_date", "granularity": "month", "dateRange": ["2024-10-01", "2026-12-31"]}]},
    {"measures": ["customers.churn_rate", "customers.active_customers"], "dimensions": ["customers.segment"],
     "timeDimensions": [{"dimension": "customers.business_date", "granularity": "month", "dateRange": ["2024-10-01", "2026-12-31"]}]},
    {"measures": ["transactions.txn_count"], "dimensions": ["transactions.channel"],
     "timeDimensions": [{"dimension": "transactions.business_date", "granularity": "month", "dateRange": ["2024-10-01", "2026-12-31"]}]},
    {"measures": ["transactions.txn_count"], "dimensions": ["transactions.channel"],
     "timeDimensions": [{"dimension": "transactions.business_date", "granularity": "day", "dateRange": ["2026-08-01", "2026-09-30"]}]},
    {"measures": ["campaigns.cac"], "dimensions": ["campaigns.campaign"],
     "timeDimensions": [{"dimension": "campaigns.business_date", "dateRange": ["2024-10-01", "2026-12-31"]}]},
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cube-url", default=os.getenv("CUBE_URL", "http://localhost:4000"))
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()
    secret = os.getenv("JWT_SECRET", "change-me-demo-secret-at-least-32-chars-long")
    token = jwt.encode({"role": "cmo", "sub": "warmup", "exp": int(time.time()) + 3600}, secret, algorithm="HS256")
    deadline = time.time() + args.timeout
    pending = list(QUERIES)
    while pending and time.time() < deadline:
        for q in list(pending):
            try:
                r = httpx.post(f"{args.cube_url}/cubejs-api/v1/load", headers={"Authorization": token},
                               json={"query": q}, timeout=120)
                body = r.json()
            except httpx.HTTPError:
                continue
            if r.status_code == 200 and body.get("error") != "Continue wait":
                pending.remove(q)
        if pending:
            time.sleep(3)
    if pending:
        print(f"warmup timed out with {len(pending)} queries still building", file=sys.stderr)
        return 1
    print("pre-aggregations are built")
    return 0


if __name__ == "__main__":
    sys.exit(main())
