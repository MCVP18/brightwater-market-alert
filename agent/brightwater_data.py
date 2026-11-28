"""
Brightwater alert data: every number the agent quotes comes from here.

The agent never guesses figures. Each tool in tools.py calls one of these
functions, and these functions only read the alert spreadsheet.

Rules match the take-home write-up:
  - 25 duplicate rows removed (11,563 alerts)
  - stores S119 and S120 belong to D8 (confirmed by Keneavy)
  - tiers by alert type: High = manual card entry, no-receipt refund;
    Medium = post-void, employee discount; Low = price override; any other type = Medium
  - queue order: tier, then highest dollar amount, then oldest
  - a review of 30 seconds or less counts as "rushed"
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd

DEFAULT_DATA = Path(__file__).resolve().parent.parent / "Brightwater_Exceptions_Aug-Oct_2026.xlsx"
TIER = {"Manual card entry": "High", "No-receipt refund": "High",
        "Post-void": "Medium", "Employee discount": "Medium", "Price override": "Low"}
TIER_RANK = {"High": 0, "Medium": 1, "Low": 2}
RUSHED_SECONDS = 30
PERIOD_START = pd.Timestamp("2026-08-31")

# Draft "what to check" notes for each alert type. These are a starting point only:
# the next release plans to agree real review criteria with Brightwater loss prevention.
WHAT_TO_CHECK = {
    "No-receipt refund": "Was the item actually returned to stock? Does the customer or amount repeat? "
                         "Is the same cashier issuing several no-receipt refunds?",
    "Manual card entry": "Why was the card keyed in instead of swiped or tapped? Is the amount unusually high? "
                         "Has this cashier keyed in other cards recently?",
    "Post-void": "Was the void done right after the sale, with a manager present? Was the customer still there? "
                 "Do this cashier's voids cluster at the end of a shift?",
    "Employee discount": "Was the purchase for the employee? Is the discount used often or on high-value items?",
    "Price override": "Was there a matching price-match, damage or promotion reason? Is the override unusually large?",
}


@lru_cache(maxsize=1)
def load(path: str | None = None) -> pd.DataFrame:
    """Load and clean the alert sheet once, then reuse it."""
    path = path or os.environ.get("BRIGHTWATER_DATA") or str(DEFAULT_DATA)
    if not Path(path).exists():
        raise FileNotFoundError(
            f"Alert spreadsheet not found at {path}. Put Brightwater_Exceptions_Aug-Oct_2026.xlsx "
            "in the repository root, or set BRIGHTWATER_DATA to its location.")
    a = pd.read_excel(path, sheet_name="Alerts").drop_duplicates().copy()
    a.loc[a.store_id.isin(["S119", "S120"]), "district"] = "D8"
    a["tier"] = a.alert_type.map(TIER).fillna("Medium")
    a["reviewed"] = a.status == "Reviewed"
    a["confirmed"] = a.outcome == "Confirmed issue"
    a["rushed"] = a.reviewed & (a.review_seconds <= RUSHED_SECONDS)
    a["real_review"] = a.reviewed & (a.review_seconds > RUSHED_SECONDS)
    a["week"] = (a.created_at - PERIOD_START).dt.days // 7 + 1
    return a


def _reviewed_confirmed_rate(df: pd.DataFrame) -> float | None:
    r = df[df.reviewed]
    return round(float(r.confirmed.mean()), 3) if len(r) else None


def type_confirmed_rates() -> dict[str, float]:
    """How often each alert type turned out to be a real problem when reviewed."""
    a = load()
    return a[a.reviewed].groupby("alert_type").confirmed.mean().round(3).to_dict()


def _fmt_alert(row, as_of: pd.Timestamp) -> dict:
    return {
        "alert_id": row.alert_id, "tier": row.tier, "type": row.alert_type,
        "amount": round(float(row.transaction_amount), 2), "cashier": row.employee_id,
        "flagged": row.created_at.strftime("%a %b %d, %I:%M %p"),
        "days_waiting": int((as_of.normalize() - row.created_at.normalize()).days),
        "reason": f"{row.tier}: {row.alert_type}",
    }


def store_queue(store_id: str, week: int = 8) -> dict:
    """A store's alerts for one week, in the new queue order (as if opened the following Monday)."""
    a = load()
    s = a[(a.store_id == store_id) & (a.week == week)].copy()
    if s.empty:
        return {"store": store_id, "week": week, "alerts": [], "note": "No alerts for this store in that week."}
    s["rank"] = s.tier.map(TIER_RANK)
    s = s.sort_values(["rank", "transaction_amount", "created_at"], ascending=[True, False, True])
    as_of = PERIOD_START + pd.Timedelta(days=7 * week)
    alerts = [_fmt_alert(r, as_of) for r in s.itertuples()]
    counts = s.tier.value_counts().reindex(["High", "Medium", "Low"], fill_value=0).to_dict()
    return {"store": store_id, "district": s.district.iloc[0], "week": week,
            "week_of": (as_of - pd.Timedelta(days=7)).strftime("%b %d, %Y"),
            "counts_by_tier": counts, "alerts": alerts}


