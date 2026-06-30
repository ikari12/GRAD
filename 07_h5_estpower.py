"""Experiment: DI/EstimatedPower vs DI/Speed
Test H5: Does using estimated power (speed × Minetti cost) as the DI denominator
reduce route artifact compared to raw speed?

Stable commit: 9ddc7c2
"""
import os, json, math, time
import numpy as np
from collections import Counter
from scipy import stats

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(SCRIPT_DIR, "data", "endomondoHR.json")
OUT  = os.path.join(SCRIPT_DIR, "results", "h5_estimated_power.txt")

# ── Minetti (2002) metabolic cost table ──
# gradient (%) → cost (J/kg/m)
MINETTI_TABLE = [
    (-45, 3.50), (-40, 2.40), (-35, 1.80), (-30, 1.40), (-25, 1.10),
    (-20, 0.95), (-15, 0.80), (-10, 0.70), (-8, 0.65),  (-5, 0.50),
    (-3, 0.40),  (0, 1.60),   (3, 2.50),   (5, 3.50),   (8, 5.00),
    (10, 6.00),  (15, 8.00),  (20, 10.50), (25, 13.00),  (30, 16.00),
    (35, 20.00), (40, 25.00), (45, 30.00)
]
_GRAD = [g for g, c in MINETTI_TABLE]
_COST = [c for g, c in MINETTI_TABLE]

def minetti_cost(gradient_pct):
    """Interpolate Minetti cost for a given gradient (%)."""
    g = np.clip(gradient_pct, -45, 45)
    return np.interp(g, _GRAD, _COST)

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def clean_array(raw, min_len=10):
    if not isinstance(raw, list) or len(raw) < min_len:
        return None
    arr = np.array([x if x is not None and isinstance(x, (int,float)) else np.nan
                    for x in raw], dtype=float)
    valid = ~np.isnan(arr)
    if valid.sum() < min_len:
        return None
    if np.isnan(arr).any():
        arr[~valid] = np.interp(np.where(~valid)[0], np.where(valid)[0], arr[valid])
    return arr

def derive_speed(lat_arr, lon_arr, ts_arr):
    n = min(len(lat_arr), len(lon_arr), len(ts_arr))
    if n < 10:
        return None
    speeds = [0.0]
    for i in range(1, n):
        la1, lo1, la2, lo2 = lat_arr[i-1], lon_arr[i-1], lat_arr[i], lon_arr[i]
        dt = ts_arr[i] - ts_arr[i-1]
        if (la1 is None or la2 is None or lo1 is None or lo2 is None or
            not isinstance(la1, (int,float)) or not isinstance(la2, (int,float)) or
            not isinstance(lo1, (int,float)) or not isinstance(lo2, (int,float))):
            speeds.append(speeds[-1]); continue
        if dt <= 0:
            speeds.append(speeds[-1]); continue
        dist = haversine(la1, lo1, la2, lo2)
        spd_kmh = (dist / dt) * 3.6
        speeds.append(spd_kmh if spd_kmh <= 150 else speeds[-1])
    return np.array(speeds, dtype=float)


def compute_gradient(alt, spd_kmh, ts):
    """Compute gradient (%) from altitude and horizontal distance."""
    dt = np.diff(ts)
    dt[dt <= 0] = 1
    # horizontal distance in meters per interval
    spd_ms = spd_kmh[:-1] / 3.6
    dx = spd_ms * dt
    dx[np.abs(dx) < 0.5] = 0.5  # avoid division by zero
    dy = np.diff(alt)
    grad = np.clip((dy / dx) * 100, -50, 50)
    grad = np.append(grad, grad[-1])  # pad to same length
    return grad


def compute_estimated_power(spd_kmh, gradient_pct):
    """Estimated metabolic power = speed(m/s) × Minetti_cost(gradient).
    Units: W/kg equivalent (J/kg/s)."""
    spd_ms = spd_kmh / 3.6
    cost = minetti_cost(gradient_pct)  # J/kg/m
    return spd_ms * cost  # J/kg/s = W/kg


