"""Pandas-only checks of the planted stories and basic data quality over data/raw/*.csv.

Independent of the generator and of Cube/dbt, so it can serve as ground truth for docs and tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
DATE_COLS = {
    "customers": ["acquisition_date", "churn_date"],
    "customer_attribute_history": ["valid_from", "valid_to"],
    "accounts": ["open_date", "close_date"],
    "account_monthly_snapshots": ["month_end"],
    "transactions": ["posting_date", "value_date"],
    "loans": ["disbursed_date"],
    "loan_monthly_snapshots": ["month_end"],
    "campaigns": ["start_date", "end_date"],
    "campaign_responses": ["response_date"],
    "gl_daily_balances": ["gl_date"],
    "branches": ["opened_date"],
}
STRESS_BRANCHES = ["Narayanganj", "Gazipur"]
NPL_CLASSES = ["Substandard", "Doubtful", "Bad-Loss"]
RMG = "RMG / Garments"
EXPECTED_COUNTS = {"branches": 25, "customers": 50_000, "accounts": 110_000, "transactions": 2_000_000}


def load(name: str, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    return pd.read_csv(raw_dir / f"{name}.csv", parse_dates=DATE_COLS.get(name, []))


def load_all(raw_dir: Path = RAW_DIR) -> dict[str, pd.DataFrame]:
    return {n: load(n, raw_dir) for n in [*DATE_COLS, "products"]}


def month_ends(t: dict[str, pd.DataFrame]) -> list[pd.Timestamp]:
    return sorted(t["account_monthly_snapshots"].month_end.unique())


def segment_asof(t: dict[str, pd.DataFrame], cust_ids: pd.Series, when: pd.Timestamp) -> pd.DataFrame:
    h = t["customer_attribute_history"]
    h = h[h.valid_from <= when]
    h = h[(h.valid_to.isna()) | (h.valid_to > when)]
    return h.set_index("customer_id").loc[:, ["segment", "home_branch_id"]].reindex(cust_ids.to_numpy())


def churn_by_month(t: dict[str, pd.DataFrame], segment: str | None = None) -> pd.DataFrame:
    """Monthly churn rate = churned in month / customers at start of month (segment as of month end)."""
    c = t["customers"]
    rows = []
    for me in month_ends(t):
        ms = me.replace(day=1)
        opening = c[(c.acquisition_date < ms) & (c.churn_date.isna() | (c.churn_date >= ms))]
        attrs = segment_asof(t, opening.customer_id, me)
        if segment:
            opening = opening[(attrs.segment == segment).to_numpy()]
        churned = opening[(opening.churn_date >= ms) & (opening.churn_date <= me)]
        rows.append((me, len(opening), len(churned), len(churned) / max(len(opening), 1)))
    return pd.DataFrame(rows, columns=["month_end", "opening", "churned", "churn_rate"])


def npl_by_month(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    s = t["loan_monthly_snapshots"].merge(t["loans"][["loan_id", "sector", "customer_id"]], on="loan_id")
    br = t["branches"].set_index("branch_id").branch_name
    out = []
    for me, g in s.groupby("month_end"):
        branch = br.reindex(segment_asof(t, g.customer_id, me).home_branch_id.to_numpy()).to_numpy()
        stress = (g.sector.to_numpy() == RMG) & pd.Series(branch).isin(STRESS_BRANCHES).to_numpy()
        for label, mask in (("stress_slice", stress), ("rest", ~stress), ("bank", slice(None))):
            gg = g[mask]
            out.append((me, label, gg.outstanding.sum(),
                        gg.loc[gg.classification.isin(NPL_CLASSES), "outstanding"].sum()))
    df = pd.DataFrame(out, columns=["month_end", "slice", "outstanding", "npl"])
    df["npl_ratio"] = df.npl / df.outstanding
    return df


def casa_by_month(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    s = t["account_monthly_snapshots"].merge(t["accounts"][["account_id", "product_id"]], on="account_id")
    s = s.merge(t["products"][["product_id", "category", "is_casa", "product_name"]], on="product_id")
    d = s[s.category == "Deposit"]
    g = d.groupby("month_end").apply(
        lambda x: pd.Series({
            "deposits": x.closing_balance.sum(),
            "casa": x.loc[x.is_casa, "closing_balance"].sum(),
            "fd": x.loc[x.product_name == "Fixed Deposit", "closing_balance"].sum(),
        }), include_groups=False)
    g["casa_ratio"] = g.casa / g.deposits
    return g.reset_index()


def campaign_table(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    r = t["campaign_responses"]
    agg = r.groupby("campaign_id").agg(targeted=("customer_id", "size"), responded=("responded", "sum"),
                                       converted=("converted_product", lambda x: x.notna().sum()))
    out = t["campaigns"].set_index("campaign_id").join(agg)
    out["response_rate"] = out.responded / out.targeted
    out["conversion_rate"] = out.converted / out.responded
    out["cac"] = out.cost / out.converted
    return out.reset_index()


def channel_by_month(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    x = t["transactions"]
    x = x.assign(month_end=x.posting_date + pd.offsets.MonthEnd(0))
    return x.pivot_table(index="month_end", columns="channel", values="txn_id", aggfunc="count").reset_index()


def story_figures(t: dict[str, pd.DataFrame]) -> dict[str, Any]:
    mends = month_ends(t)
    yp = churn_by_month(t, "Young Professionals")
    allc = churn_by_month(t)
    last_q, prev = yp.tail(3), yp.iloc[:-3]
    npl = npl_by_month(t)
    stress = npl[npl.slice == "stress_slice"].set_index("month_end").npl_ratio
    rest = npl[npl.slice == "rest"].set_index("month_end").npl_ratio
    casa = casa_by_month(t)
    camp = campaign_table(t)
    ch = channel_by_month(t).set_index("month_end")
    cross = ch.index[(ch["mobile"] > ch["ATM"])]
    return {
        "months": f"{mends[0].date()} .. {mends[-1].date()}",
        "a_yp_churn_last_quarter_avg_monthly": last_q.churned.sum() / last_q.opening.sum(),
        "a_yp_churn_prior_21m_avg_monthly": prev.churned.sum() / prev.opening.sum(),
        "a_yp_churn_by_month_last6": dict(zip([d.strftime("%Y-%m") for d in yp.month_end.tail(6)],
                                              yp.churn_rate.tail(6).round(4), strict=True)),
        "a_bank_churn_last_quarter_avg_monthly": allc.tail(3).churned.sum() / allc.tail(3).opening.sum(),
        "b_stress_npl_ratio_first": stress.iloc[0], "b_stress_npl_ratio_last": stress.iloc[-1],
        "b_rest_npl_ratio_first": rest.iloc[0], "b_rest_npl_ratio_last": rest.iloc[-1],
        "c_casa_ratio_first": casa.casa_ratio.iloc[0], "c_casa_ratio_last": casa.casa_ratio.iloc[-1],
        "c_fd_balance_growth": casa.fd.iloc[-1] / casa.fd.iloc[0] - 1,
        "d_campaigns": camp[["campaign_name", "cost", "targeted", "responded", "converted", "response_rate",
                             "conversion_rate", "cac"]],
        "e_first_month_mobile_exceeds_atm": cross.min() if len(cross) else None,
        "e_mobile_atm_first_last": (int(ch["mobile"].iloc[0]), int(ch["ATM"].iloc[0]),
                                    int(ch["mobile"].iloc[-1]), int(ch["ATM"].iloc[-1])),
    }


def quality_report(t: dict[str, pd.DataFrame]) -> list[tuple[str, bool, str]]:
    res: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        res.append((name, bool(ok), detail))

    for table, expected in EXPECTED_COUNTS.items():
        n = len(t[table])
        check(f"row count {table}", abs(n - expected) / expected <= 0.05, f"{n:,} (target ~{expected:,})")
    fks = [
        ("customers.home_branch_id", t["customers"].home_branch_id, t["branches"].branch_id),
        ("accounts.customer_id", t["accounts"].customer_id, t["customers"].customer_id),
        ("accounts.product_id", t["accounts"].product_id, t["products"].product_id),
        ("accounts.branch_id", t["accounts"].branch_id, t["branches"].branch_id),
        ("snapshots.account_id", t["account_monthly_snapshots"].account_id, t["accounts"].account_id),
        ("transactions.account_id", t["transactions"].account_id, t["accounts"].account_id),
        ("transactions.customer_id", t["transactions"].customer_id, t["customers"].customer_id),
        ("loans.account_id", t["loans"].account_id, t["accounts"].account_id),
        ("loan_snapshots.loan_id", t["loan_monthly_snapshots"].loan_id, t["loans"].loan_id),
        ("responses.customer_id", t["campaign_responses"].customer_id, t["customers"].customer_id),
        ("responses.campaign_id", t["campaign_responses"].campaign_id, t["campaigns"].campaign_id),
        ("history.customer_id", t["customer_attribute_history"].customer_id, t["customers"].customer_id),
    ]
    for name, child, parent in fks:
        bad = (~child.isin(parent)).sum()
        check(f"RI {name}", bad == 0, f"{bad} orphans")
    a = t["accounts"]
    check("account close >= open", ((a.close_date.isna()) | (a.close_date >= a.open_date)).all())
    tx = t["transactions"]
    check("txn amount > 0", (tx.amount > 0).all())
    check("txn after account open",
          (tx.posting_date >= tx.account_id.map(a.set_index("account_id").open_date)).all())
    check("unique primary keys", t["customers"].customer_id.is_unique and a.account_id.is_unique
          and tx.txn_id.is_unique)
    check("balances non-negative", (t["account_monthly_snapshots"].closing_balance >= 0).all())
    s = t["account_monthly_snapshots"].merge(a[["account_id", "product_id"]], on="account_id")
    s = s.merge(t["products"][["product_id", "category"]], on="product_id")
    gl = t["gl_daily_balances"]
    worst = 0.0
    for code, cat in (("DEPOSITS", "Deposit"), ("LOANS", "Loan")):
        marts = s[s.category == cat].groupby("month_end").closing_balance.sum()
        g = gl[gl.gl_code == code].set_index("gl_date").balance.reindex(marts.index)
        worst = max(worst, float(((g - marts).abs() / marts).max()))
    check("GL reconciles at month ends (<0.01%)", worst < 1e-4, f"max diff {worst:.4%}")
    return res
