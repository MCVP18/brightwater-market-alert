"""
Brightwater Market - alert review analysis
Reproduces every number in the take-home write-up.

Usage:  python brightwater_analysis.py Brightwater_Exceptions_Aug-Oct_2026.xlsx
Output: Brightwater_Analysis_Results.xlsx (one sheet per finding)
Needs:  pandas, numpy, openpyxl
"""
import sys
import numpy as np
import pandas as pd

SRC = sys.argv[1] if len(sys.argv) > 1 else "Brightwater_Exceptions_Aug-Oct_2026.xlsx"
OUT = "Brightwater_Analysis_Results.xlsx"
TIER = {"Manual card entry": "High", "No-receipt refund": "High",
        "Post-void": "Medium", "Employee discount": "Medium", "Price override": "Low"}
FAST = 30            # a review of 30 seconds or less counts as "rushed"
START = pd.Timestamp("2026-08-31")

# ---------------------------------------------------------------- 1. Load and clean
raw = pd.read_excel(SRC, "Alerts")
stores = pd.read_excel(SRC, "Stores")
quality = []
dups = int(raw.duplicated().sum())
a = raw.drop_duplicates().copy()
quality.append(("Duplicate rows", dups, f"Removed ({len(raw):,} -> {len(a):,} alerts)"))
blank = a.district.isna()
quality.append(("Alerts with no district (S119, S120)", int(blank.sum()),
                "Set to D8: both opened Sep 28 and weren't added to the district setup (confirmed by Keneavy)"))
a.loc[a.store_id.isin(["S119", "S120"]), "district"] = "D8"
stores.loc[stores.store_id.isin(["S119", "S120"]), "district"] = "D8"
quality.append(("Store S099 alerts (none reviewed)", int((a.store_id == "S099").sum()),
                "Kept; flagged as a possible data feed problem"))
rv = a.status == "Reviewed"
hrs = a.loc[rv, "reviewed_at"].dt.hour.value_counts()
quality.append(("Review hours spread over all 24 hours (min/max reviews per hour)", f"{hrs.min()}/{hrs.max()}",
                "Used the day of review only, not the hour"))
quality.append(("Reviewed alerts missing role/time/length/outcome",
                int((rv & (a.reviewer_role.isna() | a.reviewed_at.isna() | a.review_seconds.isna() | a.outcome.isna())).sum()), "None"))
quality.append(("Unreviewed alerts with role/time/length/outcome",
                int((~rv & (a.reviewer_role.notna() | a.reviewed_at.notna() | a.review_seconds.notna() | a.outcome.notna())).sum()), "None"))
quality.append(("Blank or negative amounts", int((a.transaction_amount.isna() | (a.transaction_amount <= 0)).sum()), "None"))
quality.append(("Reviews dated before their alert", int((a.reviewed_at < a.created_at).sum()), "None"))
quality = pd.DataFrame(quality, columns=["Check", "Count", "How it was handled"])

a["reviewed"] = a.status == "Reviewed"
a["confirmed"] = a.outcome == "Confirmed issue"
a["tier"] = a.alert_type.map(TIER)
a["real"] = a.reviewed & (a.review_seconds > FAST)
a["week"] = (a.created_at - START).dt.days // 7 + 1
r = a[a.reviewed].copy()

# ---------------------------------------------------------------- Finding 1: districts
f1 = a.groupby("district").agg(stores=("store_id", "nunique"), alerts=("alert_id", "size"),
                               reviewed_pct=("reviewed", "mean"))
f1["alerts_per_store_per_week"] = f1.alerts / f1.stores / 8
f1["dm_reviews"] = r[r.reviewer_role == "District Manager"].groupby("district").size()
st = a.groupby(["district", "store_id"]).reviewed.mean().reset_index()
total = ((st.reviewed - st.reviewed.mean()) ** 2).sum()
between = ((st.groupby("district").reviewed.transform("mean") - st.reviewed.mean()) ** 2).sum()
f1_note = pd.DataFrame({"Measure": ["Share of store-to-store difference explained by district",
                                    "Overall review rate", "Stores reviewing under 25%"],
                        "Value": [round(between / total, 3), round(a.reviewed.mean(), 3), int((st.reviewed < .25).sum())]})
