"""Synthetic Bangladesh retail/SME bank data (BDT), fully reproducible from a fixed seed.

Writes CSVs to data/raw/. Run: python scripts/generate_data.py [--scale 1.0] [--reference-date 2026-09-30]

Planted stories (see docs/STORIES.md):
  a) Young Professionals churn spikes in the last quarter
  b) RMG-sector SME loans in Gazipur + Narayanganj go bad from month 10 onward
  c) FD growth erodes the CASA ratio
  d) "Eid Cashback Blast": high response / low conversion; "Student Referral Rewards": best CAC
  e) Mobile overtakes ATM in transaction count
"""

from __future__ import annotations

import argparse
import calendar
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
DEFAULT_REFERENCE_DATE = date(2026, 9, 30)
N_MONTHS = 24
N_CUSTOMERS = 50_000
TARGET_TXNS = 2_000_000
FIRST_YEAR = 2018
FAR_FUTURE = np.datetime64("2100-01-01")
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

SEGMENTS = ["Retail", "Young Professionals", "Premium", "SME", "Student"]
SEGMENT_MIX = [0.44, 0.16, 0.08, 0.14, 0.18]
CHANNELS = ["ATM", "mobile", "card", "branch", "internet"]

# (name, region, weight, sme_weight)
BRANCHES = [
    ("Motijheel", "Dhaka", 9, 6), ("Gulshan", "Dhaka", 8, 5), ("Dhanmondi", "Dhaka", 8, 4),
    ("Uttara", "Dhaka", 6, 3), ("Mirpur", "Dhaka", 6, 3), ("Banani", "Dhaka", 5, 3),
    ("Narayanganj", "Dhaka", 4, 30), ("Gazipur", "Dhaka", 4, 30),
    ("Agrabad", "Chattogram", 8, 7), ("Chawkbazar", "Chattogram", 5, 4), ("Khulshi", "Chattogram", 4, 2),
    ("Cox's Bazar", "Chattogram", 3, 2), ("Feni", "Chattogram", 2, 2),
    ("Zindabazar", "Sylhet", 5, 3), ("Ambarkhana", "Sylhet", 3, 2), ("Moulvibazar", "Sylhet", 2, 1),
    ("Rajshahi Main", "Rajshahi", 4, 3), ("Bogura", "Rajshahi", 3, 3), ("Natore", "Rajshahi", 2, 1),
    ("Khulna Main", "Khulna", 4, 3), ("Jashore", "Khulna", 3, 3), ("Satkhira", "Khulna", 2, 1),
    ("Barishal Main", "Barishal", 3, 2), ("Rangpur Main", "Rangpur", 3, 2), ("Mymensingh Main", "Mymensingh", 3, 2),
]
STRESS_BRANCHES = ("Narayanganj", "Gazipur")

# product_id, code, name, category, is_casa, annual rate (deposit cost / loan yield)
PRODUCTS = [
    (1, "SAV", "Savings", "Deposit", True, 0.040),
    (2, "CUR", "Current", "Deposit", True, 0.000),
    (3, "FD", "Fixed Deposit", "Deposit", False, 0.080),
    (4, "DPS", "DPS", "Deposit", False, 0.085),
    (5, "PL", "Personal Loan", "Loan", False, 0.135),
    (6, "SME", "SME Loan", "Loan", False, 0.115),
    (7, "HL", "Home Loan", "Loan", False, 0.095),
    (8, "CC", "Credit Card", "Loan", False, 0.200),
]
# probability a customer of a segment holds each product (SAV, CUR, FD, DPS, PL, SME, HL, CC)
PRODUCT_PROB = {
    "Retail": [0.88, 0.12, 0.30, 0.32, 0.18, 0.00, 0.08, 0.16],
    "Young Professionals": [0.92, 0.18, 0.14, 0.32, 0.27, 0.00, 0.06, 0.35],
    "Premium": [0.80, 0.36, 0.58, 0.22, 0.12, 0.00, 0.18, 0.55],
    "SME": [0.45, 0.92, 0.27, 0.12, 0.05, 0.45, 0.04, 0.16],
    "Student": [0.97, 0.00, 0.00, 0.22, 0.00, 0.00, 0.00, 0.00],
}
SEGMENT_BALANCE_MULT = {"Retail": 1.0, "Young Professionals": 1.6, "Premium": 6.0, "SME": 4.0, "Student": 0.25}
OPEN_RECENCY = {"CUR": 1.2, "DPS": 1.0, "FD": 0.9, "PL": 1.0, "SME": 1.0, "HL": 1.0, "CC": 1.2, "SAV": 1.5}

SME_SECTORS = ["RMG / Garments", "Textile", "Agriculture", "Trading", "Food Processing", "Construction", "Transport", "Pharma"]
SME_SECTOR_P = [0.24, 0.10, 0.14, 0.20, 0.08, 0.10, 0.07, 0.07]
SLIP_BASE = {
    "RMG / Garments": 0.028, "Textile": 0.034, "Agriculture": 0.050, "Trading": 0.028, "Food Processing": 0.022,
    "Construction": 0.034, "Transport": 0.034, "Pharma": 0.017, "Consumer": 0.022, "Housing": 0.014, "Consumer Cards": 0.034,
}
LOAN_PRINCIPAL_MEDIAN = {"PL": 450_000, "SME": 2_200_000, "HL": 3_800_000, "CC": 180_000}
LOAN_TERM = {"PL": 36, "SME": 36, "HL": 180, "CC": 0}
STRESS_START_MONTH = 9  # months into the 24-month window

