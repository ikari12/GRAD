"""FitRec: Compute Meixner 4D Indices v2 - Handles speed gaps
Changes from v1:
  - Derive speed from GPS if speed array is short/missing
  - Use HR-only DI if speed completely unavailable
  - Independent array handling (no min-length alignment)
"""
import os, json, time, csv, math
from collections import defaultdict, Counter
from datetime import datetime, timezone
import numpy as np
import warnings
warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
DATA = os.path.join(DATA_DIR, "endomondoHR.json")
OUT = os.path.join(DATA_DIR, "meixner_4d_indices.csv")

def haversine(lat1, lon1, lat2, lon2):
    """Distance in meters between two GPS points."""
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def derive_speed_from_gps(lat_arr, lon_arr, ts_arr):
    """Compute speed (km/h) from GPS coordinates and timestamps."""
    n = min(len(lat_arr), len(lon_arr), len(ts_arr))
    if n < 10:
        return None
    speeds = [0.0]
    for i in range(1, n):
        la1, lo1 = lat_arr[i-1], lon_arr[i-1]
        la2, lo2 = lat_arr[i], lon_arr[i]
        dt = ts_arr[i] - ts_arr[i-1]
        if (la1 is None or la2 is None or lo1 is None or lo2 is None
            or not isinstance(la1, (int,float)) or not isinstance(la2, (int,float))
            or not isinstance(lo1, (int,float)) or not isinstance(lo2, (int,float))):
            speeds.append(speeds[-1])
            continue
        if dt <= 0:
            speeds.append(speeds[-1])
            continue
        dist = haversine(la1, lo1, la2, lo2)
        spd_ms = dist / dt
        spd_kmh = spd_ms * 3.6
        if spd_kmh > 150:  # outlier filter
            speeds.append(speeds[-1])
        else:
            speeds.append(spd_kmh)
    return np.array(speeds, dtype=float)

def clean_array(raw, min_len=10):
    """Convert to float array, interpolate NaNs."""
    if not isinstance(raw, list) or len(raw) < min_len:
        return None
    arr = np.array([x if x is not None and isinstance(x, (int,float)) else np.nan for x in raw], dtype=float)
    valid = ~np.isnan(arr)
    if valid.sum() < min_len:
        return None
    if np.isnan(arr).any():
        arr[~valid] = np.interp(np.where(~valid)[0], np.where(valid)[0], arr[valid])
    return arr

print("=" * 60)
print("Meixner 4D v2: Speed-gap tolerant")
print("=" * 60)

