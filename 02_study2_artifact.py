#!/usr/bin/env python3
"""
Study 2: DI Prediction Artifact Detection
==========================================
DIの予測アーティファクト（ルート特徴量からの疑似的予測可能性）を検出するスクリプト．

分析内容:
  a) ルート特徴量による Naive DI 予測（Ridge 回帰）
  b) ルート特徴量による GACD 予測
  c) シミュレーション証明（心拍ドリフト = 0 でも DI がルート形状で変動）
  d) 下降位置効果（desc_front と gacd_rate の関係）

出力形式: [KEY] value_name = number
"""

import os
import sys

import numpy as np
from scipy import stats
from sklearn.linear_model import Ridge
from sklearn.model_selection import cross_val_score, GroupKFold
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# データパスの設定
# ---------------------------------------------------------------------------
_BASE = os.path.dirname(__file__)
_MEIXNER_REL = os.path.join(_BASE, "data", "meixner_4d_indices.csv")
_MEIXNER_ABS = "/Users/hisashi/Desktop/Workspace/Yamap_GPX/data/fitrec/meixner_4d_indices.csv"
MEIXNER_PATH = _MEIXNER_REL if os.path.exists(_MEIXNER_REL) else _MEIXNER_ABS

_ABC_REL = os.path.join(_BASE, "data", "abc_metrics.csv")
_ABC_ABS = "/Users/hisashi/Desktop/Workspace/Yamap_GPX/data/fitrec/abc_metrics.csv"
ABC_PATH = _ABC_REL if os.path.exists(_ABC_REL) else _ABC_ABS

np.random.seed(42)


# ---------------------------------------------------------------------------
# ユーティリティ関数
# ---------------------------------------------------------------------------
def load_csv(path: str) -> dict:
    """CSVファイルを読み込み，列名をキーとする辞書を返す．"""
    with open(path, "r") as f:
        header = f.readline().strip().split(",")
        rows = [line.strip().split(",") for line in f if line.strip()]
    data = {col: [] for col in header}
    for row in rows:
        for col, val in zip(header, row):
            data[col].append(val)
    return data


def to_float(values: list) -> np.ndarray:
    """文字列リストを float 配列に変換する．空文字・nan 文字列は NaN にする．"""
    result = []
    for v in values:
        try:
            fv = float(v)
            result.append(fv)
        except (ValueError, TypeError):
            result.append(np.nan)
    return np.array(result, dtype=float)


def printkey(name: str, value: float, fmt: str = ".4f") -> None:
    """[KEY] 形式で値を出力する．"""
    print(f"[KEY] {name} = {value:{fmt}}")


def build_feature_matrix(data: dict, col_names: list) -> np.ndarray:
    """指定列を float 行列に変換する．"""
    arrays = [to_float(data[c]) for c in col_names]
    return np.column_stack(arrays)


def valid_rows(*arrays) -> np.ndarray:
    """全配列で NaN でない行のマスクを返す．"""
    mask = np.ones(len(arrays[0]), dtype=bool)
    for a in arrays:
        if a.ndim == 1:
            mask &= ~np.isnan(a)
        else:
            mask &= ~np.any(np.isnan(a), axis=1)
    return mask


# ---------------------------------------------------------------------------
# データ読み込み
# ---------------------------------------------------------------------------
print("Loading data...")
meixner = load_csv(MEIXNER_PATH)
abc = load_csv(ABC_PATH)

# ===================================================================
# (a) ルート特徴量による Naive DI 予測
# ===================================================================
print()
print("=" * 60)
print("(a) Naive DI Prediction from Route Features (Ridge + GBT)")
print("=" * 60)

# abc_metrics から豊富なルート特徴量を取得（id で結合）
abc_id_set = set(abc["id"]) if "id" in abc else set()
meixner_ids = meixner["id"]

# abc_metrics のルート特徴量を id → index マッピングで結合
abc_route_by_id = {}
rich_cols = ["total_ascent", "total_descent", "alt_range", "max_alt", "min_alt",
             "grad_mean", "grad_std", "pct_climb", "pct_desc", "pct_flat",
             "asc_front", "desc_front", "dur_min"]
for i, aid in enumerate(abc["id"]):
    vals = []
    for c in rich_cols:
        try:
            v = float(abc[c][i])
            vals.append(v if np.isfinite(v) else np.nan)
        except (ValueError, TypeError):
            vals.append(np.nan)
    abc_route_by_id[aid] = vals