# Campaign: name, channel, segment, start month idx, cost, targets, response rate, conversion-of-responders
CAMPAIGNS = [
    ("Student Starter Savings", "Digital", "Student", 1, 450_000, 4000, 0.09, 0.40),
    ("FD Festive Rate Offer", "Email", "Premium", 3, 800_000, 2500, 0.06, 0.22),
    ("Eid Cashback Blast", "SMS", "Young Professionals", 5, 1_900_000, 8000, 0.26, 0.035),
    ("SME Working Capital Push", "Call Center", "SME", 8, 1_400_000, 3000, 0.08, 0.15),
    ("DPS Habit Builder", "Social", "Retail", 10, 700_000, 6000, 0.07, 0.28),
    ("Premium Wealth Upgrade", "Branch", "Premium", 12, 1_100_000, 2000, 0.12, 0.18),
    ("Young Pro Salary Switch", "Digital", "Young Professionals", 14, 1_000_000, 5000, 0.10, 0.20),
    ("Winter Savings Drive", "SMS", "Retail", 15, 600_000, 7000, 0.05, 0.25),
    ("Student Referral Rewards", "Social", "Student", 17, 300_000, 3500, 0.11, 0.35),
    ("Mobile App Onboarding", "Digital", "Young Professionals", 19, 900_000, 6000, 0.09, 0.24),
    ("Premium FD Renewal Rate", "Call Center", "Premium", 21, 650_000, 2200, 0.10, 0.30),
    ("Retail Reactivation", "SMS", "Retail", 22, 800_000, 8000, 0.06, 0.12),
]
CONVERSION_PRODUCTS = {"Student": "Savings", "Premium": "Fixed Deposit", "SME": "Current", "Retail": "DPS",
                       "Young Professionals": "DPS"}

EID_DATES = [date(2025, 3, 31), date(2025, 6, 7), date(2026, 3, 20), date(2026, 5, 27)]


@dataclass(frozen=True)
class Calendar:
    month_ends: list[date]  # 25 entries: the month before the window, then the 24 window months

    @property
    def me64(self) -> np.ndarray:
        return np.array(self.month_ends, dtype="datetime64[D]")

    @property
    def start(self) -> date:
        return self.month_ends[1].replace(day=1)

    @property
    def ref(self) -> date:
        return self.month_ends[-1]


def build_calendar(ref: date) -> Calendar:
    last = date(ref.year, ref.month, calendar.monthrange(ref.year, ref.month)[1])
    if ref != last:
        first = ref.replace(day=1)
        last = first - timedelta(days=1)
    ends: list[date] = []
    y, m = last.year, last.month
    for _ in range(N_MONTHS + 1):
        ends.append(date(y, m, calendar.monthrange(y, m)[1]))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return Calendar(sorted(ends))


def mi(a: np.ndarray) -> np.ndarray:
    return a.astype("datetime64[M]").astype(np.int64)


def d64(s: pd.Series) -> np.ndarray:
    """Date column as day-resolution numpy dates (pandas 3 may hold other units)."""
    return s.to_numpy().astype("datetime64[D]")


def add_days(a: np.ndarray, d: np.ndarray | int) -> np.ndarray:
    return a + np.asarray(d).astype("timedelta64[D]")


