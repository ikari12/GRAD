#!/usr/bin/env python3
"""06_supplementary.py — Additional analyses to strengthen scientific rigor.

Addresses reviewer concerns:
  S1. Descriptive statistics of the sample
  S2. Measurement error vs true Occasion separation
  S3. PCA eigenvalues and factor loadings
  S4. Spearman-Brown convergence curve (k=2..10)
  S5. FDR correction for exploratory p-values
"""

import os
import sys
import warnings
import numpy as np
from scipy import stats

warnings.filterwarnings("ignore", category=RuntimeWarning)

# ---------------------------------------------------------------------------
_BASE = os.path.dirname(os.path.abspath(__file__))
MEIXNER_PATH = os.path.join(_BASE, "data", "meixner_4d_indices.csv")
ABC_PATH = os.path.join(_BASE, "data", "abc_metrics.csv")
for _p in (MEIXNER_PATH, ABC_PATH):
    if not os.path.exists(_p):
        print(f"ERROR: data file not found: {_p}", file=sys.stderr)
        sys.exit(1)


def load_csv(path):
    with open(path, "r") as f:
        lines = [l.strip() for l in f if l.strip()]
    headers = lines[0].replace("\r", "").split(",")
    data = {h: [] for h in headers}
    for line in lines[1:]:
        vals = line.replace("\r", "").split(",")
        for h, v in zip(headers, vals):
            data[h].append(v)
    return data


def to_float_array(lst):
    out = []
    for v in lst:
        try:
            out.append(float(v))
        except (ValueError, TypeError):
            out.append(np.nan)
    return np.array(out)


# ---------------------------------------------------------------------------
print("=" * 60)
print("Loading data...")
print("=" * 60)
meixner = load_csv(MEIXNER_PATH)
abc = load_csv(ABC_PATH)

# ============================================================
# S1. DESCRIPTIVE STATISTICS
# ============================================================
print("\n" + "=" * 60)
print("S1. Descriptive Statistics")
print("=" * 60)

dur = to_float_array(meixner["dur_min"])
alt_range = to_float_array(meixner["alt_range"])
avg_hr = to_float_array(meixner["avg_hr"])
max_hr = to_float_array(meixner["max_hr"])
total_asc = to_float_array(meixner["total_ascent"])
n_points = to_float_array(meixner["n_points"])

n_total = len(meixner["id"])
n_users = len(set(meixner["userId"]))

# Sport breakdown
sport_counts = {}
for s in meixner["sport"]:
    sport_counts[s] = sport_counts.get(s, 0) + 1
sport_pcts = {k: v / n_total * 100 for k, v in sorted(sport_counts.items(), key=lambda x: -x[1])}

# Gender breakdown
gender_counts = {}
for g in meixner["gender"]:
    gender_counts[g] = gender_counts.get(g, 0) + 1

print(f"  N workouts (Study 1): {n_total}")
print(f"  N users: {n_users}")
print(f"  Workouts/user: median={np.median([list(meixner['userId']).count(u) for u in set(meixner['userId'])]):.0f}")

print(f"\n  Sport breakdown:")
for sport, pct in sport_pcts.items():
    print(f"    {sport}: {sport_counts[sport]} ({pct:.1f}%)")

print(f"\n  Gender breakdown:")
for g, c in sorted(gender_counts.items(), key=lambda x: -x[1]):
    print(f"    {g}: {c} ({c/n_total*100:.1f}%)")

valid_dur = dur[np.isfinite(dur)]
valid_alt = alt_range[np.isfinite(alt_range)]
valid_hr = avg_hr[np.isfinite(avg_hr)]
valid_asc = total_asc[np.isfinite(total_asc)]

