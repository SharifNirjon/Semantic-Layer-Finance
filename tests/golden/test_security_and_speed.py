"""Role enforcement at the Cube layer, and the < 1 s promise for the demo queries."""

from __future__ import annotations

import time

import pytest
from reference import SEP_END, Reference
from story_checks import RAW_DIR

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not (RAW_DIR / "customers.csv").exists(), reason="generate data first"),
]
NARAYANGANJ = 7
SEP = ["2026-09-01", "2026-09-30"]
Q3 = ["2026-07-01", "2026-09-30"]


def q(measure: str, dims: list[str] | None = None, rng: list[str] = SEP, gran: str | None = None,
      filters: list[dict] | None = None) -> dict:
    cube = measure.split(".")[0]
    td: dict = {"dimension": f"{cube}.business_date", "dateRange": rng}
    if gran:
        td["granularity"] = gran
    return {"measures": [measure], "dimensions": dims or [], "timeDimensions": [td], "filters": filters or []}


@pytest.fixture(scope="module")
def bm(token_for) -> str:
    return token_for("branch_manager", NARAYANGANJ)


def test_branch_manager_total_equals_own_branch_not_bank(cube, bm, cmo_token):
    mine = cube.rows(bm, q("balances.total_deposits"))
    bank = cube.rows(cmo_token, q("balances.total_deposits"))
    assert float(mine[0]["balances.total_deposits"]) == pytest.approx(
        Reference().branch_deposits(NARAYANGANJ, SEP_END), rel=1e-4)
    assert float(mine[0]["balances.total_deposits"]) < 0.2 * float(bank[0]["balances.total_deposits"])


@pytest.mark.parametrize("measure", [
    "balances.total_deposits", "loans.loans_outstanding", "transactions.txn_count", "customers.active_customers",
    "campaigns.campaign_cost",
])
def test_branch_manager_only_sees_own_branch_in_every_cube(cube, bm, measure):
    cube_name = measure.split(".")[0]
    rows = cube.rows(bm, q(measure, [f"{cube_name}.branch"], rng=Q3 if cube_name != "campaigns" else ["2024-10-01", "2026-09-30"]))
    assert rows, "expected data for the branch"
    assert {r[f"{cube_name}.branch"] for r in rows} == {"Narayanganj"}


def test_branch_manager_cannot_filter_to_another_branch(cube, bm):
    flt = [{"member": "balances.branch", "operator": "equals", "values": ["Gulshan"]}]
    assert cube.rows(bm, q("balances.total_deposits", ["balances.branch"], filters=flt)) == []


def test_branch_manager_cannot_use_or_filter_to_escape(cube, bm):
    flt = [{"or": [{"member": "balances.branch", "operator": "equals", "values": ["Gulshan"]},
                   {"member": "balances.region", "operator": "equals", "values": ["Dhaka"]}]}]
    rows = cube.rows(bm, q("balances.total_deposits", ["balances.branch"], filters=flt))
    assert {r["balances.branch"] for r in rows} <= {"Narayanganj"}


def test_branch_manager_blocked_from_bank_wide_gl(cube, bm):
    r = cube.load(bm, q("gl_balances.gl_deposits"))
    assert r.status_code >= 400 and "bank-wide" in r.text


def test_branch_manager_token_without_branch_is_rejected(cube, token_for):
    r = cube.load(token_for("branch_manager"), q("balances.total_deposits"))
    assert r.status_code >= 400 and "no branch_id" in r.text


CUSTOMER_LEVEL = {
    "customers.customer_key": "customers.active_customers",
    "balances.account_key": "balances.total_deposits",
    "loans.loan_key": "loans.loans_outstanding",
    "transactions.customer_key": "transactions.txn_count",
}


def test_analyst_sees_aggregates_but_not_customer_level(cube, token_for, cmo_token):
    analyst = token_for("analyst")
    assert cube.rows(analyst, q("balances.total_deposits")) == cube.rows(cmo_token, q("balances.total_deposits"))
    for dim, measure in CUSTOMER_LEVEL.items():
        r = cube.load(analyst, {"measures": [measure], "dimensions": [dim], "limit": 3})
        assert r.status_code >= 400 and "customer-level" in r.text, dim


def test_analyst_cannot_filter_on_customer_level_member(cube, token_for):
    flt = [{"member": "transactions.customer_key", "operator": "equals", "values": ["abc"]}]
    r = cube.load(token_for("analyst"), q("transactions.txn_count", filters=flt))
    assert r.status_code >= 400 and "customer-level" in r.text


def test_cmo_can_use_hashed_customer_key_and_no_raw_ids_exposed(cube, cmo_token):
    rows = cube.rows(cmo_token, {"measures": ["transactions.txn_count"], "dimensions": ["transactions.customer_key"],
                                 "limit": 3, "timeDimensions": [{"dimension": "transactions.business_date",
                                                                 "dateRange": SEP}]})
    keys = [r["transactions.customer_key"] for r in rows]
    assert all(len(k) == 16 and not k.isdigit() for k in keys)


def test_unknown_role_and_bad_signature_are_rejected(cube, token_for):
    assert cube.load(token_for("intern"), q("balances.total_deposits")).status_code >= 400
    assert cube.load("not.a.jwt", q("balances.total_deposits")).status_code in (403, 401, 400, 500)


# -- speed --------------------------------------------------------------------------------------------------------
DASHBOARD_QUERIES = [
    q("balances.total_deposits", gran="month", rng=["2024-10-01", "2026-09-30"]),
    q("balances.casa_ratio", gran="month", rng=["2024-10-01", "2026-09-30"]),
    q("loans.npl_ratio", ["loans.region"], gran="month", rng=["2024-10-01", "2026-09-30"]),
    q("balances.nim", gran="month", rng=["2024-10-01", "2026-09-30"]),
    q("customers.active_customers", ["customers.segment"], gran="month", rng=["2024-10-01", "2026-09-30"]),
    q("customers.churn_rate", ["customers.segment"], gran="month", rng=["2024-10-01", "2026-09-30"]),
    q("transactions.txn_count", ["transactions.channel"], gran="month", rng=["2024-10-01", "2026-09-30"]),
    q("transactions.digital_share", gran="day", rng=["2026-08-01", "2026-09-30"]),
    q("campaigns.cac", ["campaigns.campaign"], rng=["2024-10-01", "2026-09-30"]),
    q("loans.npl_ratio", ["loans.branch", "loans.sector"], rng=SEP),
    q("balances.total_deposits", ["balances.branch"], rng=SEP),
]


@pytest.mark.parametrize("query", DASHBOARD_QUERIES, ids=lambda x: x["measures"][0] + "|" + ",".join(x["dimensions"]))
def test_demo_queries_return_in_under_one_second(cube, cmo_token, query):
    cube.rows(cmo_token, query)  # first call may build the pre-aggregation
    start = time.perf_counter()
    rows = cube.rows(cmo_token, query)
    assert rows
    assert time.perf_counter() - start < 1.0
