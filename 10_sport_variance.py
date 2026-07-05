#!/usr/bin/env python3
"""
10_sport_variance.py
====================
Sport-specific variance decomposition and supplementary statistics.

Computes:
  1. Sport-specific ICC(1,1), SB(k=5), and Person/Route/Occasion %
     for cycling and running separately (Shared Concern #1, Rounds 1-3)
  2. FI gradient-bin coverage statistics (Shared Concern #4, Rounds 1-3)
  3. Route-type proportions in full dataset vs high-engagement subset
     (Should-Address, Rounds 2-3)

Outputs:
  - results/sport_variance.txt  (summary statistics)
"""

import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import GroupKFold, cross_val_score

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
RES_DIR = BASE / "results"
RES_DIR.mkdir(exist_ok=True)

ROUTE_FEATURES = [
    "total_ascent", "total_descent", "alt_range", "max_alt", "min_alt",
    "grad_mean", "grad_std", "pct_climb", "pct_desc", "pct_flat",
    "asc_front", "desc_front", "dur_min",
]

METRICS = [
    ("GACD (cardiac drift)", "gacd_rate", "gacd"),
    ("Gradient sensitivity", "gacd_gradient_coef", "gradsens"),
    ("Speed sensitivity", "gacd_speed_coef", "speedsens"),
]

# ── Load data ────────────────────────────────────────────────────────────────
df_abc = pd.read_csv(DATA_DIR / "abc_metrics.csv")
df_meixner = pd.read_csv(DATA_DIR / "meixner_4d_indices.csv")

lines = []

def log(s=""):
    lines.append(s)
    print(s)


# ============================================================
# 1. Sport-specific variance decomposition
# ============================================================

def compute_icc_oneway(data, user_col="userId", value_col="value", min_workouts=5):
    counts = data.groupby(user_col).size()
    valid_users = counts[counts >= min_workouts].index
    sub = data[data[user_col].isin(valid_users)].copy()
    if len(sub) < 10 or sub[user_col].nunique() < 3:
        return float("nan"), 0, 0
    groups = sub.groupby(user_col)[value_col]
    k_groups = groups.ngroups
    n_per_group = groups.size().values
    grand_mean = sub[value_col].mean()
    N = len(sub)
    ss_between = sum(
        n * (g_mean - grand_mean) ** 2
        for n, g_mean in zip(n_per_group, groups.mean().values)
    )
    ss_within = sum(((g - g.mean()) ** 2).sum() for _, g in groups)
    df_between = k_groups - 1
    df_within = N - k_groups
    ms_between = ss_between / df_between
    ms_within = ss_within / df_within
    n0 = (N - sum(n ** 2 for n in n_per_group) / N) / (k_groups - 1)
    icc = (ms_between - ms_within) / (ms_between + (n0 - 1) * ms_within)
    return icc, k_groups, N


def compute_convergence_sb(data, user_col="userId", value_col="value", k=5):
    """Compute SB reliability at k sessions."""
    counts = data.groupby(user_col).size()
    valid_users = counts[counts >= 2 * k].index
    sub = data[data[user_col].isin(valid_users)].copy()
    if len(valid_users) < 5:
        return float("nan"), len(valid_users)
    first_means = []
    second_means = []
    for uid, group in sub.groupby(user_col):
        vals = group[value_col].values
        perm = np.random.permutation(vals)
        first_means.append(perm[:k].mean())
        second_means.append(perm[k:2*k].mean())
    if len(first_means) < 5:
        return float("nan"), len(first_means)
    r, _ = stats.pearsonr(first_means, second_means)
    sb = 2 * r / (1 + r)
    return sb, len(first_means)


