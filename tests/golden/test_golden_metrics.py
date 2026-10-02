"""Golden tests: Cube must return the same numbers as an independent pandas computation (tolerance 0.01%)."""

from __future__ import annotations

import pytest
from reference import Q3_END, Q3_START, SEP_END, Reference
from story_checks import RAW_DIR

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not (RAW_DIR / "customers.csv").exists(), reason="generate data first"),
]
SEP = ("2026-09-01", "2026-09-30")
Q3 = ("2026-07-01", "2026-09-30")
REL = 1e-4  # 0.01 %


@pytest.fixture(scope="module")
def ref() -> Reference:
    return Reference()


def seg_filter(cube_name: str, segment: str) -> list[dict]:
    return [{"member": f"{cube_name}.segment", "operator": "equals", "values": [segment]}]


def check(actual: float, expected: float) -> None:
    assert actual == pytest.approx(expected, rel=REL), f"cube={actual} pandas={expected}"


def test_total_deposits(cube, cmo_token, ref):
    check(cube.value(cmo_token, "balances.total_deposits", SEP), ref.total_deposits())


def test_casa_ratio(cube, cmo_token, ref):
    check(cube.value(cmo_token, "balances.casa_ratio", SEP), ref.casa_ratio())


def test_avg_deposits_month(cube, cmo_token, ref):
    check(cube.value(cmo_token, "balances.avg_deposits", SEP), ref.avg_deposits_month())


def test_active_customers(cube, cmo_token, ref):
    check(cube.value(cmo_token, "customers.active_customers", SEP), ref.active_customers())


def test_new_customers_q3(cube, cmo_token, ref):
    check(cube.value(cmo_token, "customers.new_customers", Q3), ref.new_customers())


def test_churn_rate_young_professionals_q3(cube, cmo_token, ref):
    actual = cube.value(cmo_token, "customers.churn_rate", Q3, seg_filter("customers", "Young Professionals"))
    check(actual, ref.churn_rate("Young Professionals", Q3_START, Q3_END))


def test_churn_rate_bank_q3(cube, cmo_token, ref):
    check(cube.value(cmo_token, "customers.churn_rate", Q3), ref.churn_rate(None))


def test_products_per_customer_and_cross_sell(cube, cmo_token, ref):
    ppc, xsell = ref.products_held()
    check(cube.value(cmo_token, "customers.products_per_customer", SEP), ppc)
    check(cube.value(cmo_token, "customers.cross_sell_rate", SEP), xsell)


def test_loans_outstanding(cube, cmo_token, ref):
    check(cube.value(cmo_token, "loans.loans_outstanding", SEP), ref.loans_outstanding())


def test_npl_ratio(cube, cmo_token, ref):
    check(cube.value(cmo_token, "loans.npl_ratio", SEP), ref.npl_ratio())


def test_provision_coverage(cube, cmo_token, ref):
    check(cube.value(cmo_token, "loans.provision_coverage", SEP), ref.provision_coverage())


def test_loans_disbursed_q3(cube, cmo_token, ref):
    check(cube.value(cmo_token, "loans.loans_disbursed", Q3), ref.loans_disbursed())


def test_net_interest_income_and_nim_q3(cube, cmo_token, ref):
    nii, nim = ref.nii_and_nim()
    check(cube.value(cmo_token, "balances.net_interest_income", Q3), nii)
    check(cube.value(cmo_token, "balances.nim", Q3), nim)


def test_transaction_metrics_q3(cube, cmo_token, ref):
    count, value, share = ref.txn_metrics()
    check(cube.value(cmo_token, "transactions.txn_count", Q3), count)
    check(cube.value(cmo_token, "transactions.txn_value", Q3), value)
    check(cube.value(cmo_token, "transactions.digital_share", Q3), share)


@pytest.mark.parametrize("name", ["Eid Cashback Blast", "Student Referral Rewards"])
def test_campaign_metrics(cube, cmo_token, ref, name):
    row = ref.campaign(name)
    flt = [{"member": "campaigns.campaign", "operator": "equals", "values": [name]}]
    window = ("2024-10-01", "2026-09-30")
    check(cube.value(cmo_token, "campaigns.campaign_cost", window, flt), row.cost)
    check(cube.value(cmo_token, "campaigns.campaign_response_rate", window, flt), row.response_rate)
    check(cube.value(cmo_token, "campaigns.campaign_conversion_rate", window, flt), row.conversion_rate)
    check(cube.value(cmo_token, "campaigns.cac", window, flt), row.cac)


def test_gl_matches_marts_at_period_end(cube, cmo_token, ref):
    gl = cube.value(cmo_token, "gl_balances.gl_deposits", SEP)
    check(gl, ref.total_deposits(SEP_END))