results = []
user_workouts = defaultdict(list)
total = 0
skip_reasons = Counter()
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
        except: continue
        if not isinstance(rec, dict): continue
        total += 1

        # === Filter ===
        hr = clean_array(rec.get('heart_rate', []))
        if hr is None: skip_reasons['no_hr'] += 1; continue

        alt = clean_array(rec.get('altitude', []))
        if alt is None: skip_reasons['no_alt'] += 1; continue

        ts_raw = rec.get('timestamp', [])
        if not isinstance(ts_raw, list) or len(ts_raw) < 10:
            skip_reasons['no_ts'] += 1; continue
        ts = np.array(ts_raw, dtype=float)

        dur_min = (ts[-1] - ts[0]) / 60.0
        if dur_min <= 90: skip_reasons['short'] += 1; continue

        alt_range = float(np.max(alt) - np.min(alt))
        if alt_range <= 200: skip_reasons['flat'] += 1; continue

        # === Get speed: prefer recorded, fallback to GPS-derived ===
        spd = clean_array(rec.get('speed', []))

        if spd is None or len(spd) < 10:
            # Derive from GPS
            spd = derive_speed_from_gps(
                rec.get('latitude', []),
                rec.get('longitude', []),
                ts_raw
            )

        has_speed = spd is not None and len(spd) >= 10

        # Align arrays to common length
        arrays = [hr, alt, ts]
        if has_speed:
            arrays.append(spd)
        n = min(len(a) for a in arrays)
        if n < 20: skip_reasons['too_few'] += 1; continue

        hr = hr[:n]; alt = alt[:n]; ts = ts[:n]
        if has_speed:
            spd = spd[:n]
            spd_pos = spd > 0.5
        else:
            spd = None
            spd_pos = None

        mid = n // 2

        # ============================================================
        # DI: Durability Index
        # ============================================================
        if has_speed and spd_pos is not None:
            m1 = spd_pos[:mid]; m2 = spd_pos[mid:]
            if m1.sum() > 5 and m2.sum() > 5:
                r1 = np.mean(hr[:mid][m1]) / np.mean(spd[:mid][m1])
                r2 = np.mean(hr[mid:][m2]) / np.mean(spd[mid:][m2])
                DI = r2 / r1 if r1 > 0 else np.nan
            else:
                DI = np.nan
        else:
            # HR-only DI: cardiac drift
            hr1 = np.mean(hr[:mid]); hr2 = np.mean(hr[mid:])
            DI = hr2 / hr1 if hr1 > 0 else np.nan

        # ============================================================
        # FI: Fatigability Index
        # ============================================================
        if has_speed:
            # Gradient computation
            dt = np.diff(ts); dt[dt <= 0] = 1
            dx = np.diff(np.cumsum(spd * np.gradient(ts) / 3600.0)) * 1000
            dy = np.diff(alt)
            dx[np.abs(dx) < 0.1] = 0.1
            gradient = np.clip((dy / dx) * 100, -50, 50)
            gradient = np.append(gradient, gradient[-1])

            grad_bins = [(-50,-10), (-10,-3), (-3,3), (3,10), (10,50)]
            fi_ratios = []
            for gmin, gmax in grad_bins:
                mask_g = (gradient >= gmin) & (gradient < gmax) & spd_pos
                m1 = mask_g.copy(); m1[mid:] = False
                m2 = mask_g.copy(); m2[:mid] = False
                if m1.sum() > 3 and m2.sum() > 3:
                    s1 = np.mean(spd[m1]); s2 = np.mean(spd[m2])
                    if s1 > 0: fi_ratios.append(s2 / s1)
            FI = np.mean(fi_ratios) if fi_ratios else np.nan
        else:
            FI = np.nan

        # ============================================================
        # RI: Repeatability Index
        # ============================================================
        window = max(1, n // 20)
        sm_alt = np.convolve(alt, np.ones(window)/window, mode='valid')
        climbs = []
        climbing = False; cs_alt = sm_alt[0] if len(sm_alt) > 0 else 0; cs_idx = 0

        for j in range(1, len(sm_alt)):
            if sm_alt[j] > sm_alt[j-1] + 0.5:
                if not climbing:
                    climbing = True; cs_idx = j; cs_alt = sm_alt[j-1]
            else:
                if climbing:
                    if sm_alt[j-1] - cs_alt > 50:
                        climbs.append((cs_idx, j))
                    climbing = False
        if climbing and sm_alt[-1] - cs_alt > 50:
            climbs.append((cs_idx, len(sm_alt)-1))

        if len(climbs) >= 2 and has_speed:
            climb_speeds = []
            for ci, (cs, ce) in enumerate(climbs):
                seg = spd[cs:ce]
                m = seg > 0.5
                if m.sum() > 2:
                    climb_speeds.append(np.mean(seg[m]))
            if len(climb_speeds) >= 2:
                RI = climb_speeds[-1] / climb_speeds[0] if climb_speeds[0] > 0 else np.nan
            else:
                RI = np.nan
        elif len(climbs) >= 2:
            # HR-based RI: HR increase across climbs
            climb_hrs = []
            for cs, ce in climbs:
                seg = hr[cs:ce]
                if len(seg) > 2:
                    climb_hrs.append(np.mean(seg))
            if len(climb_hrs) >= 2:
                # Inverse: higher HR in later climbs = worse
                RI = climb_hrs[0] / climb_hrs[-1] if climb_hrs[-1] > 0 else np.nan
            else:
                RI = np.nan
        else:
            RI = np.nan

        # ============================================================
        # Metadata
        # ============================================================
        lat_arr = rec.get('latitude', [])
        lon_arr = rec.get('longitude', [])
        lat0 = round(lat_arr[0], 1) if isinstance(lat_arr, list) and len(lat_arr) > 0 else None
        lon0 = round(lon_arr[0], 1) if isinstance(lon_arr, list) and len(lon_arr) > 0 else None
        try: date_str = datetime.fromtimestamp(ts_raw[0], tz=timezone.utc).strftime('%Y-%m-%d')
        except: date_str = None

        sport = rec.get('sport', '?')
        userId = rec.get('userId', '?')
        max_alt_val = float(np.max(alt))

        row = {
            'id': rec.get('id', ln), 'userId': userId,
            'sport': sport, 'gender': rec.get('gender', '?'),
            'dur_min': round(dur_min, 1), 'alt_range': round(alt_range, 1),
            'max_alt': round(max_alt_val, 1),
            'total_ascent': round(float(np.sum(np.maximum(np.diff(alt), 0))), 1),
            'total_descent': round(float(np.sum(np.abs(np.minimum(np.diff(alt), 0)))), 1),
            'n_climbs': len(climbs), 'n_points': n,
            'avg_hr': round(float(np.mean(hr)), 1),
            'max_hr': round(float(np.max(hr))),
            'has_speed': 1 if has_speed else 0,
            'lat': lat0, 'lon': lon0, 'date': date_str,
            'DI': round(DI, 4) if not np.isnan(DI) else '',
            'FI': round(FI, 4) if not np.isnan(FI) else '',
            'RI': round(RI, 4) if not np.isnan(RI) else '',
        }
        results.append(row)
        user_workouts[userId].append({
            'idx': len(results)-1, 'max_alt': max_alt_val,
            'avg_speed': float(np.mean(spd)) if has_speed else 0,
            'avg_hr': float(np.mean(hr)), 'DI': DI,
        })

        if len(results) % 2000 == 0:
            e = time.time()-t0
            print(f"  {total:>7,} | {len(results):>5,} done | {e:.0f}s | spd_ok:{sum(1 for r in results[-2000:] if r['has_speed']):,}/2000")

elapsed = time.time()-t0
print(f"\n  Phase 1: {len(results):,} workouts, {len(user_workouts):,} users in {elapsed:.0f}s")
print(f"  Skip reasons: {dict(skip_reasons)}")

# === ReI ===
print(f"\nPhase 2: ReI")
rei_count = 0
for uid, wkts in user_workouts.items():
    if len(wkts) < 2: continue
    high = [w for w in wkts if w['max_alt'] > 1500]
    low = [w for w in wkts if w['max_alt'] <= 1000]
    if high and low:
        h_hr = np.mean([w['avg_hr'] for w in high])
        l_hr = np.mean([w['avg_hr'] for w in low])
        if h_hr > 0:
            ReI = l_hr / h_hr  # Lower HR at altitude = better resilience
            for w in high:
                results[w['idx']]['ReI'] = round(ReI, 4)
                rei_count += 1
print(f"  ReI: {rei_count}")

for r in results:
    if 'ReI' not in r: r['ReI'] = ''

# === Save ===
keys = ['id','userId','sport','gender','dur_min','alt_range','max_alt',
        'total_ascent','total_descent','n_climbs','n_points','avg_hr','max_hr',
        'has_speed','lat','lon','date','DI','FI','RI','ReI']
with open(OUT, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
    w.writeheader(); w.writerows(results)
print(f"\n  Saved: {OUT} ({len(results):,} rows)")

# === Stats ===
di_v = [r['DI'] for r in results if r['DI'] != '']
fi_v = [r['FI'] for r in results if r['FI'] != '']
ri_v = [r['RI'] for r in results if r['RI'] != '']
rei_v = [r['ReI'] for r in results if r['ReI'] != '']

print(f"\n  Coverage:")
print(f"    DI:  {len(di_v):>6,} / {len(results):,} ({100*len(di_v)/len(results):.0f}%)")
print(f"    FI:  {len(fi_v):>6,} / {len(results):,} ({100*len(fi_v)/len(results):.0f}%)")
print(f"    RI:  {len(ri_v):>6,} / {len(results):,} ({100*len(ri_v)/len(results):.0f}%)")
print(f"    ReI: {len(rei_v):>6,} / {len(results):,} ({100*len(rei_v)/len(results):.0f}%)")

for name, vals in [('DI', di_v), ('FI', fi_v), ('RI', ri_v), ('ReI', rei_v)]:
    if vals:
        a = np.array(vals)
        print(f"  {name:3s}: mean={np.mean(a):.3f} med={np.median(a):.3f} std={np.std(a):.3f} [{np.percentile(a,25):.3f}, {np.percentile(a,75):.3f}]")

# Correlation
all3 = [(r['DI'],r['FI'],r['RI']) for r in results if r['DI']!='' and r['FI']!='' and r['RI']!='']
if len(all3) > 30:
    a = np.array(all3)
    c = np.corrcoef(a.T)
    print(f"\n  Corr (n={len(all3):,}):")
    print(f"       DI      FI      RI")
    for i, nm in enumerate(['DI','FI','RI']):
        print(f"  {nm}  {c[i,0]:6.3f}  {c[i,1]:6.3f}  {c[i,2]:6.3f}")
    # PCA
    ct = a - a.mean(axis=0)
    ev, _ = np.linalg.eig(np.cov(ct.T))
    ev = np.sort(ev.real)[::-1]
    tv = ev.sum()
    print(f"\n  PCA:")
    for i in range(3):
        print(f"    PC{i+1}: {100*ev[i]/tv:.1f}% (cum {100*ev[:i+1].sum()/tv:.1f}%)")

# Sport
sports = Counter(r['sport'] for r in results)
print(f"\n  Sport:")
for s, cnt in sports.most_common(10):
    sub = [r for r in results if r['sport']==s and r['DI']!='']
    if sub:
        print(f"    {s:25s} n={cnt:5,}  DI={np.mean([r['DI'] for r in sub]):.3f}  FI={np.mean([r['FI'] for r in sub if r['FI']!='']):.3f}  RI={np.mean([r['RI'] for r in sub if r['RI']!='']):.3f}")

print(f"\n  Total: {time.time()-t0:.0f}s")