print(f"\n  Duration (min): median={np.median(valid_dur):.1f}, IQR=[{np.percentile(valid_dur, 25):.1f}, {np.percentile(valid_dur, 75):.1f}]")
print(f"  Altitude range (m): median={np.median(valid_alt):.1f}, IQR=[{np.percentile(valid_alt, 25):.1f}, {np.percentile(valid_alt, 75):.1f}]")
print(f"  Average HR (bpm): median={np.median(valid_hr):.1f}, IQR=[{np.percentile(valid_hr, 25):.1f}, {np.percentile(valid_hr, 75):.1f}]")
print(f"  Total ascent (m): median={np.median(valid_asc):.1f}, IQR=[{np.percentile(valid_asc, 25):.1f}, {np.percentile(valid_asc, 75):.1f}]")

print(f"\n[KEY] n_workouts_study1 = {n_total}")
print(f"[KEY] n_users_study1 = {n_users}")
print(f"[KEY] median_duration_min = {np.median(valid_dur):.1f}")
print(f"[KEY] iqr_duration_lo = {np.percentile(valid_dur, 25):.1f}")
print(f"[KEY] iqr_duration_hi = {np.percentile(valid_dur, 75):.1f}")
print(f"[KEY] median_alt_range = {np.median(valid_alt):.1f}")
print(f"[KEY] iqr_alt_range_lo = {np.percentile(valid_alt, 25):.1f}")
print(f"[KEY] iqr_alt_range_hi = {np.percentile(valid_alt, 75):.1f}")
print(f"[KEY] median_avg_hr = {np.median(valid_hr):.1f}")
print(f"[KEY] median_total_ascent = {np.median(valid_asc):.1f}")

# Study 2-3 subset
abc_n = len(abc["id"])
abc_users = len(set(abc["userId"]))
print(f"\n  N workouts (Study 2-3): {abc_n}")
print(f"  N users (Study 2-3): {abc_users}")
print(f"[KEY] n_workouts_study23 = {abc_n}")
print(f"[KEY] n_users_study23 = {abc_users}")


# ============================================================
# S2. MEASUREMENT ERROR VS TRUE OCCASION SEPARATION
# ============================================================
print("\n" + "=" * 60)
print("S2. Measurement Error vs True Occasion Separation")
print("=" * 60)

# Strategy: compute ICC for users who repeated SIMILAR routes
# (same altitude range ±20%, same total ascent ±20%, same duration ±30%)
# This "route-matched" ICC should be HIGHER than the overall ICC,
# because route variance is controlled. The difference tells us
# how much of the residual is route vs true occasion.

abc_gacd = to_float_array(abc["gacd_rate"])
abc_gradsens = to_float_array(abc["gacd_gradient_coef"])
abc_speedsens = to_float_array(abc["gacd_speed_coef"])
abc_uids = abc["userId"]
abc_alt = to_float_array(abc["alt_range"])
abc_asc = to_float_array(abc["total_ascent"])
abc_dur = to_float_array(abc["dur_min"])

def compute_icc_oneway(user_groups):
    """ICC(1,1) one-way random."""
    groups = [g for g in user_groups.values() if len(g) >= 2]
    if len(groups) < 5:
        return np.nan
    k_list = [len(g) for g in groups]
    N = sum(k_list)
    K = len(groups)
    grand_mean = np.mean([v for g in groups for v in g])
    SSB = sum(len(g) * (np.mean(g) - grand_mean)**2 for g in groups)
    SSW = sum(sum((v - np.mean(g))**2 for v in g) for g in groups)
    MSB = SSB / (K - 1) if K > 1 else 0
    MSW = SSW / (N - K) if N > K else 0
    k0 = (N - sum(ki**2 for ki in k_list) / N) / (K - 1)
    if MSW == 0 and MSB == 0:
        return np.nan
    icc = (MSB - MSW) / (MSB + (k0 - 1) * MSW)
    return max(0, icc)

