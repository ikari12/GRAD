#!/usr/bin/env python3
"""
09_dw_acf_sensitivity.py
========================
Sensitivity analysis for temporal autocorrelation in GACD regressions.

Samples ~300 workouts from the high-engagement subset, re-runs the GACD
OLS regression, and computes:
  1. Durbin-Watson (DW) statistic per workout
  2. Autocorrelation function (ACF) of residuals (lags 1–20)
  3. Newey-West HAC standard errors vs OLS standard errors
  4. Adjusted R² comparison (OLS R² vs effective R² accounting for autocorrelation)

Outputs:
  - paper/Figures/figS_dw.png   (DW distribution)
  - paper/Figures/figS_acf.png  (Mean ACF with CI)
  - results/sensitivity_autocorrelation.txt  (summary statistics)
"""

import os, json, csv, time, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

# ── Style (matching 05_figures.py) ──────────────────────────────────────────
for font in ["Helvetica", "Arial", "DejaVu Sans"]:
    try:
        matplotlib.font_manager.findfont(font, fallback_to_default=False)
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = [font]
        break
    except Exception:
        continue

plt.rcParams.update({
    "font.size": 10,
    "axes.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

ROOT = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(ROOT))
from lab_gcs import open_text as lab_open_text  # noqa: E402
DATA = ROOT / "data"
FIG_DIR = ROOT / "paper" / "Figures"
RES_DIR = ROOT / "results"
FIG_DIR.mkdir(parents=True, exist_ok=True)
RES_DIR.mkdir(parents=True, exist_ok=True)

JSON_PATH = DATA / "endomondoHR.json"
ABC_CSV = DATA / "abc_metrics.csv"

SAMPLE_N = 300
MAX_LAG = 20
np.random.seed(42)

# ── Load target IDs ─────────────────────────────────────────────────────────
abc_ids = set()
with open(ABC_CSV) as f:
    for r in csv.DictReader(f):
        abc_ids.add(r["id"])

# Sample
sampled_ids = set(np.random.choice(list(abc_ids), size=min(SAMPLE_N, len(abc_ids)), replace=False))
print(f"Sampled {len(sampled_ids)} workout IDs from {len(abc_ids)} total")

# ── Helper functions ────────────────────────────────────────────────────────
def durbin_watson(residuals):
    """Compute Durbin-Watson statistic."""
    diff = np.diff(residuals)
    return np.sum(diff**2) / np.sum(residuals**2)

def acf(residuals, max_lag):
    """Compute autocorrelation function for lags 1..max_lag."""
    n = len(residuals)
    mean = residuals.mean()
    denom = np.sum((residuals - mean)**2)
    if denom == 0:
        return np.zeros(max_lag)
    result = np.zeros(max_lag)
    for lag in range(1, max_lag + 1):
        if lag >= n:
            break
        numer = np.sum((residuals[lag:] - mean) * (residuals[:-lag] - mean))
        result[lag - 1] = numer / denom
    return result

def newey_west_se(X, residuals, max_lag=None):
    """
    Compute Newey-West HAC standard errors.
    
    Parameters
    ----------
    X : array (n, p) — design matrix
    residuals : array (n,) — OLS residuals
    max_lag : int — bandwidth (default: floor(4*(n/100)^(2/9)))
    
    Returns
    -------
    se_nw : array (p,) — Newey-West standard errors for each coefficient
    """
    n, p = X.shape
    if max_lag is None:
        max_lag = int(np.floor(4 * (n / 100) ** (2.0 / 9)))
    
    # S_0 = (1/n) * X' diag(e²) X
    XtX_inv = np.linalg.inv(X.T @ X)
    
    # Meat: Σ_0 + Σ_{j=1}^{L} w_j (Σ_j + Σ_j')
    # where Σ_j = Σ_t X_t X_{t-j}' e_t e_{t-j}
    e = residuals
    Xe = X * e[:, np.newaxis]  # (n, p) — each row is X_i * e_i
    
    # Σ_0
    S = Xe.T @ Xe  # (p, p)
    
    # Add lagged terms with Bartlett kernel weights
    for j in range(1, max_lag + 1):
        w = 1.0 - j / (max_lag + 1)  # Bartlett weight
        Gamma_j = Xe[j:].T @ Xe[:-j]  # (p, p)
        S += w * (Gamma_j + Gamma_j.T)
    
    # Variance-covariance: (X'X)^{-1} S (X'X)^{-1}
    V_nw = XtX_inv @ S @ XtX_inv
    se_nw = np.sqrt(np.diag(V_nw))
    return se_nw

def ols_se(X, residuals):
    """Compute standard OLS standard errors."""
    n, p = X.shape
    sigma2 = np.sum(residuals**2) / (n - p)
    XtX_inv = np.linalg.inv(X.T @ X)
    se = np.sqrt(sigma2 * np.diag(XtX_inv))
    return se

# ── Process workouts ────────────────────────────────────────────────────────
dw_values = []
acf_matrix = []  # each row = ACF for one workout
se_ratios = {"gradient": [], "time": [], "speed": []}  # NW/OLS ratio
beta_ols_all = {"gradient": [], "time": [], "speed": []}
# Paired coefficient/SE triples, retained so that OLS and HAC confidence
# intervals can be compared on exactly the same set of workouts.
se_ols_all = {"gradient": [], "time": [], "speed": []}
se_nw_all = {"gradient": [], "time": [], "speed": []}
beta_paired = {"gradient": [], "time": [], "speed": []}
beta_gls_all = {"gradient": [], "time": [], "speed": []}
beta_ols_for_gls = {"gradient": [], "time": [], "speed": []}
gls_rho_all = []
n_points_all = []
r2_ols_all = []

found = 0
t0 = time.time()

print(f"Streaming {JSON_PATH} (~6.5 GB from local or lab GCS)...")
with lab_open_text(JSON_PATH) as f:
    for line_num, line in enumerate(f, 1):
        if found >= len(sampled_ids):
            break
        
        line = line.strip()
        if not line or line in ('[', ']'):
            continue
        if line.endswith(','):
            line = line[:-1]
        if line.startswith(','):
            line = line[1:]
        if not line or line in ('[', ']'):
            continue
        
        try:
            rec = json.loads(line.replace("'", '"').replace('True','true').replace('False','false').replace('None','null'))
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(rec, dict):
            continue
        
        wid = str(rec.get("id", ""))
        if wid not in sampled_ids:
            continue
        
        # ── Reconstruct GACD regression (same as 00b_compute_abc.py) ────
        hr_raw = rec.get("heart_rate", [])
        alt_raw = rec.get("altitude", [])
        spd_raw = rec.get("speed", [])
        ts_raw = rec.get("timestamp", [])
        
        n = min(len(hr_raw), len(alt_raw), len(spd_raw), len(ts_raw))
        if n < 30:
            found += 1
            continue
        
        hr = np.array([h if isinstance(h, (int, float)) else np.nan for h in hr_raw[:n]], dtype=float)
        alt = np.array([a if isinstance(a, (int, float)) else np.nan for a in alt_raw[:n]], dtype=float)
        spd = np.array([s if isinstance(s, (int, float)) else np.nan for s in spd_raw[:n]], dtype=float)
        ts = np.array(ts_raw[:n], dtype=float)
        
        # Interpolate NaNs
        for arr in [hr, alt, spd]:
            nans = np.isnan(arr)
            if nans.any() and not nans.all():
                good = np.where(~nans)[0]
                arr[nans] = np.interp(np.where(nans)[0], good, arr[good])
            elif nans.all():
                found += 1
                continue
        
        t_min = (ts - ts[0]) / 60.0
        spd_ms = spd / 3.6
        
        dt = np.diff(ts)
        dt[dt < 0.1] = 0.1
        d_alt = np.diff(alt)
        d_dist = spd_ms[:-1] * dt
        d_dist[d_dist < 0.1] = 0.1
        gradient = np.clip((d_alt / d_dist) * 100.0, -50, 50)
        
        hr_mid = (hr[:-1] + hr[1:]) / 2
        t_mid = (t_min[:-1] + t_min[1:]) / 2
        spd_mid = (spd_ms[:-1] + spd_ms[1:]) / 2
        
        m = len(gradient)
        if m < 20:
            found += 1
            continue
        
        X = np.column_stack([np.ones(m), gradient, t_mid, spd_mid])
        valid = np.isfinite(X).all(axis=1) & np.isfinite(hr_mid)
        if valid.sum() < 20:
            found += 1
            continue
        
        X = X[valid]
        y = hr_mid[valid]
        
        try:
            beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        except Exception:
            found += 1
            continue
        
        residuals = y - X @ beta
        n_valid = len(residuals)
        
        # R²
        ss_res = np.sum(residuals**2)
        ss_tot = np.sum((y - y.mean())**2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        
        # DW
        dw = durbin_watson(residuals)
        dw_values.append(dw)
        
        # ACF
        acf_vals = acf(residuals, MAX_LAG)
        acf_matrix.append(acf_vals)
        
        # SE comparison
        try:
            se_ols = ols_se(X, residuals)
            se_nw = newey_west_se(X, residuals)
            # Ratios for gradient (idx 1), time (idx 2), speed (idx 3)
            for idx, name in [(1, "gradient"), (2, "time"), (3, "speed")]:
                if se_ols[idx] > 0:
                    se_ratios[name].append(se_nw[idx] / se_ols[idx])
                    se_ols_all[name].append(se_ols[idx])
                    se_nw_all[name].append(se_nw[idx])
                    beta_paired[name].append(beta[idx])
            beta_ols_all["gradient"].append(beta[1])
            beta_ols_all["time"].append(beta[2])
            beta_ols_all["speed"].append(beta[3])
            # Cochrane–Orcutt GLS under AR(1): transform y_t − ρ y_{t−1}
            # and compare point estimates to OLS on the same workout.
            rho = float(np.corrcoef(residuals[1:], residuals[:-1])[0, 1])
            if np.isfinite(rho) and abs(rho) < 0.999:
                y_star = y[1:] - rho * y[:-1]
                X_star = X[1:] - rho * X[:-1]
                beta_gls, _, _, _ = np.linalg.lstsq(X_star, y_star, rcond=None)
                beta_gls_all["gradient"].append(beta_gls[1])
                beta_gls_all["time"].append(beta_gls[2])
                beta_gls_all["speed"].append(beta_gls[3])
                beta_ols_for_gls["gradient"].append(beta[1])
                beta_ols_for_gls["time"].append(beta[2])
                beta_ols_for_gls["speed"].append(beta[3])
                gls_rho_all.append(rho)
        except Exception:
            pass
        
        n_points_all.append(n_valid)
        r2_ols_all.append(r2)
        
        found += 1
        if found % 50 == 0:
            elapsed = time.time() - t0
            print(f"  Processed {found}/{len(sampled_ids)} workouts ({elapsed:.0f}s)")

elapsed = time.time() - t0
print(f"\nDone: {found} workouts processed in {elapsed:.1f}s")

# ── Summary statistics ──────────────────────────────────────────────────────
dw_arr = np.array(dw_values)
acf_mat = np.array(acf_matrix)

# Compute effective degrees of freedom reduction
# For AR(1) with autocorrelation ρ, effective n ≈ n * (1-ρ)/(1+ρ)
lag1_acfs = acf_mat[:, 0]  # lag-1 ACF for each workout
eff_ratio = (1 - lag1_acfs) / (1 + lag1_acfs)  # n_eff / n

summary_lines = []
summary_lines.append("=" * 70)
summary_lines.append("SENSITIVITY ANALYSIS: Temporal Autocorrelation in GACD Regressions")
summary_lines.append("=" * 70)
summary_lines.append(f"Workouts analysed: {len(dw_values)}")
summary_lines.append(f"Median n_points per workout: {np.median(n_points_all):.0f} "
                     f"(IQR {np.percentile(n_points_all, 25):.0f}–{np.percentile(n_points_all, 75):.0f})")
summary_lines.append("")
summary_lines.append("--- Durbin-Watson Statistic ---")
summary_lines.append(f"  Median: {np.median(dw_arr):.3f}")
summary_lines.append(f"  Mean:   {np.mean(dw_arr):.3f}")
summary_lines.append(f"  SD:     {np.std(dw_arr):.3f}")
summary_lines.append(f"  IQR:    [{np.percentile(dw_arr, 25):.3f}, {np.percentile(dw_arr, 75):.3f}]")
summary_lines.append(f"  Range:  [{np.min(dw_arr):.3f}, {np.max(dw_arr):.3f}]")
summary_lines.append(f"  % with DW < 1.5 (strong positive AC): {100*np.mean(dw_arr < 1.5):.1f}%")
summary_lines.append(f"  % with 1.5 ≤ DW ≤ 2.5 (acceptable):  {100*np.mean((dw_arr >= 1.5) & (dw_arr <= 2.5)):.1f}%")
summary_lines.append(f"  % with DW > 2.5 (negative AC):        {100*np.mean(dw_arr > 2.5):.1f}%")
summary_lines.append("")
summary_lines.append("--- Lag-1 Autocorrelation ---")
summary_lines.append(f"  Median: {np.median(lag1_acfs):.3f}")
summary_lines.append(f"  Mean:   {np.mean(lag1_acfs):.3f}")
summary_lines.append(f"  IQR:    [{np.percentile(lag1_acfs, 25):.3f}, {np.percentile(lag1_acfs, 75):.3f}]")
summary_lines.append("")
summary_lines.append("--- Effective Degrees of Freedom Reduction (AR(1) approximation) ---")
summary_lines.append(f"  Median n_eff/n: {np.median(eff_ratio):.3f}")
summary_lines.append(f"  Mean n_eff/n:   {np.mean(eff_ratio):.3f}")
summary_lines.append(f"  → Median {(1-np.median(eff_ratio))*100:.0f}% reduction in effective sample size")
summary_lines.append("")
summary_lines.append("--- Newey-West / OLS Standard Error Ratio ---")
for name in ["gradient", "time", "speed"]:
    ratios = np.array(se_ratios[name])
    summary_lines.append(f"  β_{name:10s}: median ratio = {np.median(ratios):.2f}, "
                         f"mean = {np.mean(ratios):.2f}, "
                         f"IQR [{np.percentile(ratios, 25):.2f}, {np.percentile(ratios, 75):.2f}]")
summary_lines.append("")
printkey_lines = []
summary_lines.append("--- HAC-Corrected Inference (per-workout 95% CIs) ---")
summary_lines.append("  Median half-width of the 95% CI across workouts, and the share of")
summary_lines.append("  workouts whose coefficient remains significant at alpha = .05.")
for name in ["gradient", "time", "speed"]:
    b = np.array(beta_paired[name])
    s_ols = np.array(se_ols_all[name])
    s_nw = np.array(se_nw_all[name])
    hw_ols = 1.96 * s_ols
    hw_nw = 1.96 * s_nw
    sig_ols = 100.0 * np.mean(np.abs(b) > hw_ols)
    sig_nw = 100.0 * np.mean(np.abs(b) > hw_nw)
    summary_lines.append(
        f"  β_{name:10s}: median 95% CI half-width  OLS {np.median(hw_ols):.4f}"
        f"  ->  HAC {np.median(hw_nw):.4f}")
    summary_lines.append(
        f"  {'':12s}  significant at .05        OLS {sig_ols:.1f}%"
        f"  ->  HAC {sig_nw:.1f}%")
    summary_lines.append(
        f"  {'':12s}  median coefficient        {np.median(b):+.4f}"
        f"   [HAC 95% CI {np.median(b) - np.median(hw_nw):+.4f}, "
        f"{np.median(b) + np.median(hw_nw):+.4f}]")
    printkey_lines.append(f"[KEY] HAC_HW_OLS_{name.upper()} = {np.median(hw_ols):.4f}")
    printkey_lines.append(f"[KEY] HAC_HW_NW_{name.upper()} = {np.median(hw_nw):.4f}")
    printkey_lines.append(f"[KEY] HAC_SIG_OLS_{name.upper()} = {sig_ols:.1f}")
    printkey_lines.append(f"[KEY] HAC_SIG_NW_{name.upper()} = {sig_nw:.1f}")
summary_lines.append("")
summary_lines.append("--- Coefficient Point Estimates (confirm unbiased under autocorrelation) ---")
for name in ["gradient", "time", "speed"]:
    vals = np.array(beta_ols_all[name])
    summary_lines.append(f"  β_{name:10s}: mean = {np.mean(vals):.4f}, "
                         f"median = {np.median(vals):.4f}, SD = {np.std(vals):.4f}")
summary_lines.append("")
summary_lines.append("--- OLS R² ---")
r2_arr = np.array(r2_ols_all)
summary_lines.append(f"  Median: {np.median(r2_arr):.3f}")
summary_lines.append(f"  IQR:    [{np.percentile(r2_arr, 25):.3f}, {np.percentile(r2_arr, 75):.3f}]")
summary_lines.append("")
summary_lines.append("--- Cochrane-Orcutt GLS vs OLS (AR(1) subsample) ---")
summary_lines.append(f"  Workouts with GLS fit: {len(gls_rho_all)}")
if gls_rho_all:
    summary_lines.append(f"  Median AR(1) rho used in GLS: {np.median(gls_rho_all):.3f}")
    printkey_lines.append(f"[KEY] GLS_N = {len(gls_rho_all)}")
    printkey_lines.append(f"[KEY] GLS_RHO_MEDIAN = {np.median(gls_rho_all):.3f}")
    for name in ["gradient", "time", "speed"]:
        ols_b = np.array(beta_ols_for_gls[name])
        gls_b = np.array(beta_gls_all[name])
        r = np.corrcoef(ols_b, gls_b)[0, 1]
        med_abs_diff = np.median(np.abs(gls_b - ols_b))
        med_rel = np.median(np.abs(gls_b - ols_b) / np.maximum(np.abs(ols_b), 1e-8))
        summary_lines.append(
            f"  β_{name:10s}: r(OLS,GLS) = {r:.3f}   "
            f"median |GLS-OLS| = {med_abs_diff:.4f}   "
            f"median relative |diff| = {100*med_rel:.1f}%")
        summary_lines.append(
            f"  {'':12s}  median OLS {np.median(ols_b):+.4f}   median GLS {np.median(gls_b):+.4f}")
        printkey_lines.append(f"[KEY] GLS_R_{name.upper()} = {r:.3f}")
        printkey_lines.append(f"[KEY] GLS_MED_ABS_DIFF_{name.upper()} = {med_abs_diff:.4f}")
        printkey_lines.append(f"[KEY] GLS_MED_REL_PCT_{name.upper()} = {100*med_rel:.1f}")
summary_lines.append("")

# Effective R² accounting for autocorrelation
# R²_eff ≈ 1 - (1-R²) * (n_eff_ratio)^{-1}  ... this is a rough approximation
# More precisely: the F-stat is deflated by the effective df ratio
summary_lines.append("[KEY] DW_MEDIAN = " + f"{np.median(dw_arr):.3f}")
summary_lines.append("[KEY] DW_IQR_LO = " + f"{np.percentile(dw_arr, 25):.3f}")
summary_lines.append("[KEY] DW_IQR_HI = " + f"{np.percentile(dw_arr, 75):.3f}")
summary_lines.append("[KEY] LAG1_MEDIAN = " + f"{np.median(lag1_acfs):.3f}")
summary_lines.append("[KEY] LAG1_IQR_LO = " + f"{np.percentile(lag1_acfs, 25):.3f}")
summary_lines.append("[KEY] LAG1_IQR_HI = " + f"{np.percentile(lag1_acfs, 75):.3f}")
summary_lines.append("[KEY] SE_RATIO_GRAD = " + f"{np.median(np.array(se_ratios['gradient'])):.2f}")
summary_lines.append("[KEY] SE_RATIO_TIME = " + f"{np.median(np.array(se_ratios['time'])):.2f}")
summary_lines.append("[KEY] SE_RATIO_SPEED = " + f"{np.median(np.array(se_ratios['speed'])):.2f}")
summary_lines.append("[KEY] NEFF_RATIO = " + f"{np.median(eff_ratio):.3f}")
summary_lines.append("[KEY] PCT_DW_BELOW_1_5 = " + f"{100*np.mean(dw_arr < 1.5):.1f}")
summary_lines.append("[KEY] N_WORKOUTS = " + f"{len(dw_values)}")
summary_lines.extend(printkey_lines)

summary_text = "\n".join(summary_lines)
print("\n" + summary_text)

out_txt = RES_DIR / "sensitivity_autocorrelation.txt"
with open(out_txt, "w") as f:
    f.write(summary_text)
print(f"\nSummary saved: {out_txt}")

# ── Figure S2a: Durbin-Watson histogram ──────────────────────────────────────
fig1, ax1 = plt.subplots(figsize=(5, 3.8))

ax1.hist(dw_arr, bins=40, color="#2166AC", alpha=0.7, edgecolor="white", linewidth=0.5)
ax1.axvline(x=2.0, color="#E63946", linestyle="--", linewidth=1.2, label="DW = 2.0 (no AC)")
ax1.axvline(x=np.median(dw_arr), color="#F4A261", linestyle="-", linewidth=1.5,
            label=f"Median = {np.median(dw_arr):.2f}")
ax1.set_xlabel("Durbin-Watson Statistic", fontsize=11)
ax1.set_ylabel("Count", fontsize=11)
ax1.set_title("Durbin-Watson Distribution", fontsize=12, fontweight="bold")
ax1.legend(fontsize=8, frameon=False)
# Shade strong AC region
ax1.axvspan(0, 1.5, color="#E63946", alpha=0.08)
ax1.text(0.75, ax1.get_ylim()[1] * 0.85, "Strong\npositive AC",
         ha="center", fontsize=7, color="#E63946", fontstyle="italic")

fig1.tight_layout()
out_fig1 = FIG_DIR / "figS_dw.png"
fig1.savefig(out_fig1, dpi=300)
print(f"Figure saved: {out_fig1}")
plt.close(fig1)

# ── Figure S2b: Mean ACF with CI ─────────────────────────────────────────────
fig2, ax2 = plt.subplots(figsize=(5, 3.8))

mean_acf = acf_mat.mean(axis=0)
std_acf = acf_mat.std(axis=0)
lags = np.arange(1, MAX_LAG + 1)

# 95% CI for mean ACF
ci = 1.96 * std_acf / np.sqrt(len(acf_mat))

ax2.bar(lags, mean_acf, width=0.7, color="#2166AC", alpha=0.7, edgecolor="white", linewidth=0.5)
ax2.errorbar(lags, mean_acf, yerr=ci, fmt="none", ecolor="#333333", elinewidth=0.8, capsize=2)

# Significance threshold for individual ACF: ±1.96/√(median_n)
median_n = np.median(n_points_all)
sig_threshold = 1.96 / np.sqrt(median_n)
ax2.axhline(y=sig_threshold, color="#888888", linestyle=":", linewidth=0.8,
            label=f"±1.96/√n (n={median_n:.0f})")
ax2.axhline(y=-sig_threshold, color="#888888", linestyle=":", linewidth=0.8)
ax2.axhline(y=0, color="black", linewidth=0.5)

ax2.set_xlabel("Lag", fontsize=11)
ax2.set_ylabel("Mean ACF", fontsize=11)
ax2.set_title("Mean Autocorrelation of GACD Residuals", fontsize=12, fontweight="bold")
ax2.set_xlim(0.3, MAX_LAG + 0.7)
ax2.legend(fontsize=8, frameon=False, loc="upper right")

# Annotate lag-1
ax2.annotate(f"ρ₁ = {mean_acf[0]:.2f}",
             xy=(1, mean_acf[0]), xytext=(4, mean_acf[0] + 0.05),
             fontsize=9, fontweight="bold", color="#D95F02",
             arrowprops=dict(arrowstyle="->", color="#D95F02", lw=1.2))

fig2.tight_layout()
out_fig2 = FIG_DIR / "figS_acf.png"
fig2.savefig(out_fig2, dpi=300)
print(f"Figure saved: {out_fig2}")
plt.close(fig2)

print("\n✓ Sensitivity analysis complete.")