# 結合: meixner DI + abc route features
X_rich = []; y_rich = []; X_hilly_list = []; y_hilly_list = []
for i, mid in enumerate(meixner_ids):
    if mid in abc_route_by_id:
        try:
            di_val = float(meixner["DI"][i])
            ar_val = float(meixner["alt_range"][i])
        except (ValueError, TypeError):
            continue
        if not np.isfinite(di_val):
            continue
        feats = abc_route_by_id[mid]
        if any(np.isnan(f) for f in feats):
            continue
        X_rich.append(feats)
        y_rich.append(di_val)
        if np.isfinite(ar_val) and ar_val > 500:
            X_hilly_list.append(feats)
            y_hilly_list.append(di_val)

X_rich = np.array(X_rich, dtype=np.float64)
y_rich = np.array(y_rich, dtype=np.float64)

# Ridge prediction (all)
if len(X_rich) > 30:
    scaler_a = StandardScaler()
    X_s = scaler_a.fit_transform(X_rich)
    model_a = Ridge(alpha=1.0)
    model_a.fit(X_s, y_rich)
    di_route_r2_all = model_a.score(X_s, y_rich)
    # GroupKFold: 同一ユーザーの train/test 混在を防止
    uid_rich = [meixner["userId"][i] for i, mid in enumerate(meixner_ids) if mid in abc_route_by_id
                and np.isfinite(float(meixner["DI"][i]) if meixner["DI"][i] not in ('','nan') else float('nan'))
                and mid in abc_route_by_id and not any(np.isnan(f) for f in abc_route_by_id[mid])]
    uid_map_a = {u: j for j, u in enumerate(sorted(set(uid_rich)))}
    groups_a = np.array([uid_map_a[u] for u in uid_rich[:len(X_rich)]])
    gkf_a = GroupKFold(n_splits=min(5, len(set(groups_a))))
    cv_a = cross_val_score(Ridge(alpha=1.0), X_s, y_rich, cv=gkf_a, groups=groups_a, scoring="r2")
    di_route_r2_cv_all = np.mean(cv_a)
else:
    di_route_r2_all = np.nan
    di_route_r2_cv_all = np.nan

# GBT prediction on VERY_HILLY subset (GroupKFold CV)
from sklearn.ensemble import GradientBoostingRegressor
if len(X_hilly_list) > 30:
    X_h = np.array(X_hilly_list, dtype=np.float64)
    y_h = np.array(y_hilly_list, dtype=np.float64)
    # Build user groups for hilly subset
    uid_hilly = []
    for i, mid in enumerate(meixner_ids):
        if mid in abc_route_by_id:
            try:
                di_val = float(meixner["DI"][i])
                ar_val = float(meixner["alt_range"][i])
            except (ValueError, TypeError):
                continue
            if not np.isfinite(di_val):
                continue
            feats = abc_route_by_id[mid]
            if any(np.isnan(f) for f in feats):
                continue
            if np.isfinite(ar_val) and ar_val > 500:
                uid_hilly.append(meixner["userId"][i])
    uid_map_h = {u: j for j, u in enumerate(sorted(set(uid_hilly)))}
    groups_h = np.array([uid_map_h[u] for u in uid_hilly])
    scaler_h = StandardScaler()
    X_hs = scaler_h.fit_transform(X_h)
    gbt = GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=42)
    gbt.fit(X_hs, y_h)
    di_route_r2_hilly_insample = gbt.score(X_hs, y_h)
    # GroupKFold CV
    n_folds_h = min(5, len(set(groups_h)))
    gkf_h = GroupKFold(n_splits=n_folds_h)
    cv_gbt = cross_val_score(gbt, X_hs, y_h, cv=gkf_h, groups=groups_h, scoring="r2")
    di_route_r2_hilly = np.mean(cv_gbt)
else:
    di_route_r2_hilly = np.nan
    di_route_r2_hilly_insample = np.nan

printkey("di_route_r2_all", di_route_r2_all)
printkey("di_route_r2_cv_all", di_route_r2_cv_all)
printkey("di_route_r2_hilly", di_route_r2_hilly)
print(f"  N(all valid) = {len(X_rich)}, N(hilly) = {len(X_hilly_list)}")

# ===================================================================
# (b) GACD 予測（within-person deviation からの予測）
# ===================================================================
print()
print("=" * 60)
print("(b) GACD Prediction from Route Features (within-person deviation, Ridge)")
print("=" * 60)