f1_weekly = a.pivot_table(index="week", columns="district", values="reviewed", aggfunc="mean").round(3)

# ---------------------------------------------------------------- Finding 2: alert types
f2 = a.groupby("alert_type").agg(alerts=("alert_id", "size"), reviewed_pct=("reviewed", "mean"),
                                 median_amount=("transaction_amount", "median"))
f2["share_of_alerts"] = f2.alerts / len(a)
f2["confirmed_when_reviewed"] = r.groupby("alert_type").confirmed.mean()
f2["confirmed_real_reviews_only"] = r[r.real].groupby("alert_type").confirmed.mean()
cd = r[r.confirmed].groupby("alert_type").transaction_amount.sum()
f2["confirmed_dollars"] = cd
f2["share_of_confirmed_dollars"] = cd / cd.sum()
unrev = a[~a.reviewed].groupby("alert_type").size()
f2["est_real_problems_unopened"] = (unrev * f2.confirmed_when_reviewed).round()

# ---------------------------------------------------------------- Finding 3: rushed reviews
bands = pd.cut(r.review_seconds, [0, 10, 20, 30, 60, 120, 300, 1000])
f3 = r.groupby(bands, observed=True).agg(reviews=("alert_id", "size"), confirmed_pct=("confirmed", "mean"))
f3.index = f3.index.astype(str)
fs = r.assign(fast=r.review_seconds <= FAST).groupby("store_id").fast.mean()
f3_note = pd.DataFrame({"Measure": ["Reviews of 30 seconds or less", "Share of all reviews",
                                    "Confirmed rate, 30 s or less", "Confirmed rate, over 30 s",
                                    "Stores rushing over half their reviews", "Alerts given a real review"],
                        "Value": [int((r.review_seconds <= FAST).sum()), round((r.review_seconds <= FAST).mean(), 3),
                                  round(r[r.review_seconds <= FAST].confirmed.mean(), 3), round(r[r.real].confirmed.mean(), 3),
                                  int((fs > .5).sum()), round(a.real.mean(), 3)]})

# ---------------------------------------------------------------- Finding 4: weekly habit
r["lag_hours"] = (r.reviewed_at - r.created_at).dt.total_seconds() / 3600
f4 = r.reviewed_at.dt.day_name().value_counts(normalize=True).rename("share_of_reviews").to_frame()
f4_note = pd.DataFrame({"Measure": ["Median hours before review", "Reviews waiting over 3 days",
                                    "Longest wait (days)", "Confirmed rate, reviewed within 24 h",
                                    "Confirmed rate, reviewed after 4 days"],
                        "Value": [round(r.lag_hours.median(), 1), round((r.lag_hours > 72).mean(), 3),
                                  round(r.lag_hours.max() / 24, 1),
                                  round(r[r.lag_hours <= 24].confirmed.mean(), 3),
                                  round(r[r.lag_hours > 96].confirmed.mean(), 3)]})

# ---------------------------------------------------------------- Tiers and success baselines
tiers = a.groupby("tier").agg(alerts=("alert_id", "size"), reviewed_pct=("reviewed", "mean"),
                              real_review_pct=("real", "mean"))