def gen_branches(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for i, (name, region, _, _) in enumerate(BRANCHES, start=1):
        opened = date(1995, 1, 1) + timedelta(days=int(rng.integers(0, 365 * 24)))
        rows.append((i, name, region, opened))
    return pd.DataFrame(rows, columns=["branch_id", "branch_name", "region", "opened_date"])


@dataclass
class CustomerState:
    df: pd.DataFrame  # one row per customer
    history: pd.DataFrame


def gen_customers(rng: np.random.Generator, cal: Calendar, scale: float) -> CustomerState:
    n_total = int(N_CUSTOMERS * scale)
    per_month = [int((600 + 22 * m) * scale) for m in range(N_MONTHS)]
    n_pre = n_total - sum(per_month)
    pre_start = np.datetime64(f"{FIRST_YEAR}-01-01")
    win_start = np.datetime64(cal.start)
    pre_days = rng.integers(0, int((win_start - pre_start).astype(int)), n_pre)
    acq_parts = [pre_start + pre_days.astype("timedelta64[D]")]
    for m, n in enumerate(per_month):
        ms = cal.me64[m + 1].astype("datetime64[M]").astype("datetime64[D]")
        dim = calendar.monthrange(cal.month_ends[m + 1].year, cal.month_ends[m + 1].month)[1]
        acq_parts.append(ms + rng.integers(0, dim, n).astype("timedelta64[D]"))
    acq = np.sort(np.concatenate(acq_parts))
    n = len(acq)

    seg0 = rng.choice(SEGMENTS, n, p=SEGMENT_MIX)
    b_w = np.array([b[2] for b in BRANCHES], dtype=float)
    s_w = np.array([b[3] for b in BRANCHES], dtype=float)
    branch0 = np.where(
        seg0 == "SME",
        rng.choice(len(BRANCHES), n, p=s_w / s_w.sum()),
        rng.choice(len(BRANCHES), n, p=b_w / b_w.sum()),
    ) + 1
    in_window = acq >= win_start
    ch_pre = rng.choice(["Branch", "Mobile App", "Referral", "Agent Banking", "Online", "Campaign"], n,
                        p=[0.34, 0.14, 0.15, 0.12, 0.14, 0.11])
    ch_win = rng.choice(["Branch", "Mobile App", "Referral", "Agent Banking", "Online", "Campaign"], n,
                        p=[0.22, 0.30, 0.15, 0.10, 0.15, 0.08])
    channel = np.where(in_window, ch_win, ch_pre)

    hist_lo = np.maximum(acq + np.timedelta64(90, "D"), win_start)
    hist_hi = np.datetime64(cal.ref - timedelta(days=30))
    span = np.maximum((hist_hi - hist_lo).astype(int), 1)
    evt_day = hist_lo + (rng.random(n) * span).astype(int).astype("timedelta64[D]")
    evt_ok = evt_day < hist_hi
    r = rng.random(n)
    seg_new = np.full(n, "", dtype=object)
    seg_new[(seg0 == "Student") & (r < 0.25)] = "Young Professionals"
    seg_new[(seg0 == "Retail") & (r < 0.03)] = "Premium"
    seg_new[(seg0 == "Young Professionals") & (r < 0.05)] = "Premium"
    seg_evt = (seg_new != "") & evt_ok
    br_evt_day = hist_lo + (rng.random(n) * span).astype(int).astype("timedelta64[D]")
    br_evt = (rng.random(n) < 0.03) & (br_evt_day < hist_hi)
    br_new = (branch0 + rng.integers(1, len(BRANCHES), n) - 1) % len(BRANCHES) + 1

    churn_date = np.full(n, np.datetime64("NaT", "D"), dtype="datetime64[D]")
    quarter_start = N_MONTHS - 3
    for m in range(N_MONTHS):
        me = cal.me64[m + 1]
        ms = me.astype("datetime64[M]").astype("datetime64[D]")
        seg_now = np.where(seg_evt & (evt_day <= me), seg_new, seg0)
        p = np.select(
            [seg_now == "Young Professionals", seg_now == "Student", seg_now == "Premium", seg_now == "SME"],
            [0.0085, 0.0100, 0.0040, 0.0070], 0.0075,
        )
        yp_spike = {quarter_start: 0.020, quarter_start + 1: 0.026, quarter_start + 2: 0.031}
        if m in yp_spike:
            p = np.where(seg_now == "Young Professionals", yp_spike[m], p)
        eligible = (acq < ms) & np.isnat(churn_date)
        hit = eligible & (rng.random(n) < p)
        dim = (me - ms).astype(int) + 1
        day = ms + (rng.random(n) * dim).astype(int).astype("timedelta64[D]")
        churn_date[hit] = np.maximum(day[hit], acq[hit] + np.timedelta64(1, "D"))
    seg_evt &= np.isnat(churn_date) | (evt_day < churn_date)
    br_evt &= np.isnat(churn_date) | (br_evt_day < churn_date)

    cid = np.arange(1, n + 1)
    init = pd.DataFrame({"customer_id": cid, "date": acq, "segment": seg0, "home_branch_id": branch0})
    ev_s = pd.DataFrame({"customer_id": cid[seg_evt], "date": evt_day[seg_evt], "segment": seg_new[seg_evt],
                         "home_branch_id": np.nan})
    ev_b = pd.DataFrame({"customer_id": cid[br_evt], "date": br_evt_day[br_evt], "segment": None,
                         "home_branch_id": br_new[br_evt].astype(float)})
    hist = pd.concat([init, ev_s, ev_b]).sort_values(["customer_id", "date"], kind="stable")
    hist["segment"] = hist.groupby("customer_id")["segment"].ffill()
    hist["home_branch_id"] = hist.groupby("customer_id")["home_branch_id"].ffill().astype(int)
    hist = hist.rename(columns={"date": "valid_from"})
    hist["valid_to"] = hist.groupby("customer_id")["valid_from"].shift(-1)
    last = hist.groupby("customer_id").tail(1).set_index("customer_id")

    customers = pd.DataFrame({
        "customer_id": cid,
        "segment": last.loc[cid, "segment"].to_numpy(),
        "acquisition_channel": channel,
        "acquisition_date": acq,
        "home_branch_id": last.loc[cid, "home_branch_id"].to_numpy(),
        "status": np.where(np.isnat(churn_date), "Active", "Churned"),
        "churn_date": churn_date,
        "initial_branch_id": branch0,
    })
    return CustomerState(customers, hist[["customer_id", "segment", "home_branch_id", "valid_from", "valid_to"]])


def asof_attrs(history: pd.DataFrame, cust_ids: np.ndarray, dates: np.ndarray) -> pd.DataFrame:
    left = pd.DataFrame({"customer_id": cust_ids, "d": dates, "_i": np.arange(len(cust_ids))}).sort_values("d")
    right = history.sort_values("valid_from")[["customer_id", "valid_from", "segment", "home_branch_id"]]
    m = pd.merge_asof(left, right, left_on="d", right_on="valid_from", by="customer_id", direction="backward")
    return m.sort_values("_i")[["segment", "home_branch_id"]].reset_index(drop=True)


def gen_campaigns(rng: np.random.Generator, cal: Calendar, cust: pd.DataFrame, hist: pd.DataFrame, scale: float):
    camps, resp, new_accounts = [], [], []
    for cid, (name, channel, seg, start_idx, cost, n_t, rr, cr) in enumerate(CAMPAIGNS, start=1):
        start = cal.month_ends[start_idx + 1].replace(day=10)
        end = start + timedelta(days=29)
        camps.append((cid, name, channel, int(cost * scale ** 0.5), seg, start, end))
        alive = cust[(cust.acquisition_date < np.datetime64(start)) &
                     (cust.churn_date.isna() | (cust.churn_date > np.datetime64(end)))]
        seg_at = asof_attrs(hist, alive.customer_id.to_numpy(), np.full(len(alive), np.datetime64(start)))
        pool = alive.customer_id.to_numpy()[(seg_at.segment == seg).to_numpy()]
        targets = rng.choice(pool, min(len(pool), max(int(n_t * scale), 20)), replace=False)
        responded = rng.random(len(targets)) < rr
        converted = responded & (rng.random(len(targets)) < cr)
        offs = rng.integers(0, 30, len(targets))
        product = CONVERSION_PRODUCTS[seg]
        for c, ok, conv, off in zip(targets, responded, converted, offs, strict=True):
            resp.append((cid, int(c), bool(ok), product if conv else None, start + timedelta(days=int(off))))
            if conv:
                new_accounts.append((int(c), product, start + timedelta(days=int(off))))
    campaigns = pd.DataFrame(camps, columns=["campaign_id", "campaign_name", "channel", "cost", "target_segment",
                                             "start_date", "end_date"])
    responses = pd.DataFrame(resp, columns=["campaign_id", "customer_id", "responded", "converted_product",
                                            "response_date"])
    responses.insert(0, "response_id", np.arange(1, len(responses) + 1))
    return campaigns, responses, pd.DataFrame(new_accounts, columns=["customer_id", "product", "open_date"])


def gen_accounts(rng: np.random.Generator, cal: Calendar, cust: pd.DataFrame, extra: pd.DataFrame,
                 products: pd.DataFrame) -> pd.DataFrame:
    n = len(cust)
    acq = d64(cust.acquisition_date)
    churn = d64(cust.churn_date)
    horizon = np.where(np.isnat(churn), np.datetime64(cal.ref), churn - np.timedelta64(1, "D"))
    horizon = np.maximum(horizon, acq)
    seg = cust.segment.to_numpy()
    prob = np.array([PRODUCT_PROB[s] for s in seg])
    has = rng.random(prob.shape) < prob
    has[:, 4:] &= np.isnat(churn)[:, None]  # churned customers hold no credit
    no_op = ~(has[:, 0] | has[:, 1])  # every customer needs an operating account
    has[no_op & (seg != "SME"), 0] = True
    has[no_op & (seg == "SME"), 1] = True

    pid_by_code = dict(zip(products.product_code, products.product_id, strict=True))
    parts = []
    codes = [p[1] for p in PRODUCTS]
    primary_done = np.zeros(n, dtype=bool)
    for j, code in enumerate(codes):
        idx = np.where(has[:, j])[0]
        span = (horizon[idx] - acq[idx]).astype(int)
        u = rng.random(len(idx))
        delay = np.floor(span * u ** OPEN_RECENCY[code]).astype(int)
        is_primary = (code in ("SAV", "CUR")) & ~primary_done[idx]
        delay = np.where(is_primary, rng.integers(0, 4, len(idx)), delay)
        if code in ("SAV", "CUR"):
            primary_done[idx[is_primary]] = True
        open_d = np.minimum(add_days(acq[idx], delay), horizon[idx])
        parts.append(pd.DataFrame({"customer_id": cust.customer_id.to_numpy()[idx], "product_code": code,
                                   "open_date": open_d}))
    cmap = {"Savings": "SAV", "Current": "CUR", "Fixed Deposit": "FD", "DPS": "DPS"}
    if len(extra):
        parts.append(pd.DataFrame({"customer_id": extra.customer_id, "product_code": extra["product"].map(cmap),
                                   "open_date": d64(pd.to_datetime(extra.open_date))}))
    acc = pd.concat(parts, ignore_index=True)
    acc = acc.merge(cust[["customer_id", "initial_branch_id", "churn_date"]], on="customer_id")
    acc = acc.sort_values(["open_date", "customer_id", "product_code"], kind="stable").reset_index(drop=True)
    acc["account_id"] = np.arange(1, len(acc) + 1)
    acc["product_id"] = acc.product_code.map(pid_by_code)
    acc["branch_id"] = acc.initial_branch_id
    close = d64(acc.churn_date).copy()
    dps = (acc.product_code == "DPS").to_numpy()
    mature = add_days(d64(acc.open_date), 1826)
    refd = np.datetime64(cal.ref)
    close = np.where(dps & (mature <= refd) & (np.isnat(close) | (mature < close)), mature, close)
    acc["close_date"] = close
    return acc.drop(columns=["initial_branch_id", "churn_date"])


def deposit_balances(rng: np.random.Generator, cal: Calendar, acc: pd.DataFrame, cust_seg: pd.Series) -> pd.DataFrame:
    dep = acc[acc.product_code.isin(["SAV", "CUR", "FD", "DPS"])].copy()
    me = cal.me64
    close = np.where(dep.close_date.isna(), FAR_FUTURE, d64(dep.close_date))
    opend = d64(dep.open_date)
    exists = (opend[:, None] <= me[None, :]) & (close[:, None] > me[None, :])
    age = np.maximum(mi(me)[None, :] - mi(opend)[:, None], 0)
    mult = dep.customer_id.map(cust_seg).map(SEGMENT_BALANCE_MULT).to_numpy()
    persist = rng.lognormal(0, 0.9, len(dep))
    noise = rng.lognormal(0, 0.06, age.shape)
    bal = np.zeros(age.shape)
    for code, median, growth in (("SAV", 55_000, 1.003), ("CUR", 130_000, 1.002)):
        r = (dep.product_code == code).to_numpy()
        base = median * mult[r] * persist[r]
        bal[r] = base[:, None] * growth ** age[r] * noise[r]
    r = (dep.product_code == "FD").to_numpy()
    fd_rate = PRODUCTS[2][5]
    bal[r] = (320_000 * mult[r] * persist[r] ** 0.8)[:, None] * (1 + fd_rate / 12) ** age[r]
    r = (dep.product_code == "DPS").to_numpy()
    inst = 4_000 * np.sqrt(mult[r]) * persist[r] ** 0.5
    bal[r] = inst[:, None] * (age[r] + 1) * (1 + PRODUCTS[3][5] / 24)
    bal = np.where(exists, bal, np.nan)
    first = exists & ~np.concatenate([np.zeros((len(dep), 1), bool), exists[:, :-1]], axis=1)
    bal = np.where(first, bal * rng.uniform(0.35, 1.0, bal.shape), bal)

    rate = dep.product_code.map({p[1]: p[5] for p in PRODUCTS}).to_numpy()
    prev = np.concatenate([np.full((len(dep), 1), np.nan), bal[:, :-1]], axis=1)
    adb = np.where(np.isnan(prev), bal * 0.6, (prev + bal) / 2) * rng.lognormal(0, 0.02, bal.shape)
    return _long_format(dep.account_id.to_numpy(), me, bal, adb, rate)


def _long_format(account_ids: np.ndarray, me: np.ndarray, bal: np.ndarray, adb: np.ndarray, rate: np.ndarray,
                 earning: np.ndarray | None = None) -> pd.DataFrame:
    keep = ~np.isnan(bal)
    keep[:, 0] = False  # column 0 is the month before the window
    ai, mj = np.where(keep)
    interest = adb[ai, mj] * rate[ai] / 12
    if earning is not None:
        interest = interest * earning[ai, mj]
    return pd.DataFrame({
        "account_id": account_ids[ai],
        "month_end": me[mj],
        "closing_balance": np.round(bal[ai, mj], 2),
        "avg_daily_balance": np.round(adb[ai, mj], 2),
        "interest_accrued": np.round(interest, 2),
    })


def classify(dpd: np.ndarray) -> np.ndarray:
    return np.select([dpd < 30, dpd < 90, dpd < 180, dpd < 270], ["Standard", "SMA", "Substandard", "Doubtful"],
                     "Bad-Loss")


def gen_loans(rng: np.random.Generator, cal: Calendar, acc: pd.DataFrame, cust: pd.DataFrame,
              branches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (loans, loan_monthly_snapshots, account_close_dates, loan account monthly snapshots)."""
    la = acc[acc.product_code.isin(["PL", "SME", "HL", "CC"])].reset_index(drop=True)
    n = len(la)
    code = la.product_code.to_numpy()
    c_idx = la.customer_id.to_numpy() - 1
    init_branch = cust.initial_branch_id.to_numpy()[c_idx]
    bname = branches.set_index("branch_id").branch_name
    stress_branch = np.isin(init_branch, branches[branches.branch_name.isin(STRESS_BRANCHES)].branch_id.to_numpy())

    sector = np.select([code == "PL", code == "HL", code == "CC"], ["Consumer", "Housing", "Consumer Cards"], "")
    sme = code == "SME"
    s_draw = rng.choice(SME_SECTORS, n, p=SME_SECTOR_P)
    s_draw = np.where(stress_branch & (rng.random(n) < 0.85), "RMG / Garments", s_draw)
    sector = np.where(sme, s_draw, sector)
    stressed = stress_branch & (sector == "RMG / Garments")

    principal = np.array([LOAN_PRINCIPAL_MEDIAN[c] for c in code]) * rng.lognormal(0, 0.6, n)
    principal = np.round(principal, -2)
    term = np.array([LOAN_TERM[c] for c in code])
    rate = np.array([next(p[5] for p in PRODUCTS if p[1] == c) for c in code]) + rng.uniform(-0.01, 0.01, n)
    slip = np.array([SLIP_BASE[s] for s in sector])

    me_mi = mi(cal.me64)
    open_mi = mi(d64(la.open_date))
    t0, t_end = int(open_mi.min()), int(me_mi[-1])
    hist_mi0 = int(me_mi[1])
    outstanding = np.zeros(n)
    dpd = np.zeros(n, dtype=int)
    alive = np.zeros(n, dtype=bool)
    closed_mi = np.full(n, -1)
    writeoff = np.zeros(n, dtype=bool)
    rec_out = np.full((n, N_MONTHS + 1), np.nan)
    rec_dpd = np.zeros((n, N_MONTHS + 1), dtype=int)
    util = rng.uniform(0.2, 0.7, n)
    for t in range(t0, t_end + 1):
        existing = alive & (open_mi < t)
        h = slip.copy()
        ramp = np.clip(0.007 * (t - (hist_mi0 + STRESS_START_MONTH) + 1), 0, 0.09)
        h = np.where(stressed & (t >= hist_mi0 + STRESS_START_MONTH), h + ramp, h)
        cure = np.where(dpd < 60, 0.45, np.where(dpd < 120, 0.15, 0.04))
        cure = np.where(stressed & (t >= hist_mi0 + STRESS_START_MONTH), cure * 0.4, cure)
        cur = existing & (dpd == 0)
        slipped = cur & (rng.random(n) < h)
        late = existing & (dpd > 0)
        cured = late & (rng.random(n) < cure)
        dpd = np.where(slipped, rng.integers(10, 31, n), dpd)
        dpd = np.where(late & ~cured, dpd + 30, dpd)
        dpd = np.where(cured, 0, dpd)
        paying = existing & (dpd == 0)
        amort = np.where(term > 0, principal / np.maximum(term, 1), 0.0)
        card_walk = outstanding * np.exp(rng.normal(0.01, 0.10, n))
        outstanding = np.where(paying & (term > 0), outstanding - amort, outstanding)
        outstanding = np.where(paying & (term == 0), np.minimum(card_walk, principal), outstanding)
        wo = existing & (dpd >= 360)
        paid = existing & (outstanding <= 1.0)
        writeoff |= wo
        ended = wo | paid
        closed_mi[ended] = t
        alive &= ~ended
        outstanding = np.where(ended, 0.0, outstanding)
        new = open_mi == t
        outstanding = np.where(new & (term > 0), principal, np.where(new, principal * util, outstanding))
        alive |= new
        dpd = np.where(new, 0, dpd)
        if t >= hist_mi0 - 1:
            k = t - (hist_mi0 - 1)
            rec_out[:, k] = np.where(alive, outstanding, np.nan)
            rec_dpd[:, k] = dpd

    close_date = np.full(n, np.datetime64("NaT", "D"), dtype="datetime64[D]")
    ended_mask = closed_mi >= 0
    first_of_month = (closed_mi[ended_mask].astype("datetime64[M]")).astype("datetime64[D]")
    close_date[ended_mask] = first_of_month + rng.integers(0, 27, ended_mask.sum()).astype("timedelta64[D]")

    last_out = rec_out[:, -1]
    last_dpd = rec_dpd[:, -1]
    final_cls = np.where(writeoff, "Bad-Loss", np.where(ended_mask, "Standard", classify(last_dpd)))
    loans = pd.DataFrame({
        "loan_id": np.arange(1, n + 1),
        "account_id": la.account_id.to_numpy(),
        "customer_id": la.customer_id.to_numpy(),
        "product_id": la.product_id.to_numpy(),
        "branch_id": init_branch,
        "principal": principal,
        "interest_rate": np.round(rate, 4),
        "term_months": term,
        "disbursed_date": d64(la.open_date),
        "outstanding": np.round(np.nan_to_num(last_out), 2),
        "sector": sector,
        "classification": final_cls,
        "days_past_due": np.where(ended_mask, 0, last_dpd),
    })
    del bname

    keep = ~np.isnan(rec_out)
    keep[:, 0] = False
    li, mj = np.where(keep)
    lsnap = pd.DataFrame({
        "loan_id": li + 1,
        "account_id": la.account_id.to_numpy()[li],
        "month_end": cal.me64[mj],
        "outstanding": np.round(rec_out[li, mj], 2),
        "days_past_due": rec_dpd[li, mj],
    })
    lsnap["classification"] = classify(lsnap.days_past_due.to_numpy())

    prev = np.concatenate([np.full((n, 1), np.nan), rec_out[:, :-1]], axis=1)
    adb = np.where(np.isnan(prev), rec_out * 0.5, (prev + rec_out) / 2)
    recognised = (rec_dpd < 90).astype(float)
    acc_snap = _long_format(la.account_id.to_numpy(), cal.me64, rec_out, adb, rate, earning=recognised)
    close_df = pd.DataFrame({"account_id": la.account_id.to_numpy(), "close_date": close_date})
    return loans, lsnap, close_df, acc_snap


def day_weights(ms: date, n_days: int) -> np.ndarray:
    w = np.ones(n_days)
    for i in range(n_days):
        d = ms + timedelta(days=i)
        w[i] *= {4: 0.55, 5: 0.75}.get(d.weekday(), 1.0)  # Fri / Sat weekend
        if i >= n_days - 3:
            w[i] *= 1.5
        if i < 5:
            w[i] *= 1.3
        for eid in EID_DATES:
            gap = (eid - d).days
            if 1 <= gap <= 12:
                w[i] *= 1.6
            elif -1 <= gap <= 0:
                w[i] *= 0.25
    return w / w.sum()


def gen_transactions(rng: np.random.Generator, cal: Calendar, cust: pd.DataFrame, acc: pd.DataFrame,
                     scale: float) -> pd.DataFrame:
    n = len(cust)
    acq = d64(cust.acquisition_date)
    churn = np.where(cust.churn_date.isna(), FAR_FUTURE, d64(cust.churn_date))
    seg = cust.segment.to_numpy()
    seg_i = np.array([SEGMENTS.index(s) for s in seg])
    lam_seg = np.array([2.0, 3.6, 3.1, 4.6, 2.0])[seg_i]
    act = rng.lognormal(0, 0.7, n) * np.where(rng.random(n) < 0.12, 0.1, 1.0)

    first_op = acc[acc.product_code.isin(["SAV", "CUR"])].sort_values("open_date").groupby("customer_id").first()
    first_card = acc[acc.product_code == "CC"].sort_values("open_date").groupby("customer_id").first()
    op_acct = cust.customer_id.map(first_op.account_id).to_numpy().astype(np.int64)
    op_open = d64(cust.customer_id.map(first_op.open_date))
    card_acct = cust.customer_id.map(first_card.account_id).fillna(0).to_numpy().astype(np.int64)
    card_open = np.where(card_acct > 0, d64(cust.customer_id.map(first_card.open_date)), FAR_FUTURE)

    seg_factor = np.array([  # rows = SEGMENTS, cols = CHANNELS
        [1.0, 1.0, 1.0, 1.0, 1.0],
        [0.8, 1.3, 1.1, 0.7, 1.2],
        [0.7, 1.0, 1.5, 1.1, 1.2],
        [0.8, 0.9, 0.8, 1.6, 1.3],
        [1.0, 1.4, 0.6, 0.5, 0.8],
    ])
    mu = np.array([8.5, 8.0, 7.8, 11.0, 9.8])
    sigma = np.array([0.7, 1.0, 1.0, 1.2, 1.2])
    seg_mu = np.array([0.0, 0.2, 0.7, 1.2, -0.7])
    p_credit = np.array([0.02, 0.40, 0.03, 0.50, 0.45])

    months = []
    total_lambda = 0.0
    for m in range(1, N_MONTHS + 1):
        ms_d = cal.month_ends[m].replace(day=1)
        ms, me = np.datetime64(ms_d), cal.me64[m]
        active = (acq <= me) & (churn >= ms)
        decay = np.where((churn - ms).astype(int) < 75, 0.3, 1.0)
        lam = np.where(active, lam_seg * act * decay, 0.0)
        months.append((m, ms_d, ms, me, lam))
        total_lambda += lam.sum()
    k = TARGET_TXNS * scale / total_lambda

    frames = []
    for m, ms_d, ms, me, lam in months:
        counts = rng.poisson(lam * k)
        idx = np.repeat(np.arange(n), counts)
        t = len(idx)
        n_days = (me - ms).astype(int) + 1
        cdf = np.cumsum(day_weights(ms_d, n_days))
        day = np.searchsorted(cdf, rng.random(t)).clip(0, n_days - 1)
        day = np.maximum(day, ((op_open[idx] - ms).astype(int) + 1).clip(0, n_days - 1))
        day = np.minimum(day, np.where(churn[idx] < me, (churn[idx] - ms).astype(int), n_days - 1))
        posting = ms + day.astype("timedelta64[D]")
        f = (m - 1) / (N_MONTHS - 1)
        base = np.array([0.40 - 0.16 * f, 0.20 + 0.22 * f, 0.20, 0.13 - 0.06 * f, 0.07 + 0.03 * f])
        probs = base[None, :] * seg_factor[seg_i[idx]]
        cum = np.cumsum(probs / probs.sum(axis=1, keepdims=True), axis=1)
        ch = (rng.random(t)[:, None] > cum).sum(axis=1).clip(0, len(CHANNELS) - 1)
        amount = np.round(np.exp(rng.normal(mu[ch] + seg_mu[seg_i[idx]], sigma[ch])), 2)
        credit = rng.random(t) < p_credit[ch]
        use_card = (ch == 2) & (card_open[idx] <= posting) & (rng.random(t) < 0.6)
        account = np.where(use_card, card_acct[idx], op_acct[idx])
        opened = np.where(use_card, card_open[idx], op_open[idx])
        shift = rng.choice([0, 1, -1], t, p=[0.85, 0.10, 0.05])
        value = np.minimum(posting + shift.astype("timedelta64[D]"), cal.me64[-1])
        frames.append(pd.DataFrame({
            "account_id": account.astype(np.int32), "customer_id": (idx + 1).astype(np.int32),
            "channel": pd.Categorical.from_codes(ch, CHANNELS),
            "amount": amount, "direction": pd.Categorical.from_codes(credit.astype(int), ["Debit", "Credit"]),
            "posting_date": posting, "value_date": value,
        })[posting >= opened])
    tx = pd.concat(frames, ignore_index=True).sort_values(["posting_date", "customer_id"], kind="stable")
    del frames
    tx.insert(0, "txn_id", np.arange(1, len(tx) + 1))
    return tx.reset_index(drop=True)


def gen_gl(rng: np.random.Generator, cal: Calendar, snaps: pd.DataFrame, acc: pd.DataFrame) -> pd.DataFrame:
    cat = acc.set_index("account_id").product_code.map(lambda c: "LOANS" if c in ("PL", "SME", "HL", "CC") else "DEPOSITS")
    s = snaps.assign(code=snaps.account_id.map(cat))
    totals = s.groupby(["month_end", "code"]).closing_balance.sum().unstack()
    rows = []
    for code, name in (("DEPOSITS", "Customer deposits"), ("LOANS", "Loans and advances")):
        pts = {d: float(totals.loc[np.datetime64(d), code]) * (1 + rng.uniform(-0.00002, 0.00002))
               for d in cal.month_ends[1:]}
        prev_d = cal.month_ends[1].replace(day=1)
        prev_v = pts[cal.month_ends[1]] * 0.985
        for d in cal.month_ends[1:]:
            n_days = (d - prev_d).days + 1
            for i in range(n_days):
                v = prev_v + (pts[d] - prev_v) * (i + 1) / n_days
                rows.append((prev_d + timedelta(days=i), code, name, round(v, 2)))
            prev_d, prev_v = d + timedelta(days=1), pts[d]
    return pd.DataFrame(rows, columns=["gl_date", "gl_code", "gl_name", "balance"])


def write(df: pd.DataFrame, name: str) -> None:
    df.to_csv(OUT_DIR / f"{name}.csv", index=False, date_format="%Y-%m-%d")
    print(f"  {name:32s} {len(df):>10,d} rows")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0, help="row-count scale (1.0 = spec sizes)")
    ap.add_argument("--reference-date", default=DEFAULT_REFERENCE_DATE.isoformat(),
                    help="YYYY-MM-DD or 'last-full-month'")
    args = ap.parse_args()
    if args.reference_date == "last-full-month":
        ref = date.today().replace(day=1) - timedelta(days=1)
    else:
        ref = date.fromisoformat(args.reference_date)
    cal = build_calendar(ref)
    rng = np.random.default_rng(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating data, window {cal.start} .. {cal.ref}, seed {SEED}, scale {args.scale}")

    branches = gen_branches(rng)
    products = pd.DataFrame(PRODUCTS, columns=["product_id", "product_code", "product_name", "category", "is_casa",
                                               "interest_rate"])
    state = gen_customers(rng, cal, args.scale)
    cust, hist = state.df, state.history
    campaigns, responses, conv_accounts = gen_campaigns(rng, cal, cust, hist, args.scale)
    acc = gen_accounts(rng, cal, cust, conv_accounts, products)
    loans, loan_snaps, loan_close, loan_acc_snaps = gen_loans(rng, cal, acc, cust, branches)
    acc = acc.merge(loan_close, on="account_id", how="left", suffixes=("", "_loan"))
    acc["close_date"] = acc.close_date.fillna(acc.close_date_loan)
    acc = acc.drop(columns="close_date_loan")
    dep_snaps = deposit_balances(rng, cal, acc, cust.set_index("customer_id").segment)
    snaps = pd.concat([dep_snaps, loan_acc_snaps]).sort_values(["account_id", "month_end"]).reset_index(drop=True)
    txns = gen_transactions(rng, cal, cust, acc, args.scale)
    gl = gen_gl(rng, cal, snaps, acc)

    acc_out = acc.assign(
        status=np.where(acc.close_date.isna(), "Open", "Closed"),
    )[["account_id", "customer_id", "product_id", "branch_id", "open_date", "close_date", "status"]]
    print("Writing CSVs")
    write(branches, "branches")
    write(products, "products")
    write(cust.drop(columns="initial_branch_id"), "customers")
    write(hist, "customer_attribute_history")
    write(acc_out, "accounts")
    write(snaps, "account_monthly_snapshots")
    write(txns, "transactions")
    write(loans, "loans")
    write(loan_snaps, "loan_monthly_snapshots")
    write(campaigns, "campaigns")
    write(responses, "campaign_responses")
    write(gl, "gl_daily_balances")
    (OUT_DIR / "_meta.json").write_text(json.dumps({
        "seed": SEED, "scale": args.scale, "window_start": cal.start.isoformat(),
        "reference_date": cal.ref.isoformat(),
    }))


if __name__ == "__main__":
    main()
