#!/usr/bin/env python3
"""
FitRecの実データからシミュレーションパラメータを抽出し，
05_figures.py のシミュレーションを実データに基づく制御実験に置き換える．

出力: シミュレーションパラメータの統計量（mean, std）を表示
"""

import os
import sys
import numpy as np

_BASE = os.path.dirname(os.path.abspath(__file__))
MEIXNER_PATH = os.path.join(_BASE, "data", "meixner_4d_indices.csv")
ABC_PATH = os.path.join(_BASE, "data", "abc_metrics.csv")

def load_csv(path):
    with open(path, "r") as f:
        header = f.readline().strip().replace('\r', '').split(",")
        rows = [line.strip().replace('\r', '').split(",") for line in f if line.strip()]
    data = {col: [] for col in header}
    for row in rows:
        for col, val in zip(header, row):
            data[col].append(val)
    return data

def to_float(values):
    result = []
    for v in values:
        try:
            result.append(float(v))
        except (ValueError, TypeError):
            result.append(np.nan)
    return np.array(result, dtype=float)

# ============================================================
# 1. meixner_4d_indices.csv から勾配関連パラメータを抽出
# ============================================================
print("=" * 60)
print("FitRec 実データからのシミュレーションパラメータ抽出")
print("=" * 60)

meixner = load_csv(MEIXNER_PATH)
abc = load_csv(ABC_PATH)

# --- 勾配の統計 (abc_metrics.csv) ---
grad_mean = to_float(abc["grad_mean"])
grad_std = to_float(abc["grad_std"])
asc_front = to_float(abc["asc_front"])
desc_front = to_float(abc["desc_front"])
total_ascent = to_float(abc["total_ascent"])
total_descent = to_float(abc["total_descent"])

# NaN除外
valid = np.isfinite(grad_mean) & np.isfinite(grad_std) & np.isfinite(asc_front) & np.isfinite(desc_front)
grad_mean = grad_mean[valid]
grad_std = grad_std[valid]
asc_front = asc_front[valid]
desc_front = desc_front[valid]
total_ascent_v = total_ascent[valid]
total_descent_v = total_descent[valid]

print(f"\n--- 勾配分布（abc_metrics.csv, N={valid.sum()}） ---")
print(f"grad_mean:  mean={np.mean(grad_mean):.4f}, std={np.std(grad_mean):.4f}, "
      f"median={np.median(grad_mean):.4f}, P5={np.percentile(grad_mean, 5):.4f}, P95={np.percentile(grad_mean, 95):.4f}")
print(f"grad_std:   mean={np.mean(grad_std):.4f}, std={np.std(grad_std):.4f}, "
      f"median={np.median(grad_std):.4f}")
print(f"asc_front:  mean={np.mean(asc_front):.4f}, std={np.std(asc_front):.4f}")
print(f"desc_front: mean={np.mean(desc_front):.4f}, std={np.std(desc_front):.4f}")

# ルートタイプ分類 (asc_front で分類)
# asc_front > 0.6 → 前半登り
# asc_front < 0.4 → 後半登り
# 0.4 <= asc_front <= 0.6 → 対称
front_climb_mask = asc_front > 0.6
back_climb_mask = asc_front < 0.4
symmetric_mask = (asc_front >= 0.4) & (asc_front <= 0.6)

print(f"\n--- ルートタイプ分類（asc_front ベース） ---")
print(f"Front-climb (asc_front > 0.6): N={front_climb_mask.sum()} ({front_climb_mask.mean()*100:.1f}%)")
print(f"Back-climb  (asc_front < 0.4): N={back_climb_mask.sum()} ({back_climb_mask.mean()*100:.1f}%)")
print(f"Symmetric   (0.4-0.6):         N={symmetric_mask.sum()} ({symmetric_mask.mean()*100:.1f}%)")

for label, mask in [("Front-climb", front_climb_mask), ("Back-climb", back_climb_mask), ("Symmetric", symmetric_mask)]:
    if mask.sum() > 0:
        print(f"\n  {label}:")
        print(f"    grad_mean: mean={np.mean(grad_mean[mask]):.4f}, std={np.std(grad_mean[mask]):.4f}")
        print(f"    grad_std:  mean={np.mean(grad_std[mask]):.4f}, std={np.std(grad_std[mask]):.4f}")

# --- HR関連パラメータ (meixner_4d_indices.csv) ---
avg_hr = to_float(meixner["avg_hr"])
max_hr = to_float(meixner["max_hr"])

valid_hr = np.isfinite(avg_hr) & np.isfinite(max_hr)
avg_hr = avg_hr[valid_hr]

print(f"\n--- 心拍数分布（meixner_4d_indices.csv, N={valid_hr.sum()}） ---")
print(f"avg_hr: mean={np.mean(avg_hr):.1f}, std={np.std(avg_hr):.1f}, "
      f"P5={np.percentile(avg_hr, 5):.1f}, P95={np.percentile(avg_hr, 95):.1f}")

# --- HR感受性パラメータ (abc_metrics.csv) ---
hr_grad_sens = to_float(abc["hr_gradient_sensitivity"])
hr_speed_sens = to_float(abc["hr_speed_sensitivity"])
avg_speed = to_float(abc["avg_speed"])

valid_abc = np.isfinite(hr_grad_sens) & np.isfinite(hr_speed_sens) & np.isfinite(avg_speed)
hr_grad_sens_v = hr_grad_sens[valid_abc]
hr_speed_sens_v = hr_speed_sens[valid_abc]
avg_speed_v = avg_speed[valid_abc]

print(f"\n--- HR感受性（abc_metrics.csv, N={valid_abc.sum()}） ---")
print(f"hr_gradient_sensitivity: mean={np.mean(hr_grad_sens_v):.4f}, std={np.std(hr_grad_sens_v):.4f}, "
      f"P5={np.percentile(hr_grad_sens_v, 5):.4f}, P95={np.percentile(hr_grad_sens_v, 95):.4f}")
print(f"hr_speed_sensitivity:    mean={np.mean(hr_speed_sens_v):.4f}, std={np.std(hr_speed_sens_v):.4f}")
print(f"avg_speed (km/h):        mean={np.mean(avg_speed_v):.2f}, std={np.std(avg_speed_v):.2f}, "
      f"P5={np.percentile(avg_speed_v, 5):.2f}, P95={np.percentile(avg_speed_v, 95):.2f}")

# --- スポーツ別内訳 ---
sports = meixner["sport"]
sport_counts = {}
for s in sports:
    sport_counts[s] = sport_counts.get(s, 0) + 1
print(f"\n--- スポーツ内訳 ---")
for s, c in sorted(sport_counts.items(), key=lambda x: -x[1]):
    print(f"  {s}: {c} ({c/len(sports)*100:.1f}%)")

# ============================================================
# 2. 推奨パラメータのサマリー
# ============================================================
print("\n" + "=" * 60)
print("推奨シミュレーションパラメータ（FitRec実データ準拠）")
print("=" * 60)
print("""
以下のパラメータを 05_figures.py のシミュレーションに適用すべき:

1. ルートタイプ比率: FitRecの実測分類比率を使用
2. 勾配分布: 各ルートタイプのgrad_mean, grad_stdの実測分布から抽出
3. HR: avg_hrの実測分布 (P5-P95) を使用
4. HR感受性: hr_gradient_sensitivityの実測分布を使用  
5. 速度: avg_speedの実測分布を使用
""")
