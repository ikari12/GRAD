#!/usr/bin/env python3
"""
Study 1: Construct Validity of Meixner 4D Framework
====================================================
Meixner 4Dフレームワークの構成妥当性を検証するスクリプト．

分析内容:
  a) DI-FI，DI-RI，FI-RI 間のブートストラップ相関（2000回反復）
  b) PCA + 平行分析による因子数の決定
  c) DI，FI，RI の級内相関係数（ICC）
  d) DI の折半信頼性（Spearman-Brown 補正付き）
  e) DI-FI 相関の交差検証（50/50 分割，100 回反復）

出力形式: [KEY] value_name = number
"""

import os
import sys

import numpy as np
from scipy import stats

# ---------------------------------------------------------------------------
# データ読み込み
# ---------------------------------------------------------------------------
DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "meixner_4d_indices.csv")
if not os.path.exists(DATA_PATH):
    print(f"ERROR: data file not found: {DATA_PATH}", file=sys.stderr)
    sys.exit(1)


def load_data(path: str) -> dict:
    """CSVファイルを読み込み，列名をキーとする辞書を返す．"""
    with open(path, "r") as f:
        header = f.readline().strip().split(",")
        rows = [line.strip().split(",") for line in f if line.strip()]
    data = {col: [] for col in header}
    for row in rows:
        for col, val in zip(header, row):
            data[col].append(val)
    return data


def to_float_array(values: list) -> np.ndarray:
    """文字列リストを float 配列に変換する．空文字は NaN にする．"""
    result = []
    for v in values:
        try:
            result.append(float(v))
        except (ValueError, TypeError):
            result.append(np.nan)
    return np.ndarray(len(result), dtype=float, buffer=np.array(result))


def printkey(name: str, value: float, fmt: str = ".4f") -> None:
    """[KEY] 形式で値を出力する．"""
    print(f"[KEY] {name} = {value:{fmt}}")


# ---------------------------------------------------------------------------
# メインデータの準備
# ---------------------------------------------------------------------------
raw = load_data(DATA_PATH)
n_rows = len(raw["id"])

user_ids = np.array(raw["userId"])
di_all = to_float_array(raw["DI"])
fi_all = to_float_array(raw["FI"])
ri_all = to_float_array(raw["RI"])

# ユーザごとのワークアウト数をカウント
unique_users = np.unique(user_ids)
user_counts = {u: np.sum(user_ids == u) for u in unique_users}


def person_medians(metric: np.ndarray, min_workouts: int = 5) -> tuple:
    """
    ユーザごとの中央値を算出する．
    min_workouts 以上のワークアウトを持つユーザのみ対象．
    有効な（NaN でない）値を持つユーザの中央値配列とユーザ ID を返す．
    """
    medians = []
    valid_users = []
    for u in unique_users:
        if user_counts[u] < min_workouts:
            continue
        mask = user_ids == u
        vals = metric[mask]
        vals = vals[~np.isnan(vals)]
        if len(vals) == 0:
            continue
        medians.append(np.median(vals))
        valid_users.append(u)
    return np.array(medians), np.array(valid_users)


# ---------------------------------------------------------------------------
# (a) ブートストラップ相関
# ---------------------------------------------------------------------------
print("=" * 60)
print("(a) Bootstrap Correlation (2000 iterations)")
print("=" * 60)

di_med, users_di = person_medians(di_all, min_workouts=5)
fi_med, users_fi = person_medians(fi_all, min_workouts=5)
ri_med, users_ri = person_medians(ri_all, min_workouts=5)

# DI，FI，RI すべてが有効なユーザの共通集合を求める
common_users = np.intersect1d(np.intersect1d(users_di, users_fi), users_ri)

di_common = np.array([di_med[np.where(users_di == u)[0][0]] for u in common_users])
fi_common = np.array([fi_med[np.where(users_fi == u)[0][0]] for u in common_users])
ri_common = np.array([ri_med[np.where(users_ri == u)[0][0]] for u in common_users])

np.random.seed(42)
n_boot = 2000
n_common = len(common_users)

boot_di_fi = np.zeros(n_boot)
boot_di_ri = np.zeros(n_boot)
boot_fi_ri = np.zeros(n_boot)

for i in range(n_boot):
    idx = np.random.choice(n_common, size=n_common, replace=True)
    boot_di_fi[i] = np.corrcoef(di_common[idx], fi_common[idx])[0, 1]
    boot_di_ri[i] = np.corrcoef(di_common[idx], ri_common[idx])[0, 1]
    boot_fi_ri[i] = np.corrcoef(fi_common[idx], ri_common[idx])[0, 1]

# ポイント推定値
di_fi_r = np.corrcoef(di_common, fi_common)[0, 1]
di_ri_r = np.corrcoef(di_common, ri_common)[0, 1]
fi_ri_r = np.corrcoef(fi_common, ri_common)[0, 1]

# 95% 信頼区間（パーセンタイル法）
di_fi_ci_lo, di_fi_ci_hi = np.percentile(boot_di_fi, [2.5, 97.5])

printkey("di_fi_r", di_fi_r)
printkey("di_fi_ci_lo", di_fi_ci_lo)
printkey("di_fi_ci_hi", di_fi_ci_hi)
printkey("di_ri_r", di_ri_r)
printkey("fi_ri_r", fi_ri_r)

print(f"  N(common users) = {n_common}")

# ---------------------------------------------------------------------------
# (b) PCA + 平行分析
# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("(b) PCA + Parallel Analysis (100 permutations)")
print("=" * 60)

# 共通ユーザの中央値行列を標準化して PCA を実行
X = np.column_stack([di_common, fi_common, ri_common])
X_std = (X - X.mean(axis=0)) / X.std(axis=0)