gacd_route_cols = [
    "total_ascent", "total_descent", "alt_range", "max_alt", "min_alt",
    "grad_mean", "grad_std", "pct_climb", "pct_desc", "pct_flat",
    "asc_front", "desc_front", "dur_min",
]
X_gacd = build_feature_matrix(abc, gacd_route_cols)
y_gacd = to_float(abc["gacd_rate"])
user_ids_abc = abc["userId"]

mask_b = valid_rows(X_gacd, y_gacd)

# Within-person deviation: y_dev = y - person_mean
from collections import defaultdict
user_means = defaultdict(list)
for i in range(len(y_gacd)):
    if mask_b[i]:
        user_means[user_ids_abc[i]].append(y_gacd[i])
user_mean_map = {u: np.mean(v) for u, v in user_means.items() if len(v) >= 3}

X_dev = []; y_dev = []; groups_dev = []
uid_map_b = {}
for i in range(len(y_gacd)):
    if mask_b[i] and user_ids_abc[i] in user_mean_map:
        X_dev.append(X_gacd[i])
        y_dev.append(y_gacd[i] - user_mean_map[user_ids_abc[i]])
        uid = user_ids_abc[i]
        if uid not in uid_map_b:
            uid_map_b[uid] = len(uid_map_b)
        groups_dev.append(uid_map_b[uid])

X_dev = np.array(X_dev, dtype=np.float64)
y_dev = np.array(y_dev, dtype=np.float64)
groups_dev = np.array(groups_dev)

scaler_b = StandardScaler()
X_gacd_s = scaler_b.fit_transform(X_dev)

model_b = Ridge(alpha=1.0)
model_b.fit(X_gacd_s, y_dev)
gacd_route_r2_all = model_b.score(X_gacd_s, y_dev)

# GroupKFold: 同一ユーザーの train/test 混在を防止
gkf_b = GroupKFold(n_splits=min(5, len(set(groups_dev))))
cv_scores_b = cross_val_score(Ridge(alpha=1.0), X_gacd_s, y_dev, cv=gkf_b, groups=groups_dev, scoring="r2")
gacd_route_r2_cv_all = np.mean(cv_scores_b)

printkey("gacd_route_r2_all", gacd_route_r2_all)
printkey("gacd_route_r2_cv_all", gacd_route_r2_cv_all)
print(f"  N(valid deviations) = {len(X_dev)}")

# ===================================================================
# (c) シミュレーション証明（心拍ドリフト = 0）
# ===================================================================
print()
print("=" * 60)
print("(c) Simulation: DI artifact with zero cardiac drift")
print("=" * 60)

np.random.seed(42)
N_SIM = 5000

# ルートタイプごとの勾配プロファイルを生成
# 各ワークアウトは 60 ポイント（元の分析と一致），前半 30 / 後半 30
n_points = 60
half = n_points // 2


def make_gradient_profile(route_type: str) -> np.ndarray:
    """ルートタイプに応じた勾配プロファイルを生成する（正規分布使用）．"""
    if route_type == "front_climb":
        return np.concatenate([
            np.random.normal(8, 3, half),
            np.random.normal(-5, 3, half),
        ])
    elif route_type == "back_climb":
        return np.concatenate([
            np.random.normal(-5, 3, half),
            np.random.normal(8, 3, half),
        ])
    elif route_type == "symmetric":
        return np.random.normal(0, 5, n_points)
    elif route_type == "valley":
        return np.concatenate([
            np.random.normal(-6, 3, half),
            np.random.normal(6, 3, half),
        ])
    elif route_type == "peak":
        return np.concatenate([
            np.random.normal(6, 3, half),
            np.random.normal(-6, 3, half),
        ])
    else:
        raise ValueError(f"Unknown route type: {route_type}")


route_types = ["front_climb", "back_climb", "symmetric", "valley", "peak"]

sim_dis = []
sim_route_features = []  # gradient_asymmetry，asc_front，desc_front，grad_std，alt_range
sim_labels = []