def explain_alert(alert_id: str) -> dict:
    """Everything a manager needs to review one alert, plus draft guidance on what to check."""
    a = load()
    m = a[a.alert_id == alert_id]
    if m.empty:
        return {"error": f"No alert with ID {alert_id}."}
    row = m.iloc[0]
    rates = type_confirmed_rates()
    cashier = a[(a.employee_id == row.employee_id) & (a.alert_id != alert_id)]
    return {
        "alert_id": alert_id, "store": row.store_id, "district": row.district,
        "type": row.alert_type, "tier": row.tier, "amount": round(float(row.transaction_amount), 2),
        "cashier": row.employee_id, "flagged": row.created_at.strftime("%a %b %d, %Y %I:%M %p"),
        "status": row.status, "outcome": None if pd.isna(row.outcome) else row.outcome,
        "how_often_this_type_is_real": rates.get(row.alert_type),
        "cashier_other_alerts_8_weeks": int(len(cashier)),
        "cashier_other_confirmed_issues": int(cashier.confirmed.sum()),
        "draft_what_to_check": WHAT_TO_CHECK.get(row.alert_type, "New alert type: no guidance yet."),
        "note": "Line items are in the platform but not in this dataset; no receipt image exists.",
    }


def store_summary(store_id: str) -> dict:
    """How well one store keeps up, over all 8 weeks."""
    a = load()
    s = a[a.store_id == store_id]
    if s.empty:
        return {"error": f"No alerts for store {store_id}."}
    by_tier = {}
    for t in ("High", "Medium", "Low"):
        x = s[s.tier == t]
        by_tier[t] = {"alerts": int(len(x)), "review_rate": round(float(x.reviewed.mean()), 3) if len(x) else None,
                      "real_review_rate": round(float(x.real_review.mean()), 3) if len(x) else None}
    r = s[s.reviewed]
    return {
        "store": store_id, "district": s.district.iloc[0], "alerts": int(len(s)),
        "alerts_per_week": round(len(s) / 8, 1),
        "review_rate": round(float(s.reviewed.mean()), 3),
        "real_review_rate": round(float(s.real_review.mean()), 3),
        "rushed_share_of_reviews": round(float(r.rushed.mean()), 3) if len(r) else None,
        "confirmed_issues": int(s.confirmed.sum()),
        "confirmed_rate_when_reviewed": _reviewed_confirmed_rate(s),
        "by_tier": by_tier,
        "chain_review_rate": round(float(a.reviewed.mean()), 3),
    }