def compute_variance_decomposition(data, user_col="userId", value_col="value",
                                   route_features=ROUTE_FEATURES, min_workouts=5):
    counts = data.groupby(user_col).size()
    valid_users = counts[counts >= min_workouts].index
    sub = data[data[user_col].isin(valid_users)].copy()
    if len(sub) < 10 or sub[user_col].nunique() < 3:
        return float("nan"), float("nan"), float("nan")

    icc, _, _ = compute_icc_oneway(sub, user_col=user_col, value_col=value_col,
                                   min_workouts=min_workouts)
    if np.isnan(icc):
        return float("nan"), float("nan"), float("nan")

    user_means = sub.groupby(user_col)[value_col].transform("mean")
    sub = sub.copy()
    sub["deviation"] = sub[value_col] - user_means

    available_features = [f for f in route_features if f in sub.columns]
    sub_clean = sub.dropna(subset=available_features + ["deviation"])

    if len(sub_clean) < 10 or len(available_features) == 0:
        return icc * 100, 0.0, (1 - icc) * 100

    X = sub_clean[available_features].values
    y = sub_clean["deviation"].values
    groups = sub_clean[user_col].values

    n_groups = len(np.unique(groups))
    n_folds = min(5, n_groups)
    if n_folds < 2:
        route_r2 = 0.0
    else:
        gkf = GroupKFold(n_splits=n_folds)
        ridge = RidgeCV(alphas=[0.01, 0.1, 1.0, 10.0, 100.0])
        cv_scores = cross_val_score(ridge, X, y, cv=gkf, groups=groups, scoring="r2")
        route_r2 = max(0, np.mean(cv_scores))

    pct_person = icc * 100
    pct_route = route_r2 * (1 - icc) * 100
    pct_occasion = 100 - pct_person - pct_route
    return pct_person, pct_route, pct_occasion


log("=" * 70)
log("SPORT-SPECIFIC VARIANCE DECOMPOSITION")
log("=" * 70)

# Sport breakdown in high-engagement subset
counts_by_sport = df_abc.groupby("userId").size()
he_users = counts_by_sport[counts_by_sport >= 5].index
df_he = df_abc[df_abc["userId"].isin(he_users)].copy()

sport_counts_he = df_he["sport"].value_counts()
log(f"\nHigh-engagement subset: {len(df_he)} workouts, {len(he_users)} users")
log("Sport breakdown (high-engagement):")
for sport, cnt in sport_counts_he.items():
    pct = 100 * cnt / len(df_he)
    n_users = df_he[df_he["sport"] == sport]["userId"].nunique()
    log(f"  {sport:20s}: {cnt:5d} workouts ({pct:5.1f}%), {n_users:4d} users")

log("")

# For each sport with enough data, compute ICC, SB, decomposition
for sport_name in ["bike", "run", "mountain bike"]:
    sport_df = df_he[df_he["sport"] == sport_name].copy()
    n_workouts = len(sport_df)
    n_users = sport_df["userId"].nunique()
    users_ge5 = sport_df.groupby("userId").size()
    n_users_ge5 = (users_ge5 >= 5).sum()

    log(f"--- {sport_name.upper()} ---")
    log(f"  Total: {n_workouts} workouts, {n_users} users ({n_users_ge5} with ≥5 sessions)")

    if n_users_ge5 < 5:
        log(f"  *** Insufficient users (≥5 sessions) for stable ICC estimation ***")
        log(f"  [KEY] sport_{sport_name}_INSUFFICIENT = True")
        log("")
        continue

    for metric_name, metric_col, short_name in METRICS:
        metric_df = sport_df[["userId", metric_col] + ROUTE_FEATURES].dropna(subset=[metric_col])
        metric_df = metric_df.rename(columns={metric_col: "value"})

        icc, k_users, n_obs = compute_icc_oneway(metric_df, min_workouts=5)
        sb, n_sb_users = compute_convergence_sb(metric_df, k=5)
        pct_p, pct_r, pct_o = compute_variance_decomposition(metric_df, min_workouts=5)

        log(f"  {metric_name}:")
        log(f"    ICC(1,1) = {icc:.3f}  (K={k_users}, N={n_obs})")
        log(f"    SB(k=5)  = {sb:.3f}  (n_users={n_sb_users})")
        log(f"    %Person  = {pct_p:.1f}%")
        log(f"    %Route   = {pct_r:.1f}%")
        log(f"    %Occasion= {pct_o:.1f}%")
        log(f"    [KEY] icc_{short_name}_{sport_name} = {icc:.3f}")
        log(f"    [KEY] sb_{short_name}_{sport_name} = {sb:.3f}")
        log(f"    [KEY] pct_person_{short_name}_{sport_name} = {pct_p:.1f}")
        log(f"    [KEY] pct_route_{short_name}_{sport_name} = {pct_r:.1f}")
        log(f"    [KEY] pct_occasion_{short_name}_{sport_name} = {pct_o:.1f}")
    log("")


