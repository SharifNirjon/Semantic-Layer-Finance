"""Phase 1 acceptance: row counts, referential integrity and planted stories over data/raw/*.csv."""

from __future__ import annotations

import pytest
from story_checks import RAW_DIR, load_all, quality_report, story_figures

pytestmark = pytest.mark.skipif(not (RAW_DIR / "customers.csv").exists(), reason="run scripts/generate_data.py first")


@pytest.fixture(scope="module")
def tables():
    return load_all()


def test_quality_report_has_no_failures(tables):
    failed = [(n, d) for n, ok, d in quality_report(tables) if not ok]
    assert not failed, failed


@pytest.fixture(scope="module")
def stories(tables):
    return story_figures(tables)


def test_story_a_young_professional_churn_spikes(stories):
    assert stories["a_yp_churn_last_quarter_avg_monthly"] > 2.5 * stories["a_yp_churn_prior_21m_avg_monthly"]
    assert stories["a_yp_churn_last_quarter_avg_monthly"] > 2 * stories["a_bank_churn_last_quarter_avg_monthly"]


def test_story_b_rmg_npl_rises_in_two_branches(stories):
    assert stories["b_stress_npl_ratio_last"] > 5 * stories["b_stress_npl_ratio_first"]
    assert stories["b_stress_npl_ratio_last"] > 5 * stories["b_rest_npl_ratio_last"]


def test_story_c_casa_declines_as_fd_grows(stories):
    assert stories["c_casa_ratio_first"] - stories["c_casa_ratio_last"] > 0.05
    assert stories["c_fd_balance_growth"] > 0.5


def test_story_d_campaign_effectiveness(stories):
    camp = stories["d_campaigns"].set_index("campaign_name")
    assert camp.cac.idxmin() == "Student Referral Rewards"
    eid = camp.loc["Eid Cashback Blast"]
    assert eid.response_rate > 2 * camp.response_rate.median()
    assert eid.conversion_rate < 0.5 * camp.conversion_rate.median()


def test_story_e_mobile_overtakes_atm(stories):
    m0, a0, m1, a1 = stories["e_mobile_atm_first_last"]
    assert m0 < a0 and m1 > a1
    assert stories["e_first_month_mobile_exceeds_atm"] is not None