def district_summary(district: str, last_weeks: int = 8) -> dict:
    """Review rates for every store in a district, with the stores most worth a follow-up."""
    a = load()
    d = a[(a.district == district) & (a.week > 8 - last_weeks)]
    if d.empty:
        return {"error": f"No alerts for district {district}."}
    g = d.groupby("store_id")
    stores = pd.DataFrame({
        "alerts": g.size(), "review_rate": g.reviewed.mean(), "real_review_rate": g.real_review.mean(),
        "high_tier_review_rate": d[d.tier == "High"].groupby("store_id").reviewed.mean(),
        "confirmed_issues": g.confirmed.sum(),
    }).round(3).fillna(0)
    stores["rushed_share"] = d[d.reviewed].groupby("store_id").rushed.mean().round(3)
    others = a[(a.district != district) & (a.week > 8 - last_weeks)]
    follow_up = stores.sort_values("review_rate").head(3).index.tolist()
    rushers = stores[stores.rushed_share > 0.5].index.tolist()
    return {
        "district": district, "weeks_covered": last_weeks, "stores": len(stores),
        "district_review_rate": round(float(d.reviewed.mean()), 3),
        "other_districts_review_rate": round(float(others.reviewed.mean()), 3),
        "district_high_tier_review_rate": round(float(d[d.tier == "High"].reviewed.mean()), 3),
        "confirmed_issues": int(d.confirmed.sum()),
        "lowest_review_rate_stores": follow_up,
        "stores_rushing_over_half_their_reviews": rushers,
        "per_store": stores.reset_index().to_dict(orient="records"),
    }


METRICS = {
    "alerts": lambda x: int(len(x)),
    "review_rate": lambda x: round(float(x.reviewed.mean()), 3) if len(x) else None,
    "real_review_rate": lambda x: round(float(x.real_review.mean()), 3) if len(x) else None,
    "confirmed_rate_when_reviewed": _reviewed_confirmed_rate,
    "confirmed_issues": lambda x: int(x.confirmed.sum()),
    "confirmed_dollars": lambda x: round(float(x.loc[x.confirmed, "transaction_amount"].sum()), 2),
    "rushed_share_of_reviews": lambda x: round(float(x[x.reviewed].rushed.mean()), 3) if x.reviewed.any() else None,
    "median_amount": lambda x: round(float(x.transaction_amount.median()), 2) if len(x) else None,
}
GROUPS = {"district", "store_id", "alert_type", "tier", "week", "reviewer_role", "status"}


def query_alerts(metric: str, group_by: str | None = None, district: str | None = None,
                 store_id: str | None = None, alert_type: str | None = None, tier: str | None = None,
                 week_from: int | None = None, week_to: int | None = None,
                 min_amount: float | None = None, max_amount: float | None = None) -> dict:
    """Answer a data question with one metric, optionally filtered and grouped. No free-form code."""
    if metric not in METRICS:
        return {"error": f"Unknown metric. Choose one of: {', '.join(METRICS)}."}
    if group_by and group_by not in GROUPS:
        return {"error": f"Can't group by {group_by}. Choose one of: {', '.join(sorted(GROUPS))}."}
    x = load()
    filters = {"district": district, "store_id": store_id, "alert_type": alert_type, "tier": tier}
    for col, val in filters.items():
        if val:
            x = x[x[col] == val]
    if week_from:
        x = x[x.week >= week_from]
    if week_to:
        x = x[x.week <= week_to]
    if min_amount is not None:
        x = x[x.transaction_amount >= min_amount]
    if max_amount is not None:
        x = x[x.transaction_amount < max_amount]
    applied = {k: v for k, v in {**filters, "week_from": week_from, "week_to": week_to,
                                  "min_amount": min_amount, "max_amount": max_amount}.items() if v is not None}
    if group_by:
        result = {str(k): METRICS[metric](g) for k, g in x.groupby(group_by)}
    else:
        result = METRICS[metric](x)
    return {"metric": metric, "group_by": group_by, "filters": applied, "rows_used": int(len(x)), "result": result}


def chain_overview() -> dict:
    """Headline numbers for all 120 stores over the 8 weeks."""
    a = load()
    r = a[a.reviewed]
    return {
        "alerts": int(len(a)), "stores": int(a.store_id.nunique()), "weeks": 8,
        "review_rate": round(float(a.reviewed.mean()), 3),
        "real_review_rate": round(float(a.real_review.mean()), 3),
        "confirmed_rate_when_reviewed": round(float(r.confirmed.mean()), 3),
        "rushed_share_of_reviews": round(float(r.rushed.mean()), 3),
        "monday_share_of_reviews": round(float((r.reviewed_at.dt.dayofweek == 0).mean()), 3),
        "review_rate_by_district": a.groupby("district").reviewed.mean().round(3).to_dict(),
        "confirmed_rate_by_type": type_confirmed_rates(),
    }