for i in range(N_SIM):
    rt = np.random.choice(route_types)
    gradients = make_gradient_profile(rt)

    # ベースパラメータにランダムな個人差を加える
    hr_base = np.random.uniform(100, 140)
    hr_sensitivity = np.random.uniform(2, 8)
    speed_base = np.random.uniform(2, 5)
    speed_sensitivity = np.random.uniform(0.05, 0.15)

    # HR = base + sensitivity * gradient + noise （ドリフトなし）
    hr = hr_base + hr_sensitivity * gradients + np.random.normal(0, 3, n_points)

    # Speed = base - sensitivity * gradient + noise
    speed = np.maximum(0.5, speed_base - speed_sensitivity * gradients + np.random.normal(0, 0.3, n_points))

    # DI の計算: (HR_H2/Speed_H2) / (HR_H1/Speed_H1)
    hr_h1 = np.mean(hr[:half])
    hr_h2 = np.mean(hr[half:])
    speed_h1 = np.mean(speed[:half])
    speed_h2 = np.mean(speed[half:])

    di = (hr_h2 / speed_h2) / (hr_h1 / speed_h1)
    sim_dis.append(di)

    # ルート特徴量の算出
    asc_mask = gradients > 0
    desc_mask = gradients < 0

    # gradient_asymmetry: 前半と後半の勾配平均の差
    grad_asymmetry = np.mean(gradients[:half]) - np.mean(gradients[half:])

    # asc_front: 登りポイントのうち前半に含まれる割合
    n_asc_total = np.sum(asc_mask)
    n_asc_front = np.sum(asc_mask[:half])
    asc_front = n_asc_front / n_asc_total if n_asc_total > 0 else 0.5

    # desc_front: 下りポイントのうち前半に含まれる割合
    n_desc_total = np.sum(desc_mask)
    n_desc_front = np.sum(desc_mask[:half])
    desc_front = n_desc_front / n_desc_total if n_desc_total > 0 else 0.5

    # 累積標高から alt_range を概算
    alt = np.cumsum(gradients * 0.1)  # 簡易的に 100m 間隔と仮定
    alt_range_val = np.max(alt) - np.min(alt)

    sim_route_features.append([
        grad_asymmetry, asc_front, desc_front,
        np.std(gradients), alt_range_val,
    ])
    sim_labels.append(rt)

sim_dis = np.array(sim_dis)
sim_route_features = np.array(sim_route_features)
sim_labels = np.array(sim_labels)

# DI をルート特徴量から予測
scaler_sim = StandardScaler()
X_sim = scaler_sim.fit_transform(sim_route_features)
cv_scores_sim = cross_val_score(Ridge(alpha=1.0), X_sim, sim_dis, cv=5, scoring="r2")

printkey("sim_r2_cv", np.mean(cv_scores_sim))

# gradient_asymmetry と DI の相関
r_asymmetry = np.corrcoef(sim_route_features[:, 0], sim_dis)[0, 1]
printkey("sim_r_asymmetry", r_asymmetry)

# ルートタイプ別の DI 平均
for rt in ["front_climb", "back_climb", "symmetric"]:
    rt_mask = sim_labels == rt
    printkey(f"sim_di_{rt}", np.mean(sim_dis[rt_mask]))

# ドリフト実験: symmetric ルートのみ，ドリフト = 0.0, 0.1, 0.5
print()
print("  --- Drift experiment (symmetric routes only) ---")

for drift_val in [0.0, 0.1, 0.5]:
    drift_dis = []
    np.random.seed(42)
    for _ in range(1000):
        gradients = make_gradient_profile("symmetric")

        hr_base = np.random.uniform(120, 160)
        hr_sensitivity = np.random.uniform(1.0, 3.0)
        speed_base = np.random.uniform(8, 15)
        speed_sensitivity = np.random.uniform(0.3, 1.0)

        # ドリフト: 時間に比例して HR が増加
        time_vec = np.linspace(0, 1, n_points)
        hr = hr_base + hr_sensitivity * gradients + drift_val * hr_base * time_vec
        hr += np.random.normal(0, 2, n_points)
        hr = np.clip(hr, 60, 220)

        speed = speed_base - speed_sensitivity * gradients + np.random.normal(0, 0.5, n_points)
        speed = np.clip(speed, 1, 30)

        hr_h1 = np.mean(hr[:half])
        hr_h2 = np.mean(hr[half:])
        speed_h1 = np.mean(speed[:half])
        speed_h2 = np.mean(speed[half:])
        di = (hr_h2 / speed_h2) / (hr_h1 / speed_h1)
        drift_dis.append(di)

    drift_key = f"sim_drift{str(drift_val).replace('.', '')}_di"
    printkey(drift_key, np.mean(drift_dis))

# ===================================================================
# (d) 下降位置効果（desc_front と gacd_rate の関係）
# ===================================================================
print()
print("=" * 60)
print("(d) Descent Position Effect (Table 2)")
print("=" * 60)