# Overall ICC
for metric_name, metric_vals in [("gacd", abc_gacd), ("gradsens", abc_gradsens), ("speedsens", abc_speedsens)]:
    # Overall ICC
    user_groups_all = {}
    for i, uid in enumerate(abc_uids):
        if np.isfinite(metric_vals[i]):
            user_groups_all.setdefault(uid, []).append(metric_vals[i])
    icc_all = compute_icc_oneway(user_groups_all)

    # Route-matched ICC: only pairs where alt_range and total_ascent are within 20%
    user_route_groups = {}
    user_workouts = {}
    for i, uid in enumerate(abc_uids):
        if np.isfinite(metric_vals[i]) and np.isfinite(abc_alt[i]) and np.isfinite(abc_asc[i]):
            user_workouts.setdefault(uid, []).append(i)

    route_matched_count = 0
    for uid, indices in user_workouts.items():
        if len(indices) < 2:
            continue
        # Find pairs with similar route characteristics
        matched = []
        for idx in indices:
            a, asc, d = abc_alt[idx], abc_asc[idx], abc_dur[idx]
            if a > 0 and asc > 0 and d > 0:
                matched.append(idx)
        if len(matched) < 2:
            continue
        # Use the first workout as reference, keep those within ±20% alt/asc
        ref_alt = abc_alt[matched[0]]
        ref_asc = abc_asc[matched[0]]
        similar = [matched[0]]
        for idx in matched[1:]:
            alt_ratio = abc_alt[idx] / ref_alt if ref_alt > 0 else 999
            asc_ratio = abc_asc[idx] / ref_asc if ref_asc > 0 else 999
            if 0.8 <= alt_ratio <= 1.2 and 0.8 <= asc_ratio <= 1.2:
                similar.append(idx)
        if len(similar) >= 2:
            user_route_groups[uid] = [metric_vals[j] for j in similar]
            route_matched_count += len(similar)

    icc_route_matched = compute_icc_oneway(user_route_groups)

    print(f"\n  {metric_name}:")
    print(f"    ICC (all routes):     {icc_all:.3f}")
    print(f"    ICC (route-matched):  {icc_route_matched:.3f}")
    print(f"    N route-matched pairs: {route_matched_count}")
    print(f"    Difference (route effect): {icc_route_matched - icc_all:.3f}")
    print(f"    → When route is controlled, Person ICC increases by {(icc_route_matched - icc_all)*100:.1f}pp")
    print(f"    → This {(icc_route_matched - icc_all)*100:.1f}pp was misattributed to Occasion in original decomposition")

    print(f"[KEY] icc_all_{metric_name} = {icc_all:.3f}")
    print(f"[KEY] icc_route_matched_{metric_name} = {icc_route_matched:.3f}")
    print(f"[KEY] icc_diff_{metric_name} = {icc_route_matched - icc_all:.3f}")
    print(f"[KEY] n_route_matched_{metric_name} = {route_matched_count}")

# Summary: estimate upper bound on measurement error
# If route-matched ICC is X and overall ICC is Y, then:
# Route variance ≈ X - Y
# True Occasion ≈ 1 - X (what remains after controlling person AND route)
# Measurement error is part of True Occasion but we can't separate further
print("\n  --- Revised Variance Decomposition ---")
for metric_name, metric_vals in [("gacd", abc_gacd), ("gradsens", abc_gradsens), ("speedsens", abc_speedsens)]:
    user_groups_all = {}
    for i, uid in enumerate(abc_uids):
        if np.isfinite(metric_vals[i]):
            user_groups_all.setdefault(uid, []).append(metric_vals[i])
    icc_all = compute_icc_oneway(user_groups_all)

    user_route_groups = {}
    user_workouts = {}
    for i, uid in enumerate(abc_uids):
        if np.isfinite(metric_vals[i]) and np.isfinite(abc_alt[i]) and np.isfinite(abc_asc[i]):
            user_workouts.setdefault(uid, []).append(i)
    for uid, indices in user_workouts.items():
        matched = [idx for idx in indices if abc_alt[idx] > 0 and abc_asc[idx] > 0]
        if len(matched) < 2:
            continue
        ref_alt, ref_asc = abc_alt[matched[0]], abc_asc[matched[0]]
        similar = [matched[0]]
        for idx in matched[1:]:
            if ref_alt > 0 and ref_asc > 0:
                if 0.8 <= abc_alt[idx]/ref_alt <= 1.2 and 0.8 <= abc_asc[idx]/ref_asc <= 1.2:
                    similar.append(idx)
        if len(similar) >= 2:
            user_route_groups[uid] = [metric_vals[j] for j in similar]

    icc_rm = compute_icc_oneway(user_route_groups)
    pct_person = icc_all * 100
    pct_route = max(0, (icc_rm - icc_all)) * 100
    pct_residual = (1 - icc_rm) * 100
    print(f"  {metric_name}: Person={pct_person:.1f}%, Route≈{pct_route:.1f}%, Residual(Occasion+Error)={pct_residual:.1f}%")
    print(f"[KEY] revised_pct_person_{metric_name} = {pct_person:.1f}")
    print(f"[KEY] revised_pct_route_{metric_name} = {pct_route:.1f}")
    print(f"[KEY] revised_pct_residual_{metric_name} = {pct_residual:.1f}")


