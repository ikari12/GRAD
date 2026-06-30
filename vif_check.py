"""Compute VIF (Variance Inflation Factor) for the GACD OLS regression.

Samples workouts and computes per-workout VIF for gradient, speed, time.
Reports median, IQR, and % of workouts with VIF < 10.

Usage: python vif_check.py
"""
import os, json, csv, sys, ast
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
JSON_PATH = os.path.join(DATA_DIR, "endomondoHR.json")
IDX_CSV = os.path.join(DATA_DIR, "meixner_4d_indices.csv")

# Load target IDs
target_ids = set()
with open(IDX_CSV) as f:
    for r in csv.DictReader(f):
        target_ids.add(r['id'])
print(f"Target IDs: {len(target_ids):,}")

def compute_vif_for_workout(rec):
    """Compute VIF for [gradient, time, speed] in a single workout."""
    hr_raw = rec.get('heart_rate', [])
    alt_raw = rec.get('altitude', [])
    spd_raw = rec.get('speed', [])
    ts_raw = rec.get('timestamp', [])

    n = min(len(hr_raw), len(alt_raw), len(spd_raw), len(ts_raw))
    if n < 30: return None

    hr = np.array([h if isinstance(h, (int, float)) else np.nan for h in hr_raw[:n]], dtype=float)
    alt = np.array([a if isinstance(a, (int, float)) else np.nan for a in alt_raw[:n]], dtype=float)
    spd = np.array([s if isinstance(s, (int, float)) else np.nan for s in spd_raw[:n]], dtype=float)
    ts = np.array(ts_raw[:n], dtype=float)

    # Interpolate NaNs
    for arr in [hr, alt, spd]:
        nans = np.isnan(arr)
        if nans.all(): return None
        if nans.any():
            idx = np.arange(len(arr))
            arr[nans] = np.interp(idx[nans], idx[~nans], arr[~nans])

    # Convert speed to m/s (raw is km/h)
    spd = spd / 3.6

    # Time in minutes
    t_min = (ts - ts[0]) / 60.0

    # Duration filter
    duration_min = t_min[-1] - t_min[0]
    if duration_min < 90: return None

    # Altitude range filter
    alt_range = np.nanmax(alt) - np.nanmin(alt)
    if alt_range < 200: return None

    # Compute gradient
    dt = np.diff(ts)
    dt = np.maximum(dt, 0.1)
    dist = np.maximum(spd[:-1] * dt, 0.1)
    gradient = np.clip(100 * np.diff(alt) / dist, -50, 50)

    # Midpoints
    hr_mid = (hr[:-1] + hr[1:]) / 2
    t_mid = (t_min[:-1] + t_min[1:]) / 2
    spd_mid = (spd[:-1] + spd[1:]) / 2

    m = len(gradient)
    if m < 20: return None

    # Design matrix (without intercept for VIF)
    X = np.column_stack([gradient, t_mid, spd_mid])

    valid = np.isfinite(X).all(axis=1) & np.isfinite(hr_mid)
    if valid.sum() < 20: return None
    X = X[valid]

    # VIF = 1 / (1 - R²_j) where R²_j is from regressing x_j on the other predictors
    n_vars = X.shape[1]
    vifs = []
    for j in range(n_vars):
        y_j = X[:, j]
        X_j = np.column_stack([np.ones(len(y_j)), np.delete(X, j, axis=1)])
        try:
            beta, _, _, _ = np.linalg.lstsq(X_j, y_j, rcond=None)
            y_pred = X_j @ beta
            ss_res = np.sum((y_j - y_pred)**2)
            ss_tot = np.sum((y_j - y_j.mean())**2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
            vif = 1 / (1 - r2) if r2 < 1 else 999
        except:
            vif = np.nan
        vifs.append(vif)

    return vifs  # [VIF_gradient, VIF_time, VIF_speed]


# Stream through JSON and compute VIF for each target workout
vif_results = []
count = 0
with open(JSON_PATH) as f:
    for line in f:
        rec = ast.literal_eval(line)
        wid = str(rec.get('id', ''))
        if wid not in target_ids:
            continue
        result = compute_vif_for_workout(rec)
        if result is not None:
            vif_results.append(result)
            count += 1
            if count % 2000 == 0:
                print(f"  Processed {count:,} workouts...")

vif_arr = np.array(vif_results)
labels = ['Gradient', 'Time', 'Speed']

print(f"\n{'='*60}")
print(f"VIF Analysis: {len(vif_results):,} workouts")
print(f"{'='*60}")
print(f"{'Variable':<12} {'Median':>8} {'P25':>8} {'P75':>8} {'Max':>8} {'%<10':>8}")
print(f"{'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
for j, label in enumerate(labels):
    col = vif_arr[:, j]
    med = np.median(col)
    p25 = np.percentile(col, 25)
    p75 = np.percentile(col, 75)
    mx = np.max(col)
    pct_ok = 100 * np.mean(col < 10)
    print(f"{label:<12} {med:8.2f} {p25:8.2f} {p75:8.2f} {mx:8.2f} {pct_ok:7.1f}%")

# Max VIF per workout
max_vif = np.max(vif_arr, axis=1)
print(f"\nMax VIF per workout:")
print(f"  Median: {np.median(max_vif):.2f}")
print(f"  P25-P75: [{np.percentile(max_vif, 25):.2f}, {np.percentile(max_vif, 75):.2f}]")
print(f"  % workouts with all VIF < 5: {100*np.mean(max_vif < 5):.1f}%")
print(f"  % workouts with all VIF < 10: {100*np.mean(max_vif < 10):.1f}%")
