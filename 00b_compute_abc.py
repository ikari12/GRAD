"""Compute A/B/C Novel Endurance Metrics from FitRec Raw Data
A. GACD (Gradient-Adjusted Cardiac Drift) — true physiological decoupling
B. Personal HR-Terrain Response — gradient sensitivity coefficient
C. Recovery Dynamics — HR recovery speed decay across workout

Streams endomondoHR.json, outputs abc_metrics.csv
"""
import os, json, csv, time, sys
import numpy as np
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
JSON_PATH = os.path.join(DATA_DIR, "endomondoHR.json")
IDX_CSV = os.path.join(DATA_DIR, "meixner_4d_indices.csv")
OUT_CSV = os.path.join(DATA_DIR, "abc_metrics.csv")

# Load target IDs and metadata
target_meta = {}
with open(IDX_CSV) as f:
    for r in csv.DictReader(f):
        target_meta[r['id']] = {'sport': r['sport'],
            'alt_range': float(r.get('alt_range','0') or 0)}
target_ids = set(target_meta.keys())
print(f"Target IDs: {len(target_ids):,}")

def safe_gradient(alt, dist_m):
    """Compute gradient (%) from altitude diff and horizontal distance."""
    if dist_m < 1: return 0.0
    return (alt / dist_m) * 100.0