# ============================================================
# S3. PCA EIGENVALUES AND FACTOR LOADINGS
# ============================================================
print("\n" + "=" * 60)
print("S3. PCA Eigenvalues and Factor Loadings")
print("=" * 60)

di_vals = to_float_array(meixner["DI"])
fi_vals = to_float_array(meixner["FI"])
ri_vals = to_float_array(meixner["RI"])

# Filter valid rows (all three finite)
valid_mask = np.isfinite(di_vals) & np.isfinite(fi_vals) & np.isfinite(ri_vals)
di_v = di_vals[valid_mask]
fi_v = fi_vals[valid_mask]
ri_v = ri_vals[valid_mask]
n_valid = len(di_v)

# Standardize
X = np.column_stack([
    (di_v - np.mean(di_v)) / np.std(di_v),
    (fi_v - np.mean(fi_v)) / np.std(fi_v),
    (ri_v - np.mean(ri_v)) / np.std(ri_v),
])

# PCA via eigendecomposition of correlation matrix
corr = np.corrcoef(X.T)
eigenvalues, eigenvectors = np.linalg.eigh(corr)
# Sort descending
idx = np.argsort(eigenvalues)[::-1]
eigenvalues = eigenvalues[idx]
eigenvectors = eigenvectors[:, idx]

# Parallel analysis (Monte Carlo)
n_iter = 1000
random_eigenvalues = np.zeros((n_iter, 3))
for it in range(n_iter):
    random_data = np.random.randn(n_valid, 3)
    random_corr = np.corrcoef(random_data.T)
    re = np.sort(np.linalg.eigvalsh(random_corr))[::-1]
    random_eigenvalues[it] = re
parallel_threshold = np.percentile(random_eigenvalues, 95, axis=0)

print(f"  N valid (DI, FI, RI all finite): {n_valid}")
print(f"\n  Correlation matrix:")
labels = ["DI", "FI", "RI"]
for i in range(3):
    row = "  " + "  ".join(f"{corr[i,j]:+.3f}" for j in range(3))
    print(f"    {labels[i]}: {row}")

print(f"\n  {'Component':<12} {'Eigenvalue':<12} {'% Variance':<12} {'Parallel 95%':<14} {'Retain?'}")
for i in range(3):
    retain = "Yes" if eigenvalues[i] > parallel_threshold[i] else "No"
    print(f"    PC{i+1:<9} {eigenvalues[i]:<12.3f} {eigenvalues[i]/3*100:<12.1f} {parallel_threshold[i]:<14.3f} {retain}")

print(f"\n  Factor loadings (PC1):")
for i, label in enumerate(labels):
    print(f"    {label}: {eigenvectors[i, 0]:+.3f}")

n_retain = sum(1 for i in range(3) if eigenvalues[i] > parallel_threshold[i])
print(f"\n  Factors retained by parallel analysis: {n_retain}")
print(f"  Shared variance DI-FI: {corr[0,1]**2*100:.1f}%")

