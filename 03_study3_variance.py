#!/usr/bin/env python3
"""
Study 3: Variance Decomposition and Reliability
================================================

分散分解と信頼性の分析．abc_metrics.csv を用いて，
3 つの心拍指標（Cardiac Drift，Gradient Sensitivity，Speed Sensitivity）について
ICC，折半信頼性，分散分解（ブートストラップ CI），交差検証，収束妥当性，
時間安定性，収束分析，ICC 感度分析を実施する．

出力形式: [KEY] value_name = number
"""

import os
import sys
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import Ridge
from sklearn.model_selection import cross_val_score, GroupKFold

warnings.filterwarnings("ignore")
np.random.seed(42)

# ============================================================
# データ読み込み
# ============================================================
# 相対パスを優先し，フォールバックとして絶対パスを使用する
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR_REL = os.path.join(SCRIPT_DIR, "data")
DATA_DIR_ABS = "/Users/hisashi/Desktop/Workspace/Yamap_GPX/data/fitrec"

if os.path.isdir(DATA_DIR_REL):
    DATA_DIR = DATA_DIR_REL
else:
    DATA_DIR = DATA_DIR_ABS

abc_path = os.path.join(DATA_DIR, "abc_metrics.csv")
meixner_path = os.path.join(DATA_DIR, "meixner_4d_indices.csv")

if not os.path.exists(abc_path):
    print(f"ERROR: {abc_path} not found.", file=sys.stderr)
    sys.exit(1)

df_abc = pd.read_csv(abc_path)
print(f"Loaded abc_metrics.csv: {len(df_abc)} rows")

# ルート特徴量
ROUTE_FEATURES = [
    "total_ascent", "total_descent", "alt_range", "max_alt", "min_alt",
    "grad_mean", "grad_std", "pct_climb", "pct_desc", "pct_flat",
    "asc_front", "desc_front", "dur_min",
]

# 分析対象の指標定義（名前，カラム名，短縮名，データソース）
METRICS = [
    ("gacd_rate",           "gacd_rate",           "gacd",     "abc"),
    ("gacd_gradient_coef",  "gacd_gradient_coef",  "gradsens", "abc"),
    ("gacd_speed_coef",     "gacd_speed_coef",     "speedsens","abc"),
]


def get_metric_series(metric_col, source):
    """指標データを取得する．ソースに応じて異なるデータフレームを使用する．"""
    if source == "abc":
        return df_abc[["userId", metric_col] + ROUTE_FEATURES].dropna(subset=[metric_col])
    else:
        raise ValueError(f"Unknown source: {source}")


# ============================================================
# (a) ICC（一方向ランダム効果モデル，ユーザ ≥5 ワークアウト）
# ============================================================
def compute_icc_oneway(data, user_col="userId", value_col="value", min_workouts=5):
    """
    ICC(1,1) を計算する．一方向ランダム効果モデル．
    ユーザごとのワークアウト数が min_workouts 以上のユーザのみ使用する．
    """
    counts = data.groupby(user_col).size()
    valid_users = counts[counts >= min_workouts].index
    sub = data[data[user_col].isin(valid_users)].copy()

    groups = sub.groupby(user_col)[value_col]
    k_groups = groups.ngroups
    n_per_group = groups.size().values
    grand_mean = sub[value_col].mean()
    N = len(sub)

    # グループ間平方和（Between）
    ss_between = sum(
        n * (g_mean - grand_mean) ** 2
        for n, g_mean in zip(n_per_group, groups.mean().values)
    )
    # グループ内平方和（Within）
    ss_within = sum(
        ((g - g.mean()) ** 2).sum()
        for _, g in groups
    )

    df_between = k_groups - 1
    df_within = N - k_groups

    ms_between = ss_between / df_between
    ms_within = ss_within / df_within

    # 不均等サンプルサイズの場合の n0
    n0 = (N - sum(n ** 2 for n in n_per_group) / N) / (k_groups - 1)

    icc = (ms_between - ms_within) / (ms_between + (n0 - 1) * ms_within)
    return icc


print("\n" + "=" * 60)
print("(a) ICC (one-way random, users >= 5 workouts)")
print("=" * 60)