def compute_metrics(rec):
    """Compute A/B/C metrics for a single workout."""
    hr_raw = rec.get('heart_rate', [])
    alt_raw = rec.get('altitude', [])
    spd_raw = rec.get('speed', [])
    ts_raw = rec.get('timestamp', [])
    lat_raw = rec.get('latitude', [])
    lon_raw = rec.get('longitude', [])

    n = min(len(hr_raw), len(alt_raw), len(spd_raw), len(ts_raw))
    if n < 30: return None

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
            return None

    # Time in minutes from start
    t_min = (ts - ts[0]) / 60.0
    dur_min = t_min[-1]
    if dur_min < 5: return None

    # Compute point-to-point gradient
    dt = np.diff(ts)
    dt[dt < 0.1] = 0.1
    d_alt = np.diff(alt)
    d_dist = spd[:-1] * dt  # horizontal distance in meters (speed is m/s)
    d_dist[d_dist < 0.1] = 0.1
    gradient = (d_alt / d_dist) * 100.0  # percent
    gradient = np.clip(gradient, -50, 50)  # reasonable range

    # Align arrays (n-1 points for gradient)
    hr_mid = (hr[:-1] + hr[1:]) / 2  # midpoint HR
    t_mid = (t_min[:-1] + t_min[1:]) / 2  # midpoint time
    spd_mid = (spd[:-1] + spd[1:]) / 2
    alt_mid = (alt[:-1] + alt[1:]) / 2

    m = len(gradient)
    if m < 20: return None

    # ================================================================
    # A. GACD (Gradient-Adjusted Cardiac Drift)
    # Linear model: HR ~ gradient + time_elapsed
    # GACD = coefficient on time_elapsed (bpm per minute)
    # ================================================================
    # Multiple regression: HR = b0 + b1*gradient + b2*time + b3*speed
    X_a = np.column_stack([
        np.ones(m),
        gradient,
        t_mid,
        spd_mid,
    ])
    # Filter valid
    valid = np.isfinite(X_a).all(axis=1) & np.isfinite(hr_mid)
    if valid.sum() < 20: return None
    X_a = X_a[valid]; y_a = hr_mid[valid]

    try:
        beta, res, rank, sv = np.linalg.lstsq(X_a, y_a, rcond=None)
    except:
        return None

    gacd_rate = beta[2]  # bpm per minute of elapsed time (after controlling for gradient+speed)
    gacd_gradient_coef = beta[1]  # HR response to gradient (bpm per 1% gradient)
    gacd_speed_coef = beta[3]
    gacd_intercept = beta[0]

    # R² of the gradient+speed+time model
    y_pred = X_a @ beta
    ss_res = np.sum((y_a - y_pred)**2)
    ss_tot = np.sum((y_a - y_a.mean())**2)
    gacd_r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    # Also compute residual variance (how much HR is NOT explained)
    gacd_residual_std = np.sqrt(ss_res / len(y_a)) if len(y_a) > 4 else 0

    # Compare first-half vs second-half residuals (residual drift)
    residuals = y_a - y_pred
    half = len(residuals) // 2
    resid_h1 = residuals[:half].mean()
    resid_h2 = residuals[half:].mean()
    gacd_resid_drift = resid_h2 - resid_h1  # positive = unexplained HR increase in 2nd half

    # ================================================================
    # B. Personal HR-Terrain Response Coefficients
    # Stored per-workout for later aggregation at user level
    # b1 = gradient sensitivity, b3 = speed sensitivity
    # ================================================================
    hr_gradient_sensitivity = gacd_gradient_coef
    hr_speed_sensitivity = gacd_speed_coef
    hr_time_sensitivity = gacd_rate  # same as GACD

    # Also: segment-level analysis
    # Divide workout into 5 equal segments, compute mean HR and mean gradient
    seg_n = 5
    seg_len = m // seg_n
    seg_hr = []; seg_grad = []
    for s in range(seg_n):
        si = s * seg_len; ei = (s+1) * seg_len if s < seg_n-1 else m
        seg_hr.append(hr_mid[si:ei].mean())
        seg_grad.append(gradient[si:ei].mean())

    # HR increase not explained by gradient change across segments
    if seg_n >= 3:
        # Gradient-adjusted HR progression
        adj_hr = [seg_hr[i] - gacd_gradient_coef * seg_grad[i] for i in range(seg_n)]
        hr_progression = adj_hr[-1] - adj_hr[0]  # total gradient-adjusted HR drift
    else:
        hr_progression = 0

    # ================================================================
    # C. Recovery Dynamics
    # Find descent segments, measure HR recovery speed
    # Compare early vs late recovery
    # ================================================================
    # Identify descent segments: gradient < -3% for ≥ 5 consecutive points
    descents = []
    in_descent = False; d_start = 0
    for i in range(m):
        if gradient[i] < -3:
            if not in_descent: d_start = i; in_descent = True
        else:
            if in_descent and i - d_start >= 5:
                descents.append((d_start, i))
            in_descent = False
    if in_descent and m - d_start >= 5:
        descents.append((d_start, m))

    recovery_speeds = []  # bpm/min of recovery during each descent
    recovery_times = []   # time position (fraction of workout)

    for d_s, d_e in descents:
        hr_seg = hr_mid[d_s:d_e]
        t_seg = t_mid[d_s:d_e]
        if len(hr_seg) < 5: continue

        # HR at start of descent (peak) vs end (trough)
        hr_peak = hr_seg[0]
        hr_min = hr_seg.min()
        hr_drop = hr_peak - hr_min
        t_drop = t_seg[t_seg <= t_seg[hr_seg.argmin()]][-1] - t_seg[0] if hr_seg.argmin() > 0 else 0

        if t_drop > 0.5 and hr_drop > 3:  # at least 30s and 3bpm drop
            rec_speed = hr_drop / t_drop  # bpm per minute
            recovery_speeds.append(rec_speed)
            recovery_times.append(t_mid[d_s] / dur_min)  # fraction of workout

    n_descents = len(recovery_speeds)
    if n_descents >= 2:
        # Split into early and late
        mid_idx = n_descents // 2
        early_rec = np.mean(recovery_speeds[:mid_idx])
        late_rec = np.mean(recovery_speeds[mid_idx:])
        recovery_decay = late_rec / early_rec if early_rec > 0.1 else 1.0
        avg_recovery_speed = np.mean(recovery_speeds)

        # Linear trend of recovery speed over workout
        if n_descents >= 3:
            slope, intercept = np.polyfit(recovery_times, recovery_speeds, 1)
            recovery_trend = slope  # negative = recovery slowing down
        else:
            recovery_trend = (recovery_speeds[-1] - recovery_speeds[0])
    elif n_descents == 1:
        recovery_decay = np.nan
        avg_recovery_speed = recovery_speeds[0]
        recovery_trend = np.nan
    else:
        recovery_decay = np.nan
        avg_recovery_speed = np.nan
        recovery_trend = np.nan

    # ================================================================
    # Route features (for ML later)
    # ================================================================
    total_asc = np.sum(d_alt[d_alt > 0])
    total_desc = np.abs(np.sum(d_alt[d_alt < 0]))
    alt_range_v = alt.max() - alt.min()

    # Gradient distribution
    grad_mean = gradient.mean()
    grad_std = gradient.std()
    pct_climb = np.mean(gradient > 3) * 100
    pct_desc = np.mean(gradient < -3) * 100
    pct_flat = np.mean(np.abs(gradient) <= 3) * 100

    # Terrain asymmetry (first half vs second half)
    h = m // 2
    asc_h1 = np.sum(d_alt[:h][d_alt[:h] > 0])
    asc_h2 = np.sum(d_alt[h:][d_alt[h:] > 0])
    asc_front = asc_h1 / (asc_h1 + asc_h2) if (asc_h1 + asc_h2) > 0 else 0.5
    desc_h1 = np.abs(np.sum(d_alt[:h][d_alt[:h] < 0]))
    desc_h2 = np.abs(np.sum(d_alt[h:][d_alt[h:] < 0]))
    desc_front = desc_h1 / (desc_h1 + desc_h2) if (desc_h1 + desc_h2) > 0 else 0.5

    return {
        'id': str(rec.get('id', '')),
        'userId': str(rec.get('userId', '')),
        'sport': target_meta.get(str(rec.get('id','')), {}).get('sport', ''),
        'alt_range': alt_range_v,
        'dur_min': dur_min,
        'n_points': n,
        # A: GACD
        'gacd_rate': gacd_rate,              # bpm/min drift after gradient control
        'gacd_gradient_coef': gacd_gradient_coef,  # HR per 1% gradient
        'gacd_speed_coef': gacd_speed_coef,
        'gacd_r2': gacd_r2,                  # model fit
        'gacd_residual_std': gacd_residual_std,
        'gacd_resid_drift': gacd_resid_drift,  # unexplained H2-H1 drift
        'hr_progression': hr_progression,      # total gradient-adjusted HR drift
        # B: Personal response
        'hr_gradient_sensitivity': hr_gradient_sensitivity,
        'hr_speed_sensitivity': hr_speed_sensitivity,
        'hr_time_sensitivity': hr_time_sensitivity,
        # C: Recovery dynamics
        'n_descents': n_descents,
        'avg_recovery_speed': avg_recovery_speed,
        'recovery_decay': recovery_decay,       # late/early recovery ratio (<1 = fatiguing)
        'recovery_trend': recovery_trend,        # slope of recovery speed over time
        # Route features (for ML)
        'total_ascent': total_asc,
        'total_descent': total_desc,
        'avg_hr': hr.mean(),
        'max_hr': hr.max(),
        'avg_speed': spd.mean(),
        'grad_mean': grad_mean,
        'grad_std': grad_std,
        'pct_climb': pct_climb,
        'pct_desc': pct_desc,
        'pct_flat': pct_flat,
        'asc_front': asc_front,
        'desc_front': desc_front,
        'max_alt': alt.max(),
        'min_alt': alt.min(),
    }