# ABC データから必要な列を取得
desc_front_abc = to_float(abc["desc_front"])
gacd_rate_abc = to_float(abc["gacd_rate"])
grad_std_abc = to_float(abc["grad_std"])
alt_range_abc = to_float(abc["alt_range"])
user_ids_abc = np.array(abc["userId"])
sport_abc = np.array(abc["sport"])

# 有効データマスク
valid_d = valid_rows(desc_front_abc, gacd_rate_abc, grad_std_abc, alt_range_abc)


def between_person_r(mask: np.ndarray) -> float:
    """指定マスクのサブセットで desc_front と gacd_rate の Person 間相関を計算する．"""
    combined = mask & valid_d
    if np.sum(combined) < 10:
        return np.nan
    return np.corrcoef(desc_front_abc[combined], gacd_rate_abc[combined])[0, 1]


def within_person_analysis(mask: np.ndarray, min_workouts: int = 5) -> tuple:
    """
    個人内分析: ユーザごとに desc_front と gacd_rate の相関を求め，
    平均相関が 0 と異なるか t 検定する．
    """
    combined = mask & valid_d
    users = np.unique(user_ids_abc[combined])
    user_rs = []

    for u in users:
        u_mask = combined & (user_ids_abc == u)
        if np.sum(u_mask) < min_workouts:
            continue
        df_u = desc_front_abc[u_mask]
        gr_u = gacd_rate_abc[u_mask]
        # 分散がゼロの場合はスキップ
        if np.std(df_u) < 1e-10 or np.std(gr_u) < 1e-10:
            continue
        r_u = np.corrcoef(df_u, gr_u)[0, 1]
        if not np.isnan(r_u):
            user_rs.append(r_u)

    if len(user_rs) < 3:
        return np.nan, np.nan

    user_rs = np.array(user_rs)
    mean_r = np.mean(user_rs)
    t_stat, p_val = stats.ttest_1samp(user_rs, 0)
    return mean_r, p_val


def cohens_d_median_split(mask: np.ndarray) -> float:
    """desc_front の中央値分割で gacd_rate の Cohen's d を計算する．"""
    combined = mask & valid_d
    if np.sum(combined) < 10:
        return np.nan
    df_sub = desc_front_abc[combined]
    gr_sub = gacd_rate_abc[combined]

    median_df = np.median(df_sub)
    low_mask = df_sub <= median_df
    high_mask = df_sub > median_df

    mean_low = np.mean(gr_sub[low_mask])
    mean_high = np.mean(gr_sub[high_mask])

    # プールされた標準偏差
    n_low = np.sum(low_mask)
    n_high = np.sum(high_mask)
    var_low = np.var(gr_sub[low_mask], ddof=1)
    var_high = np.var(gr_sub[high_mask], ddof=1)
    pooled_std = np.sqrt(((n_low - 1) * var_low + (n_high - 1) * var_high) / (n_low + n_high - 2))

    if pooled_std < 1e-10:
        return np.nan
    return (mean_high - mean_low) / pooled_std


# --- 勾配サブセットの定義 ---
subsets = {
    "all": np.ones(len(desc_front_abc), dtype=bool),
    "gentle": valid_d & (grad_std_abc < 5),
    "moderate": valid_d & (grad_std_abc >= 5) & (grad_std_abc < 8),
    "steep": valid_d & (grad_std_abc >= 8),
    "hilly": valid_d & (alt_range_abc > 500),
}

for name, subset_mask in subsets.items():
    r_between = between_person_r(subset_mask)
    r_within, p_within = within_person_analysis(subset_mask)
    d_val = cohens_d_median_split(subset_mask)

    printkey(f"desc_between_{name}", r_between)
    printkey(f"desc_within_{name}", r_within)
    printkey(f"desc_d_{name}", d_val)
    print(f"  N({name}) = {np.sum(subset_mask & valid_d)}")

# --- スポーツ別分析 ---
print()
print("  --- Sport-specific between-person correlations ---")

sport_map = {
    "bike": "bike",
    "run": "run",
    "mtb": "mountain bike",
}

for key, sport_name in sport_map.items():
    sport_mask = sport_abc == sport_name
    r_between = between_person_r(sport_mask)
    printkey(f"desc_between_{key}", r_between)
    print(f"  N({key}) = {np.sum(sport_mask & valid_d)}")

print()
print("=" * 60)
print("Study 2 complete.")
print("=" * 60)