print(f"\n[KEY] pca_eigenvalue_1 = {eigenvalues[0]:.3f}")
print(f"[KEY] pca_eigenvalue_2 = {eigenvalues[1]:.3f}")
print(f"[KEY] pca_eigenvalue_3 = {eigenvalues[2]:.3f}")
print(f"[KEY] pca_parallel_threshold_1 = {parallel_threshold[0]:.3f}")
print(f"[KEY] pca_parallel_threshold_2 = {parallel_threshold[1]:.3f}")
print(f"[KEY] pca_loading_di_pc1 = {eigenvectors[0, 0]:+.3f}")
print(f"[KEY] pca_loading_fi_pc1 = {eigenvectors[1, 0]:+.3f}")
print(f"[KEY] pca_loading_ri_pc1 = {eigenvectors[2, 0]:+.3f}")
print(f"[KEY] di_fi_shared_variance_pct = {corr[0,1]**2*100:.1f}")
print(f"[KEY] di_fi_corr = {corr[0,1]:.3f}")
print(f"[KEY] di_ri_corr = {corr[0,2]:.3f}")
print(f"[KEY] fi_ri_corr = {corr[1,2]:.3f}")


# ============================================================
# S4. CONVERGENCE CURVE (Spearman-Brown at k=2..10)
# ============================================================
print("\n" + "=" * 60)
print("S4. Spearman-Brown Convergence Curve (k=2..10)")
print("=" * 60)

for metric_name, metric_vals in [("gacd", abc_gacd), ("gradsens", abc_gradsens), ("speedsens", abc_speedsens)]:
    # Collect per-user vectors
    user_vals = {}
    for i, uid in enumerate(abc_uids):
        if np.isfinite(metric_vals[i]):
            user_vals.setdefault(uid, []).append(metric_vals[i])

    print(f"\n  {metric_name}:")
    print(f"    {'k':<5} {'Split-half r':<14} {'SB reliability':<16} {'Status'}")
    for k in range(2, 11):
        # Users with >= k measurements
        eligible = {u: v[:k] for u, v in user_vals.items() if len(v) >= k}
        if len(eligible) < 10:
            print(f"    {k:<5} {'n/a':<14} {'n/a':<16} (n<10)")
            continue
        # Split-half: odd vs even indices
        odd_means = []
        even_means = []
        for u, vals in eligible.items():
            odd = [vals[j] for j in range(0, k, 2)]
            even = [vals[j] for j in range(1, k, 2)]
            if len(odd) > 0 and len(even) > 0:
                odd_means.append(np.mean(odd))
                even_means.append(np.mean(even))
        if len(odd_means) < 5:
            continue
        r_sh = np.corrcoef(odd_means, even_means)[0, 1]
        sb = 2 * r_sh / (1 + r_sh) if r_sh > 0 else 0
        status = "✓ ≥0.80" if sb >= 0.80 else "  <0.80"
        print(f"    {k:<5} {r_sh:<14.3f} {sb:<16.3f} {status}")
        print(f"[KEY] converge_{metric_name}_k{k}_sh = {r_sh:.3f}")
        print(f"[KEY] converge_{metric_name}_k{k}_sb = {sb:.3f}")


# ============================================================
# S5. FDR CORRECTION FOR EXPLORATORY P-VALUES
# ============================================================
print("\n" + "=" * 60)
print("S5. FDR Correction (Benjamini-Hochberg) for Exploratory Tests")
print("=" * 60)

# Collect all exploratory p-values from descent placement analysis
# We need to recompute these from data
desc_front = to_float_array(abc["desc_front"])
gacd_rate = to_float_array(abc["gacd_rate"])
grad_std = to_float_array(abc["grad_std"])
sport_list = abc["sport"]

# Compute p-values for each exploratory test
exploratory_tests = {}

# E1: Descent-front vs GACD (between-person)
valid = np.isfinite(desc_front) & np.isfinite(gacd_rate)
r, p = stats.pearsonr(desc_front[valid], gacd_rate[valid])
exploratory_tests["E1_desc_front_vs_gacd"] = (r, p)