tiers["share_of_alerts"] = tiers.alerts / len(a)
tiers["share_of_real_problems"] = r[r.confirmed].groupby("tier").size() / r.confirmed.sum()
tiers["share_of_confirmed_dollars"] = r[r.confirmed].groupby("tier").transaction_amount.sum() / cd.sum()
store_weeks = r.groupby(["store_id", "week"]).review_seconds.sum() / 60
hi = a[a.tier == "High"]
baselines = pd.DataFrame({"Measure": [
    "High-tier alerts given a real review (main measure)", "High + Medium review rate",
    "D6 High-tier review rate", "D7 High-tier review rate", "Confirmed issues per store per week",
    "High-tier reviews of 30 s or less", "Median review minutes per store per week", "Low-tier confirmed rate"],
    "Today": [hi.real.mean(), a[a.tier != "Low"].reviewed.mean(),
              hi[hi.district == "D6"].reviewed.mean(), hi[hi.district == "D7"].reviewed.mean(),
              r.confirmed.sum() / (118 * 8 + 2 * 4),
              (r[r.tier == "High"].review_seconds <= FAST).mean(), store_weeks.median(),
              r[r.tier == "Low"].confirmed.mean()],
    "Target at 8 weeks": [">= 70%", ">= 70%", ">= 45%", ">= 45%", ">= 1.2", "<= 20%", "No increase", "< 5%"]})
baselines["Today"] = baselines.Today.round(3)

# ---------------------------------------------------------------- Next release: price-override thresholds
po = a[a.alert_type == "Price override"]
rows = []
for t in (10, 15, 20, 25, 30, 50):
    s = po[po.transaction_amount < t]
    rows.append({"Not flagged if under": f"${t}", "alerts_removed": len(s), "share_of_all_alerts": len(s) / len(a),
                 "per_store_per_week": len(s) / 120 / 8, "confirmed_lost": int(s.confirmed.sum()),
                 "confirmed_dollars_lost": round(s.loc[s.confirmed, "transaction_amount"].sum(), 2)})
thresholds = pd.DataFrame(rows)

# ---------------------------------------------------------------- Review judgment consistency
rr = r[r.real]
judgment_role = rr.groupby("reviewer_role").confirmed.agg(reviews="size", confirmed_pct="mean")
rng = np.random.default_rng(0)
jrows = []
for ty in TIER:
    s = rr[rr.alert_type == ty].groupby("store_id").confirmed.agg(["size", "sum"])
    s = s[s["size"] >= 8]
    p = s["sum"].sum() / s["size"].sum()
    rate = s["sum"] / s["size"]
    sims = [(rng.binomial(s["size"], p) / s["size"]).std() for _ in range(2000)]
    jrows.append({"alert_type": ty, "stores_with_8+_real_reviews": len(s), "overall_confirmed": round(p, 3),
                  "store_10th_pct": round(rate.quantile(.1), 3), "store_90th_pct": round(rate.quantile(.9), 3),
                  "chance_of_this_much_spread": round(float(np.mean(np.array(sims) >= rate.std())), 3)})
judgment_type = pd.DataFrame(jrows)

# ---------------------------------------------------------------- Write workbook
with pd.ExcelWriter(OUT) as xw:
    quality.to_excel(xw, "Data quality", index=False)
    f1.round(3).to_excel(xw, "F1 Districts")
    f1_note.to_excel(xw, "F1 Districts", index=False, startrow=len(f1) + 3)
    f1_weekly.to_excel(xw, "F1 Weekly review rate")
    f2.round(3).to_excel(xw, "F2 Alert types")
    f3.round(3).to_excel(xw, "F3 Review speed")
    f3_note.to_excel(xw, "F3 Review speed", index=False, startrow=len(f3) + 3)
    f4.round(3).to_excel(xw, "F4 Review timing")
    f4_note.to_excel(xw, "F4 Review timing", index=False, startrow=len(f4) + 3)
    tiers.round(3).to_excel(xw, "Tiers")
    baselines.to_excel(xw, "Success baselines", index=False)
    thresholds.round(3).to_excel(xw, "Next - PO thresholds", index=False)
    judgment_role.round(3).to_excel(xw, "Next - Judgment")
    judgment_type.to_excel(xw, "Next - Judgment", index=False, startrow=len(judgment_role) + 3)
print(f"Wrote {OUT}")