def main():
    print("=" * 60)
    print("H5 Experiment: DI/EstimatedPower vs DI/Speed")
    print("=" * 60)

    records = []
    total = 0
    skip = Counter()
    t0 = time.time()

    with open(DATA, 'r') as f:
        for ln, line in enumerate(f):
            line = line.strip()
            if not line or line in ('[', ']'): continue
            if line.endswith(','): line = line[:-1]
            if line.startswith(','): line = line[1:]
            line = line.strip()
            if not line or line in ('[', ']'): continue
            try:
                fixed = line.replace("'", '"').replace('True','true').replace('False','false').replace('None','null')
                rec = json.loads(fixed)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(rec, dict): continue
            total += 1

            hr = clean_array(rec.get('heart_rate', []))
            if hr is None: skip['no_hr'] += 1; continue

            alt = clean_array(rec.get('altitude', []))
            if alt is None: skip['no_alt'] += 1; continue

            ts_raw = rec.get('timestamp', [])
            if not isinstance(ts_raw, list) or len(ts_raw) < 10:
                skip['no_ts'] += 1; continue
            ts = np.array(ts_raw, dtype=float)

            dur_min = (ts[-1] - ts[0]) / 60.0
            if dur_min <= 90: skip['short'] += 1; continue

            alt_range = float(np.max(alt) - np.min(alt))
            if alt_range <= 200: skip['flat'] += 1; continue

            spd = clean_array(rec.get('speed', []))
            if spd is None or len(spd) < 10:
                spd = derive_speed(
                    rec.get('latitude', []),
                    rec.get('longitude', []),
                    ts_raw
                )
            if spd is None or len(spd) < 10:
                skip['no_spd'] += 1; continue

            # Align
            n = min(len(hr), len(alt), len(ts), len(spd))
            if n < 30: skip['too_few'] += 1; continue
            hr, alt, ts, spd = hr[:n], alt[:n], ts[:n], spd[:n]

            spd_pos = spd > 0.5
            if spd_pos.sum() < 20: skip['no_move'] += 1; continue

            # Compute gradient
            gradient = compute_gradient(alt, spd, ts)

            # Compute estimated power
            est_power = compute_estimated_power(spd, gradient)

            mid = n // 2

            # ── DI/Speed ──
            m1s = spd_pos[:mid]; m2s = spd_pos[mid:]
            if m1s.sum() < 5 or m2s.sum() < 5: skip['halves'] += 1; continue
            r1_spd = np.mean(hr[:mid][m1s]) / np.mean(spd[:mid][m1s])
            r2_spd = np.mean(hr[mid:][m2s]) / np.mean(spd[mid:][m2s])
            di_speed = r2_spd / r1_spd if r1_spd > 0 else np.nan

            # ── DI/EstPower ──
            ep = est_power.copy()
            ep_pos = ep > 0.01
            valid_mask = spd_pos & ep_pos
            m1p = valid_mask[:mid]; m2p = valid_mask[mid:]
            if m1p.sum() < 5 or m2p.sum() < 5: skip['ep_halves'] += 1; continue
            r1_ep = np.mean(hr[:mid][m1p]) / np.mean(ep[:mid][m1p])
            r2_ep = np.mean(hr[mid:][m2p]) / np.mean(ep[mid:][m2p])
            di_estpower = r2_ep / r1_ep if r1_ep > 0 else np.nan

            if np.isnan(di_speed) or np.isnan(di_estpower): continue

            # Route features
            total_asc = float(np.sum(np.maximum(np.diff(alt), 0)))
            total_desc = float(np.sum(np.minimum(np.diff(alt), 0)))
            mean_grad_h1 = float(np.mean(gradient[:mid]))
            mean_grad_h2 = float(np.mean(gradient[mid:]))
            grad_asymmetry = mean_grad_h2 - mean_grad_h1

            uid = str(rec.get('userId', rec.get('id', ln)))
            sport = str(rec.get('sport', 'unknown'))

            records.append({
                'uid': uid,
                'sport': sport,
                'di_speed': di_speed,
                'di_estpower': di_estpower,
                'alt_range': alt_range,
                'total_asc': total_asc,
                'total_desc': total_desc,
                'mean_grad_h1': mean_grad_h1,
                'mean_grad_h2': mean_grad_h2,
                'grad_asymmetry': grad_asymmetry,
                'dur_min': dur_min,
            })

            if total % 50000 == 0:
                print(f"  processed {total:,} lines, kept {len(records):,} ...")

    elapsed = time.time() - t0
    print(f"\nTotal lines: {total:,}, kept: {len(records):,}, time: {elapsed:.0f}s")
    print(f"Skip reasons: {dict(skip)}")

    if len(records) < 100:
        print("ERROR: too few records for analysis")
        return

    # ── Analysis ──
    di_s = np.array([r['di_speed'] for r in records])
    di_p = np.array([r['di_estpower'] for r in records])
    asym = np.array([r['grad_asymmetry'] for r in records])
    alt_r = np.array([r['alt_range'] for r in records])

    # Clip outliers (1st-99th percentile)
    for arr_name, arr in [('di_speed', di_s), ('di_estpower', di_p)]:
        p1, p99 = np.percentile(arr, [1, 99])
        mask = (arr >= p1) & (arr <= p99)
        print(f"  {arr_name}: clipped {(~mask).sum()} outliers")

    # Use common valid mask
    p1s, p99s = np.percentile(di_s, [1, 99])
    p1p, p99p = np.percentile(di_p, [1, 99])
    valid = ((di_s >= p1s) & (di_s <= p99s) &
             (di_p >= p1p) & (di_p <= p99p) &
             np.isfinite(asym))
    di_s_v = di_s[valid]
    di_p_v = di_p[valid]
    asym_v = asym[valid]
    alt_v = alt_r[valid]

    print(f"\n{'='*60}")
    print(f"RESULTS (N = {valid.sum():,})")
    print(f"{'='*60}")

    # 1. Correlation with gradient asymmetry
    r_speed, p_speed = stats.pearsonr(asym_v, di_s_v)
    r_estpow, p_estpow = stats.pearsonr(asym_v, di_p_v)
    print(f"\n[1] Correlation with gradient asymmetry:")
    print(f"  DI/Speed      r = {r_speed:+.4f}  (p = {p_speed:.2e})")
    print(f"  DI/EstPower   r = {r_estpow:+.4f}  (p = {p_estpow:.2e})")
    print(f"  Reduction: {abs(r_speed) - abs(r_estpow):+.4f} ({(1 - abs(r_estpow)/abs(r_speed))*100:.1f}%)")

    # 2. Route prediction R² (simple OLS with route features)
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import GroupKFold

    uids_v = [records[i]['uid'] for i in range(len(records)) if valid[i]]
    X = np.column_stack([
        asym_v,
        [records[i]['mean_grad_h1'] for i in range(len(records)) if valid[i]],
        [records[i]['mean_grad_h2'] for i in range(len(records)) if valid[i]],
        [records[i]['total_asc'] for i in range(len(records)) if valid[i]],
        [records[i]['total_desc'] for i in range(len(records)) if valid[i]],
        alt_v,
    ])

    # GroupKFold CV
    unique_uids = list(set(uids_v))
    uid_to_int = {u: i for i, u in enumerate(unique_uids)}
    groups = np.array([uid_to_int[u] for u in uids_v])

    gkf = GroupKFold(n_splits=min(5, len(unique_uids)))

    def cv_r2(X, y, groups):
        preds = np.full(len(y), np.nan)
        for train_idx, test_idx in gkf.split(X, y, groups):
            model = Ridge(alpha=1.0)
            model.fit(X[train_idx], y[train_idx])
            preds[test_idx] = model.predict(X[test_idx])
        valid_p = ~np.isnan(preds)
        ss_res = np.sum((y[valid_p] - preds[valid_p])**2)
        ss_tot = np.sum((y[valid_p] - np.mean(y[valid_p]))**2)
        return 1 - ss_res / ss_tot

    r2_speed = cv_r2(X, di_s_v, groups)
    r2_estpow = cv_r2(X, di_p_v, groups)
    print(f"\n[2] Route prediction CV R² (GroupKFold, Ridge):")
    print(f"  DI/Speed      R² = {r2_speed:+.4f}")
    print(f"  DI/EstPower   R² = {r2_estpow:+.4f}")
    print(f"  Reduction: {r2_speed - r2_estpow:+.4f}")

    # 3. Hilly subset (alt_range > 400m)
    hilly = alt_v > 400
    if hilly.sum() > 50:
        r_s_h, _ = stats.pearsonr(asym_v[hilly], di_s_v[hilly])
        r_p_h, _ = stats.pearsonr(asym_v[hilly], di_p_v[hilly])
        r2_s_h = cv_r2(X[hilly], di_s_v[hilly], groups[hilly]) if len(set(groups[hilly])) >= 5 else float('nan')
        r2_p_h = cv_r2(X[hilly], di_p_v[hilly], groups[hilly]) if len(set(groups[hilly])) >= 5 else float('nan')
        print(f"\n[3] Hilly subset (alt > 400m, N = {hilly.sum():,}):")
        print(f"  DI/Speed      r = {r_s_h:+.4f}, R² = {r2_s_h:+.4f}")
        print(f"  DI/EstPower   r = {r_p_h:+.4f}, R² = {r2_p_h:+.4f}")

    # 4. Descriptive stats
    print(f"\n[4] Descriptive statistics:")
    print(f"  DI/Speed:    mean={np.mean(di_s_v):.4f}, std={np.std(di_s_v):.4f}, "
          f"median={np.median(di_s_v):.4f}")
    print(f"  DI/EstPower: mean={np.mean(di_p_v):.4f}, std={np.std(di_p_v):.4f}, "
          f"median={np.median(di_p_v):.4f}")

    # 5. Correlation between DI/Speed and DI/EstPower
    r_ss, _ = stats.pearsonr(di_s_v, di_p_v)
    print(f"\n[5] DI/Speed vs DI/EstPower correlation: r = {r_ss:+.4f}")

    # 6. ICC comparison (for users with >=5 workouts)
    from collections import defaultdict
    user_dis = defaultdict(list)
    user_dip = defaultdict(list)
    for i, r in enumerate(records):
        if valid[i]:
            user_dis[r['uid']].append(di_s_v[np.where(valid)[0].tolist().index(i)] if i < len(di_s_v) else None)
            user_dip[r['uid']].append(di_p_v[np.where(valid)[0].tolist().index(i)] if i < len(di_p_v) else None)

    # Simpler ICC: just use the grouped data
    uid_list = []
    dis_list = []
    dip_list = []
    idx = 0
    for i in range(len(records)):
        if valid[i]:
            uid_list.append(records[i]['uid'])
            dis_list.append(di_s_v[idx])
            dip_list.append(di_p_v[idx])
            idx += 1

    # Count per user
    from collections import Counter as Cnt
    uid_counts = Cnt(uid_list)
    rich_uids = {u for u, c in uid_counts.items() if c >= 5}

    if len(rich_uids) >= 10:
        # Simple ICC(3,1) approximation via one-way ANOVA
        def icc_oneway(values, groups):
            """ICC(1,1) from one-way random ANOVA."""
            group_set = sorted(set(groups))
            k_list = []
            for g in group_set:
                vals = [v for v, gg in zip(values, groups) if gg == g]
                if len(vals) >= 2:
                    k_list.append(vals)
            if len(k_list) < 10:
                return float('nan')
            # Between and within MS
            grand_mean = np.mean([v for kk in k_list for v in kk])
            n_groups = len(k_list)
            ns = [len(kk) for kk in k_list]
            n_total = sum(ns)
            ss_between = sum(len(kk) * (np.mean(kk) - grand_mean)**2 for kk in k_list)
            ss_within = sum(sum((v - np.mean(kk))**2 for v in kk) for kk in k_list)
            ms_between = ss_between / (n_groups - 1)
            ms_within = ss_within / (n_total - n_groups)
            k0 = np.mean(ns)
            icc = (ms_between - ms_within) / (ms_between + (k0 - 1) * ms_within)
            return max(0, icc)

        rich_vals_s = [v for v, u in zip(dis_list, uid_list) if u in rich_uids]
        rich_grps_s = [u for u in uid_list if u in rich_uids]
        rich_vals_p = [v for v, u in zip(dip_list, uid_list) if u in rich_uids]

        icc_s = icc_oneway(rich_vals_s, rich_grps_s)
        icc_p = icc_oneway(rich_vals_p, rich_grps_s)
        print(f"\n[6] ICC (users with ≥5 workouts, N_users = {len(rich_uids)}):")
        print(f"  DI/Speed      ICC = {icc_s:.4f}")
        print(f"  DI/EstPower   ICC = {icc_p:.4f}")

    # Save
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        f.write(f"H5 Experiment: DI/EstimatedPower vs DI/Speed\n")
        f.write(f"N = {valid.sum()}\n")
        f.write(f"[KEY] r_asym_di_speed = {r_speed:.4f}\n")
        f.write(f"[KEY] r_asym_di_estpower = {r_estpow:.4f}\n")
        f.write(f"[KEY] r2_cv_di_speed = {r2_speed:.4f}\n")
        f.write(f"[KEY] r2_cv_di_estpower = {r2_estpow:.4f}\n")
        f.write(f"[KEY] r_di_speed_vs_estpower = {r_ss:.4f}\n")
        if len(rich_uids) >= 10:
            f.write(f"[KEY] icc_di_speed = {icc_s:.4f}\n")
            f.write(f"[KEY] icc_di_estpower = {icc_p:.4f}\n")

    print(f"\nResults saved to {OUT}")
    print("Done.")


if __name__ == '__main__':
    main()
