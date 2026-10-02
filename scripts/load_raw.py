"""Load data/raw/*.csv into the warehouse `raw` schema (recreates the raw tables)."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
SQL_DIR = Path(__file__).resolve().parent / "sql"
# load order; parent tables first
TABLES = [
    "branches", "products", "customers", "customer_attribute_history", "accounts", "account_monthly_snapshots",
    "transactions", "loans", "loan_monthly_snapshots", "campaigns", "campaign_responses", "gl_daily_balances",
]


def dsn() -> str:
    return "host={host} port={port} dbname={db} user={user} password={pw}".format(
        host=os.getenv("POSTGRES_HOST", "localhost"), port=os.getenv("POSTGRES_PORT", "5432"),
        db=os.getenv("POSTGRES_DB", "warehouse"), user=os.getenv("POSTGRES_USER", "bank"),
        pw=os.getenv("POSTGRES_PASSWORD", "bank_demo_pw"),
    )


def main() -> None:
    with psycopg.connect(dsn(), autocommit=True) as conn:
        conn.execute((SQL_DIR / "raw_schema.sql").read_text())
        for t in TABLES:
            with conn.cursor() as cur, (RAW_DIR / f"{t}.csv").open("rb") as f:
                with cur.copy(f"COPY raw.{t} FROM STDIN WITH (FORMAT csv, HEADER true)") as cp:
                    while chunk := f.read(1 << 20):
                        cp.write(chunk)
            n = conn.execute(f"SELECT count(*) FROM raw.{t}").fetchone()
            print(f"  raw.{t:30s} {n[0] if n else 0:>10,d}")
        conn.execute("""
            CREATE INDEX ON raw.transactions (posting_date); CREATE INDEX ON raw.transactions (customer_id);
            CREATE INDEX ON raw.account_monthly_snapshots (account_id, month_end);
            CREATE INDEX ON raw.customer_attribute_history (customer_id, valid_from);
            CREATE INDEX ON raw.loan_monthly_snapshots (loan_id, month_end);
            ANALYZE;""")


if __name__ == "__main__":
    main()