# E1: Steepness interaction - gentle
gentle = valid & (grad_std < 5)
if np.sum(gentle) > 10:
    r_g, p_g = stats.pearsonr(desc_front[gentle], gacd_rate[gentle])
    exploratory_tests["E1_gentle_slope"] = (r_g, p_g)

# E1: Steepness interaction - moderate
moderate = valid & (grad_std >= 5) & (grad_std < 8)
if np.sum(moderate) > 10:
    r_m, p_m = stats.pearsonr(desc_front[moderate], gacd_rate[moderate])
    exploratory_tests["E1_moderate_slope"] = (r_m, p_m)

# E1: Sport-specific
for sport_name in ["bike", "run", "mountain bike"]:
    sport_mask = valid & np.array([s == sport_name for s in sport_list])
    if np.sum(sport_mask) > 10:
        r_s, p_s = stats.pearsonr(desc_front[sport_mask], gacd_rate[sport_mask])
        exploratory_tests[f"E1_{sport_name}"] = (r_s, p_s)

# E2: Speed correlation with gradient sensitivity
avg_speed = to_float_array(abc["avg_speed"])
valid_gs = np.isfinite(abc_gradsens) & np.isfinite(avg_speed)
if np.sum(valid_gs) > 10:
    r_gs, p_gs = stats.pearsonr(abc_gradsens[valid_gs], avg_speed[valid_gs])
    exploratory_tests["E2_gradsens_vs_speed"] = (r_gs, p_gs)

valid_ss = np.isfinite(abc_speedsens) & np.isfinite(avg_speed)
if np.sum(valid_ss) > 10:
    r_ss, p_ss = stats.pearsonr(abc_speedsens[valid_ss], avg_speed[valid_ss])
    exploratory_tests["E2_speedsens_vs_speed"] = (r_ss, p_ss)

# Apply BH-FDR
test_names = list(exploratory_tests.keys())
p_values = np.array([exploratory_tests[t][1] for t in test_names])
r_values = np.array([exploratory_tests[t][0] for t in test_names])
n_tests = len(p_values)
sorted_idx = np.argsort(p_values)
fdr_adjusted = np.zeros(n_tests)
for rank, idx in enumerate(sorted_idx):
    fdr_adjusted[idx] = p_values[idx] * n_tests / (rank + 1)
# Enforce monotonicity
for i in range(n_tests - 2, -1, -1):
    fdr_adjusted[sorted_idx[i]] = min(fdr_adjusted[sorted_idx[i]], fdr_adjusted[sorted_idx[i+1]] if i+1 < n_tests else 1.0)
fdr_adjusted = np.minimum(fdr_adjusted, 1.0)

print(f"\n  {'Test':<30} {'r':>8} {'p (raw)':>12} {'p (FDR)':>12} {'Sig.'}")
print(f"  {'-'*30} {'-'*8} {'-'*12} {'-'*12} {'-'*6}")
for i, name in enumerate(test_names):
    sig = "***" if fdr_adjusted[i] < 0.001 else "**" if fdr_adjusted[i] < 0.01 else "*" if fdr_adjusted[i] < 0.05 else "ns"
    print(f"  {name:<30} {r_values[i]:+.4f} {p_values[i]:>12.2e} {fdr_adjusted[i]:>12.4f} {sig}")
    print(f"[KEY] fdr_{name}_r = {r_values[i]:.4f}")
    print(f"[KEY] fdr_{name}_p_raw = {p_values[i]:.2e}")
    print(f"[KEY] fdr_{name}_p_adj = {fdr_adjusted[i]:.4f}")

n_sig = sum(1 for p in fdr_adjusted if p < 0.05)
print(f"\n  {n_sig}/{n_tests} tests remain significant after FDR correction")
print(f"[KEY] fdr_n_significant = {n_sig}")
print(f"[KEY] fdr_n_tests = {n_tests}")

print("\n" + "=" * 60)
print("All supplementary analyses complete.")
print("=" * 60)