# ============================================================
# 2. FI gradient-bin coverage statistics
# ============================================================
log("=" * 70)
log("FI GRADIENT-BIN COVERAGE STATISTICS")
log("=" * 70)

# Recompute bin coverage from meixner data
# FI is non-NaN when at least some bins were valid
fi_valid = df_meixner[df_meixner["FI"].notna()]
fi_total = len(df_meixner)
fi_count = len(fi_valid)
fi_pct = 100 * fi_count / fi_total
log(f"Workouts with valid FI: {fi_count}/{fi_total} ({fi_pct:.1f}%)")
log(f"Workouts without valid FI: {fi_total - fi_count} ({100-fi_pct:.1f}%)")

# To count bins, we need to recompute from the raw data
# Instead, we'll note the bin structure and report what we can
grad_bins = [(-50, -10), (-10, -3), (-3, 3), (3, 10), (10, 50)]
log(f"Gradient bins used: {grad_bins}")
log(f"FI requires >3 valid points per half per bin")
log(f"[KEY] fi_valid_pct = {fi_pct:.1f}")
log(f"[KEY] fi_valid_n = {fi_count}")
log(f"[KEY] fi_total_n = {fi_total}")
log("")


# ============================================================
# 3. Route-type proportions: full dataset vs high-engagement
# ============================================================
log("=" * 70)
log("ROUTE-TYPE PROPORTIONS: FULL vs HIGH-ENGAGEMENT")
log("=" * 70)

# Need asc_front from abc_metrics (available for all workouts with GACD)
# And from meixner for the full DI dataset
# asc_front is in abc_metrics

def classify_route(asc_front):
    if asc_front > 0.6:
        return "front-climb"
    elif asc_front < 0.4:
        return "back-climb"
    else:
        return "symmetric"

# Full dataset (abc_metrics has asc_front)
df_full = df_abc[df_abc["asc_front"].notna()].copy()
df_full["route_type"] = df_full["asc_front"].apply(classify_route)
full_counts = df_full["route_type"].value_counts()
full_total = len(df_full)

log(f"\nFull dataset (N = {full_total}):")
for rt in ["front-climb", "symmetric", "back-climb"]:
    cnt = full_counts.get(rt, 0)
    pct = 100 * cnt / full_total
    log(f"  {rt:15s}: {cnt:5d} ({pct:5.1f}%)")
    log(f"  [KEY] route_{rt}_full_pct = {pct:.1f}")

# High-engagement subset
df_he_rt = df_he[df_he["asc_front"].notna()].copy()
df_he_rt["route_type"] = df_he_rt["asc_front"].apply(classify_route)
he_counts = df_he_rt["route_type"].value_counts()
he_total = len(df_he_rt)

log(f"\nHigh-engagement subset (N = {he_total}):")
for rt in ["front-climb", "symmetric", "back-climb"]:
    cnt = he_counts.get(rt, 0)
    pct = 100 * cnt / he_total
    log(f"  {rt:15s}: {cnt:5d} ({pct:5.1f}%)")
    log(f"  [KEY] route_{rt}_he_pct = {pct:.1f}")

log("")

# Save
out_txt = RES_DIR / "sport_variance.txt"
with open(out_txt, "w") as f:
    f.write("\n".join(lines))
log(f"Summary saved: {out_txt}")
log("\n✓ Sport-specific analysis complete.")