for metric_name, metric_col, short_name, source in METRICS:
    metric_df = get_metric_series(metric_col, source)
    metric_df = metric_df.rename(columns={metric_col: "value"})
    icc_val = compute_icc_oneway(metric_df, min_workouts=5)
    print(f"[KEY] icc_{short_name} = {icc_val:.3f}")


# ============================================================
# (b) 折半信頼性（ユーザ ≥10 ワークアウト）
# ============================================================
def compute_split_half(data, user_col="userId", value_col="value", min_workouts=10):
    """
    折半信頼性を計算する．
    前半の平均と後半の平均のピアソン相関を求め，
    スピアマン＝ブラウン補正を適用する．
    """
    counts = data.groupby(user_col).size()
    valid_users = counts[counts >= min_workouts].index
    sub = data[data[user_col].isin(valid_users)].copy()

    first_half_means = []
    second_half_means = []

    for uid, group in sub.groupby(user_col):
        vals = group[value_col].values
        mid = len(vals) // 2
        first_half_means.append(vals[:mid].mean())
        second_half_means.append(vals[mid:].mean())

    r, _ = stats.pearsonr(first_half_means, second_half_means)
    sb = 2 * r / (1 + r)
    return r, sb


print("\n" + "=" * 60)
print("(b) Split-half reliability (users >= 10 workouts)")
print("=" * 60)

for metric_name, metric_col, short_name, source in METRICS:
    metric_df = get_metric_series(metric_col, source)
    metric_df = metric_df.rename(columns={metric_col: "value"})
    sh_r, sb_val = compute_split_half(metric_df, min_workouts=10)
    print(f"[KEY] sh_{short_name} = {sh_r:.3f}")
    print(f"[KEY] sb_{short_name} = {sb_val:.3f}")


# ============================================================
# (c) 分散分解（ブートストラップ CI，500 反復）
# ============================================================
def compute_variance_decomposition(data, user_col="userId", value_col="value",
                                   route_features=ROUTE_FEATURES, min_workouts=5):
    """
    分散分解を計算する．
    - %Person = ICC
    - %Route = Ridge R² × (1 - ICC) （個人内偏差に対するルート特徴量の説明力）
    - %Occasion = 100 - %Person - %Route
    """
    counts = data.groupby(user_col).size()
    valid_users = counts[counts >= min_workouts].index
    sub = data[data[user_col].isin(valid_users)].copy()

    # ICC を計算
    icc = compute_icc_oneway(sub, user_col=user_col, value_col=value_col, min_workouts=min_workouts)

    # 個人内偏差を計算（各ワークアウトの値 - ユーザ平均）
    user_means = sub.groupby(user_col)[value_col].transform("mean")
    sub = sub.copy()
    sub["deviation"] = sub[value_col] - user_means

    # ルート特徴量が存在するか確認し，欠損値を除去
    available_features = [f for f in route_features if f in sub.columns]
    sub_clean = sub.dropna(subset=available_features + ["deviation"])

    if len(sub_clean) < 10 or len(available_features) == 0:
        return icc * 100, 0.0, (1 - icc) * 100

    X = sub_clean[available_features].values
    y = sub_clean["deviation"].values
    groups = sub_clean[user_col].values

    # GroupKFold CV R²（同一ユーザーの train/test 混在を防止）
    n_groups = len(np.unique(groups))
    n_folds = min(5, n_groups)
    if n_folds < 2:
        route_r2 = 0.0
    else:
        gkf = GroupKFold(n_splits=n_folds)
        ridge = Ridge(alpha=1.0)
        cv_scores = cross_val_score(ridge, X, y, cv=gkf, groups=groups, scoring="r2")
        route_r2 = max(0, np.mean(cv_scores))

    pct_person = icc * 100
    pct_route = route_r2 * (1 - icc) * 100
    pct_occasion = 100 - pct_person - pct_route

    return pct_person, pct_route, pct_occasion


