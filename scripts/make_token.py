"""Print a demo JWT for connecting an external MCP client (Claude Desktop etc.) to the governed metrics server.

    python scripts/make_token.py cmo
    python scripts/make_token.py branch_manager --branch 7
    python scripts/make_token.py analyst --hours 24

The token is signed with JWT_SECRET (default: the demo secret from .env.example). Never reuse the demo secret outside a demo.
"""

from __future__ import annotations

import argparse
import os
import time

import jwt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("role", choices=["cmo", "branch_manager", "analyst"])
    ap.add_argument("--branch", type=int, default=7, help="branch id for branch_manager (7 = Narayanganj)")
    ap.add_argument("--hours", type=int, default=8)
    args = ap.parse_args()
    claims: dict[str, object] = {"sub": f"mcp-client-{args.role}", "role": args.role,
                                 "exp": int(time.time()) + args.hours * 3600}
    if args.role == "branch_manager":
        claims["branch_id"] = args.branch
    secret = os.getenv("JWT_SECRET", "change-me-demo-secret-at-least-32-chars-long")
    print(jwt.encode(claims, secret, algorithm="HS256"))


if __name__ == "__main__":
    main()
