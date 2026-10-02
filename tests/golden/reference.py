"""Independent pandas implementation of the governed metrics, computed straight from the raw CSVs.

Deliberately shares no code or SQL with dbt or Cube. The golden tests assert that Cube returns the same numbers.
"""

from __future__ import annotations

from functools import cached_property

import pandas as pd
from story_checks import (
    NPL_CLASSES,
    campaign_table,
    churn_by_month,
    load_all,
    segment_asof,
)

PROVISION_RATE = {"Standard": 0.01, "SMA": 0.05, "Substandard": 0.20, "Doubtful": 0.50, "Bad-Loss": 1.00}
Q3_START, Q3_END = pd.Timestamp("2026-07-01"), pd.Timestamp("2026-09-30")
SEP_END = pd.Timestamp("2026-09-30")


class Reference:
    def __init__(self) -> None:
        self.t = load_all()

    @cached_property
    def snaps(self) -> pd.DataFrame:
        s = self.t["account_monthly_snapshots"].merge(self.t["accounts"][["account_id", "customer_id", "product_id"]],
                                                      on="account_id")
        return s.merge(self.t["products"][["product_id", "category", "is_casa", "product_name"]], on="product_id")

    def _month(self, df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        return df[(df.month_end >= start) & (df.month_end <= end)]

    def total_deposits(self, me: pd.Timestamp = SEP_END) -> float:
        s = self.snaps
        return float(s[(s.month_end == me) & (s.category == "Deposit")].closing_balance.sum())

    def casa_ratio(self, me: pd.Timestamp = SEP_END) -> float:
        s = self.snaps
        d = s[(s.month_end == me) & (s.category == "Deposit")]
        return float(d[d.is_casa].closing_balance.sum() / d.closing_balance.sum())

    def avg_deposits_month(self, me: pd.Timestamp = SEP_END) -> float:
        s = self.snaps
        return float(s[(s.month_end == me) & (s.category == "Deposit")].avg_daily_balance.sum())

    def customers_at(self, me: pd.Timestamp) -> pd.DataFrame:
        c = self.t["customers"]
        return c[(c.acquisition_date <= me) & (c.churn_date.isna() | (c.churn_date > me))]

    def active_customers(self, me: pd.Timestamp = SEP_END) -> int:
        tx = self.t["transactions"]
        recent = tx[(tx.posting_date > me - pd.Timedelta(days=90)) & (tx.posting_date <= me)].customer_id.unique()
        return int(self.customers_at(me).customer_id.isin(recent).sum())

    def new_customers(self, start: pd.Timestamp = Q3_START, end: pd.Timestamp = Q3_END) -> int:
        c = self.t["customers"]
        return int(((c.acquisition_date >= start) & (c.acquisition_date <= end)).sum())

    def churn_rate(self, segment: str | None, start: pd.Timestamp = Q3_START, end: pd.Timestamp = Q3_END) -> float:
        m = churn_by_month(self.t, segment)
        m = m[(m.month_end >= start) & (m.month_end <= end)]
        return float(m.churned.sum() / m.opening.sum())

    def products_held(self, me: pd.Timestamp = SEP_END) -> tuple[float, float]:
        """(products_per_customer, cross_sell_rate) at month end."""
        a = self.t["accounts"]
        open_ = a[(a.open_date <= me) & (a.close_date.isna() | (a.close_date > me))]
        n = open_.groupby("customer_id").product_id.nunique()
        cust = self.customers_at(me).customer_id
        n = n.reindex(cust).fillna(0)
        return float(n.sum() / len(cust)), float((n >= 2).sum() / len(cust))

    def loans_at(self, me: pd.Timestamp = SEP_END) -> pd.DataFrame:
        s = self.t["loan_monthly_snapshots"]
        return s[s.month_end == me]

    def loans_outstanding(self, me: pd.Timestamp = SEP_END) -> float:
        return float(self.loans_at(me).outstanding.sum())

    def npl_ratio(self, me: pd.Timestamp = SEP_END) -> float:
        s = self.loans_at(me)
        return float(s[s.classification.isin(NPL_CLASSES)].outstanding.sum() / s.outstanding.sum())

    def provision_coverage(self, me: pd.Timestamp = SEP_END) -> float:
        s = self.loans_at(me)
        prov = (s.outstanding * s.classification.map(PROVISION_RATE)).sum()
        return float(prov / s[s.classification.isin(NPL_CLASSES)].outstanding.sum())

    def loans_disbursed(self, start: pd.Timestamp = Q3_START, end: pd.Timestamp = Q3_END) -> float:
        loans = self.t["loans"]
        disb = loans[(loans.disbursed_date >= start) & (loans.disbursed_date <= end)].copy()
        disb["month_end"] = disb.disbursed_date + pd.offsets.MonthEnd(0)
        live = self.t["loan_monthly_snapshots"][["loan_id", "month_end"]]
        return float(disb.merge(live, on=["loan_id", "month_end"]).principal.sum())

    def nii_and_nim(self, start: pd.Timestamp = Q3_START, end: pd.Timestamp = Q3_END) -> tuple[float, float]:
        s = self._month(self.snaps, start, end)
        income = s[s.category == "Loan"].interest_accrued.sum()
        expense = s[s.category == "Deposit"].interest_accrued.sum()
        earning = s[s.category == "Loan"].avg_daily_balance.sum()
        nii = income - expense
        return float(nii), float(12 * nii / earning)

    def txn_metrics(self, start: pd.Timestamp = Q3_START, end: pd.Timestamp = Q3_END) -> tuple[int, float, float]:
        tx = self.t["transactions"]
        x = tx[(tx.posting_date >= start) & (tx.posting_date <= end)]
        return len(x), float(x.amount.sum()), float(x.channel.isin(["mobile", "internet"]).mean())

    def campaign(self, name: str) -> pd.Series:
        c = campaign_table(self.t)
        return c[c.campaign_name == name].iloc[0]

    def branch_deposits(self, branch_id: int, me: pd.Timestamp = SEP_END) -> float:
        s = self.snaps
        d = s[(s.month_end == me) & (s.category == "Deposit")]
        branch = segment_asof(self.t, d.customer_id, me).home_branch_id.to_numpy()
        return float(d[branch == branch_id].closing_balance.sum())