def bootstrap_variance_decomposition(data, user_col="userId", value_col="value",
                                     route_features=ROUTE_FEATURES, min_workouts=5,
                                     n_bootstrap=500):
    """
    ブートストラップによる分散分解の信頼区間を計算する．
    ユーザを復元抽出してリサンプリングする．
    """
    counts = data.groupby(user_col).size()
    valid_users = counts[counts >= min_workouts].index
    sub = data[data[user_col].isin(valid_users)].copy()

    users = sub[user_col].unique()

    boot_person = []
    boot_route = []
    boot_occasion = []

    for i in range(n_bootstrap):
        # ユーザを復元抽出
        sampled_users = np.random.choice(users, size=len(users), replace=True)

        # リサンプリングされたデータを構築（同じユーザが複数回選ばれた場合，異なるユーザ ID を割り当てる）
        frames = []
        for new_id, uid in enumerate(sampled_users):
            user_data = sub[sub[user_col] == uid].copy()
            user_data[user_col] = new_id
            frames.append(user_data)
        boot_data = pd.concat(frames, ignore_index=True)

        p, r, o = compute_variance_decomposition(
            boot_data, user_col=user_col, value_col=value_col,
            route_features=route_features, min_workouts=1  # リサンプリング後は閾値を緩和
        )
        boot_person.append(p)
        boot_route.append(r)
        boot_occasion.append(o)

    return (
        np.percentile(boot_person, [2.5, 97.5]),
        np.percentile(boot_route, [2.5, 97.5]),
        np.percentile(boot_occasion, [2.5, 97.5]),
    )


print("\n" + "=" * 60)
print("(c) Variance decomposition with Bootstrap CI (500 iter)")
print("=" * 60)

for metric_name, metric_col, short_name, source in METRICS:
    metric_df = get_metric_series(metric_col, source)
    metric_df = metric_df.rename(columns={metric_col: "value"})

    pct_p, pct_r, pct_o = compute_variance_decomposition(metric_df)

    ci_person, ci_route, ci_occasion = bootstrap_variance_decomposition(metric_df)

    print(f"[KEY] pct_person_{short_name} = {pct_p:.1f}")
    print(f"[KEY] pct_person_{short_name}_ci_lo = {ci_person[0]:.1f}")
    print(f"[KEY] pct_person_{short_name}_ci_hi = {ci_person[1]:.1f}")
    print(f"[KEY] pct_route_{short_name} = {pct_r:.1f}")
    print(f"[KEY] pct_route_{short_name}_ci_lo = {ci_route[0]:.1f}")
    print(f"[KEY] pct_route_{short_name}_ci_hi = {ci_route[1]:.1f}")
    print(f"[KEY] pct_occasion_{short_name} = {pct_o:.1f}")
    print(f"[KEY] pct_occasion_{short_name}_ci_lo = {ci_occasion[0]:.1f}")
    print(f"[KEY] pct_occasion_{short_name}_ci_hi = {ci_occasion[1]:.1f}")


# ============================================================
# (d) ルート R² 交差検証（5-fold CV，Ridge）
# ============================================================
print("\n" + "=" * 60)
print("(d) Route R² cross-validation (5-fold CV Ridge)")
print("=" * 60)

for metric_name, metric_col, short_name, source in METRICS:
    metric_df = get_metric_series(metric_col, source)
    metric_df = metric_df.rename(columns={metric_col: "value"})

    # ユーザ ≥5 に絞る
    counts = metric_df.groupby("userId").size()
    valid_users = counts[counts >= 5].index
    sub = metric_df[metric_df["userId"].isin(valid_users)].copy()

    # 個人内偏差
    user_means = sub.groupby("userId")["value"].transform("mean")
    sub["deviation"] = sub["value"] - user_means

    available_features = [f for f in ROUTE_FEATURES if f in sub.columns]
    sub_clean = sub.dropna(subset=available_features + ["deviation"])

    X = sub_clean[available_features].values
    y = sub_clean["deviation"].values
    groups = sub_clean["userId"].values

    # GroupKFold: 同一ユーザーの train/test 混在を防止
    n_groups = len(np.unique(groups))
    n_folds = min(5, n_groups)
    gkf = GroupKFold(n_splits=n_folds)
    ridge = Ridge(alpha=1.0)
    cv_scores = cross_val_score(ridge, X, y, cv=gkf, groups=groups, scoring="r2")
    mean_cv_r2 = cv_scores.mean()

    print(f"[KEY] route_r2_cv_{short_name} = {mean_cv_r2:.3f}")