# ================================================================
# Stream and process
# ================================================================
t0 = time.time()
results = []
total = 0; matched = 0

with open(JSON_PATH) as f:
    for line in f:
        line = line.strip()
        if not line or line in ('[', ']'): continue
        if line.endswith(','): line = line[:-1]
        if line.startswith(','): line = line[1:]
        if not line or line in ('[', ']'): continue
        try:
            rec = json.loads(line.replace("'", '"').replace('True','true').replace('False','false').replace('None','null'))
        except: continue
        if not isinstance(rec, dict): continue
        total += 1

        wid = str(rec.get('id', ''))
        if wid not in target_ids: continue

        metrics = compute_metrics(rec)
        if metrics is None: continue

        results.append(metrics)
        matched += 1

        if matched % 500 == 0:
            print(f"  {matched:,} processed ({total:,} scanned, {time.time()-t0:.0f}s)", flush=True)

print(f"\nDone: {total:,} scanned → {matched:,} matched ({time.time()-t0:.0f}s)")

# Save
if results:
    keys = results[0].keys()
    with open(OUT_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(results)
    print(f"Saved: {OUT_CSV}")

    # Quick summary
    print(f"\n{'='*60}")
    print("METRIC SUMMARY")
    print(f"{'='*60}")
    for key in ['gacd_rate', 'gacd_gradient_coef', 'gacd_r2', 'gacd_resid_drift',
                'hr_progression', 'hr_gradient_sensitivity', 'hr_speed_sensitivity',
                'n_descents', 'avg_recovery_speed', 'recovery_decay', 'recovery_trend']:
        vals = [r[key] for r in results if r[key] is not None and not np.isnan(r[key])]
        if vals:
            print(f"  {key:30s}: n={len(vals):,}  mean={np.mean(vals):+.4f}  std={np.std(vals):.4f}  "
                  f"[{np.percentile(vals,5):+.3f}, {np.percentile(vals,95):+.3f}]")