cov_mat = np.cov(X_std, rowvar=False)
eigenvalues, eigenvectors = np.linalg.eigh(cov_mat)
# 降順にソート
eigenvalues = eigenvalues[::-1]

# 平行分析: ランダムデータの固有値と比較して因子数を決定
np.random.seed(42)
n_perm = 100
random_eigenvalues = np.zeros((n_perm, 3))

for i in range(n_perm):
    random_data = np.random.normal(size=(n_common, 3))
    random_data = (random_data - random_data.mean(axis=0)) / random_data.std(axis=0)
    random_cov = np.cov(random_data, rowvar=False)
    rand_eig = np.linalg.eigh(random_cov)[0][::-1]
    random_eigenvalues[i] = rand_eig

# 95 パーセンタイルの閾値
threshold = np.percentile(random_eigenvalues, 95, axis=0)
n_factors = int(np.sum(eigenvalues > threshold))

var_explained_1 = eigenvalues[0] / np.sum(eigenvalues)

printkey("pca_n_factors", n_factors, ".0f")
printkey("pca_var_explained_1", var_explained_1)

print(f"  Eigenvalues: {eigenvalues}")
print(f"  Threshold (95th percentile): {threshold}")

# ---------------------------------------------------------------------------
# (c) ICC（級内相関係数，一方向ランダム効果モデル）
# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("(c) ICC (one-way random, users with >= 5 workouts)")
print("=" * 60)


def compute_icc_oneway(values: np.ndarray, groups: np.ndarray) -> float:
    """
    一方向ランダム効果モデルの ICC を計算する．
    ICC(1,1) = (MS_between - MS_within) / (MS_between + (n0 - 1) * MS_within)
    n0 はグループサイズの調和平均的な補正値．
    """
    unique_grp = np.unique(groups)
    k = len(unique_grp)

    # グループごとの値を収集
    group_data = []
    for g in unique_grp:
        mask = groups == g
        vals = values[mask]
        vals = vals[~np.isnan(vals)]
        if len(vals) > 0:
            group_data.append(vals)

    k = len(group_data)
    if k < 2:
        return np.nan

    # 全体平均
    all_vals = np.concatenate(group_data)
    grand_mean = np.mean(all_vals)
    N = len(all_vals)

    # グループ間の平方和（SS_between）
    ss_between = sum(len(g) * (np.mean(g) - grand_mean) ** 2 for g in group_data)
    # グループ内の平方和（SS_within）
    ss_within = sum(np.sum((g - np.mean(g)) ** 2) for g in group_data)

    ms_between = ss_between / (k - 1)
    ms_within = ss_within / (N - k)

    # n0 の計算（不均等グループサイズの補正）
    n_i = np.array([len(g) for g in group_data], dtype=float)
    n0 = (N - np.sum(n_i ** 2) / N) / (k - 1)

    icc = (ms_between - ms_within) / (ms_between + (n0 - 1) * ms_within)
    return icc


# 5 ワークアウト以上のユーザのみ対象
valid_mask = np.array([user_counts[u] >= 5 for u in user_ids])
icc_users = user_ids[valid_mask]
icc_di = compute_icc_oneway(di_all[valid_mask], icc_users)
icc_fi = compute_icc_oneway(fi_all[valid_mask], icc_users)
icc_ri = compute_icc_oneway(ri_all[valid_mask], icc_users)

printkey("icc_di", icc_di)
printkey("icc_fi", icc_fi)
printkey("icc_ri", icc_ri)

# ---------------------------------------------------------------------------
# (d) 折半信頼性（DI，10 ワークアウト以上のユーザ）
# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("(d) Split-Half Reliability for DI (users with >= 10 workouts)")
print("=" * 60)

first_half_means = []
second_half_means = []

for u in unique_users:
    if user_counts[u] < 10:
        continue
    mask = user_ids == u
    vals = di_all[mask]
    vals = vals[~np.isnan(vals)]
    if len(vals) < 10:
        continue
    mid = len(vals) // 2
    first_half_means.append(np.mean(vals[:mid]))
    second_half_means.append(np.mean(vals[mid:]))

first_half_means = np.array(first_half_means)
second_half_means = np.array(second_half_means)

sh_di_r = np.corrcoef(first_half_means, second_half_means)[0, 1]
# Spearman-Brown 補正: r_sb = 2 * r / (1 + r)
sb_di = 2 * sh_di_r / (1 + sh_di_r)

printkey("sh_di_r", sh_di_r)
printkey("sb_di", sb_di)
print(f"  N(users with >=10 workouts) = {len(first_half_means)}")

# ---------------------------------------------------------------------------
# (e) DI-FI 相関の交差検証（50/50 分割，100 回反復）
# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("(e) Cross-Validation of DI-FI Correlation (50/50 split, 100 iter)")
print("=" * 60)

np.random.seed(42)
n_cv = 100
cv_corrs = np.zeros(n_cv)

for i in range(n_cv):
    perm = np.random.permutation(n_common)
    half = n_common // 2
    idx_train = perm[:half]
    idx_test = perm[half:]

    # 訓練セットで相関を推定
    r_train = np.corrcoef(di_common[idx_train], fi_common[idx_train])[0, 1]
    # テストセットで相関を評価（相関そのものを検証指標として使用）
    r_test = np.corrcoef(di_common[idx_test], fi_common[idx_test])[0, 1]
    cv_corrs[i] = r_test

printkey("di_fi_cv_mean", np.mean(cv_corrs))
printkey("di_fi_cv_std", np.std(cv_corrs))

print()
print("=" * 60)
print("Study 1 complete.")
print("=" * 60)