# ============================================================
# (e) 収束妥当性: 個人中央値 vs avg_speed の個人中央値
# ============================================================
print("\n" + "=" * 60)
print("(e) Convergent validity: person-level median vs avg_speed")
print("=" * 60)

for metric_name, metric_col, short_name, source in METRICS:
    metric_df = get_metric_series(metric_col, source)

    # avg_speed がデータに含まれているか確認
    if "avg_speed" not in metric_df.columns:
        # abc から avg_speed を取得
        speed_df = df_abc[["userId", "avg_speed"]].dropna()
        metric_df = metric_df.merge(
            speed_df.drop_duplicates(), on="userId", how="left", suffixes=("", "_y")
        )
        if "avg_speed_y" in metric_df.columns:
            metric_df["avg_speed"] = metric_df["avg_speed_y"]
            metric_df.drop(columns=["avg_speed_y"], inplace=True)

    metric_df = metric_df.dropna(subset=[metric_col, "avg_speed"])

    # 個人レベルの中央値を計算
    person_metric = metric_df.groupby("userId")[metric_col].median()
    person_speed = metric_df.groupby("userId")["avg_speed"].median()

    # 共通ユーザのみ
    common = person_metric.index.intersection(person_speed.index)
    r, _ = stats.pearsonr(person_metric[common], person_speed[common])
    print(f"[KEY] speed_corr_{short_name} = {r:.3f}")


# ============================================================
# (f) 時間安定性: ユーザ ≥10，前 1/3 平均 vs 後 1/3 平均
# ============================================================
print("\n" + "=" * 60)
print("(f) Temporal stability (users >= 10, early 1/3 vs late 1/3)")
print("=" * 60)

# gradient sensitivity について計算
metric_col = "gacd_gradient_coef"
metric_df = get_metric_series(metric_col, "abc")
metric_df = metric_df.rename(columns={metric_col: "value"})

counts = metric_df.groupby("userId").size()
valid_users = counts[counts >= 10].index
sub = metric_df[metric_df["userId"].isin(valid_users)]

early_means = []
late_means = []

for uid, group in sub.groupby("userId"):
    vals = group["value"].values
    n = len(vals)
    third = n // 3
    early_means.append(vals[:third].mean())
    late_means.append(vals[-third:].mean())

temporal_r, _ = stats.pearsonr(early_means, late_means)
print(f"[KEY] temporal_r_gradsens = {temporal_r:.3f}")


# ============================================================
# (g) 収束分析: n_agg ∈ {2,3,5,7,10}
# ============================================================
print("\n" + "=" * 60)
print("(g) Convergence analysis (gradient sensitivity)")
print("=" * 60)

metric_col = "gacd_gradient_coef"
metric_df = get_metric_series(metric_col, "abc")
metric_df = metric_df.rename(columns={metric_col: "value"})

for n_agg in [2, 3, 5, 7, 10]:
    # 各ユーザに 2*n_agg 以上のワークアウトが必要
    counts = metric_df.groupby("userId").size()
    valid_users = counts[counts >= 2 * n_agg].index
    sub = metric_df[metric_df["userId"].isin(valid_users)]

    group1_means = []
    group2_means = []

    for uid, group in sub.groupby("userId"):
        vals = group["value"].values
        np.random.shuffle(vals)
        group1_means.append(vals[:n_agg].mean())
        group2_means.append(vals[n_agg:2 * n_agg].mean())

    r, _ = stats.pearsonr(group1_means, group2_means)
    print(f"[KEY] converge_{n_agg} = {r:.3f}")


# ============================================================
# (h) ICC 感度分析: gradient sensitivity のユーザ閾値別 ICC
# ============================================================
print("\n" + "=" * 60)
print("(h) ICC sensitivity (gradient sensitivity, varying thresholds)")
print("=" * 60)

metric_col = "gacd_gradient_coef"
metric_df = get_metric_series(metric_col, "abc")
metric_df = metric_df.rename(columns={metric_col: "value"})

for thresh in [3, 5, 8, 10, 15]:
    icc_val = compute_icc_oneway(metric_df, min_workouts=thresh)
    print(f"[KEY] icc_thresh_{thresh} = {icc_val:.3f}")

print("\n" + "=" * 60)
print("Study 3 complete.")
print("=" * 60)
