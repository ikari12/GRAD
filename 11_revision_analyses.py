#!/usr/bin/env python3
"""
Revision Analyses: Reviewer-Requested Additions
================================================
査読コメント（R1/R2/R3 + メタレビュー）で追加を求められた解析．

分析内容:
  a) 平行分析のブートストラップ推論（PC2 と閾値の差の分布，保持判定の安定性）
  b) DI-FI のみの PCA（RI を ICC=0.10 のため除外したロバストネスチェック）
  c) 降下配置の勾配層別サイズと調整効果の Fisher z 検定
  d) データ来歴の監査（行数・ユーザ数・速度補完率）

出力形式: [KEY] value_name = number
"""

import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

BASE = os.path.dirname(os.path.abspath(__file__))
IDX_PATH = os.path.join(BASE, "data", "meixner_4d_indices.csv")
ABC_PATH = os.path.join(BASE, "data", "abc_metrics.csv")

for p in (IDX_PATH, ABC_PATH):
    if not os.path.exists(p):
        print(f"ERROR: data file not found: {p}", file=sys.stderr)
        sys.exit(1)

SEED = 42
N_BOOT = 2000
N_PERM = 1000


def printkey(name: str, value: float, fmt: str = ".4f") -> None:
    """[KEY] 形式で値を出力する．"""
    print(f"[KEY] {name} = {value:{fmt}}")


def header(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def parallel_threshold(n_obs: int, n_var: int, rng: np.random.Generator) -> np.ndarray:
    """平行分析: ランダム正規データの固有値の 95 パーセンタイルを返す．"""
    eigs = np.empty((N_PERM, n_var))
    for i in range(N_PERM):
        rand = rng.standard_normal((n_obs, n_var))
        rand = (rand - rand.mean(axis=0)) / rand.std(axis=0)
        eigs[i] = np.linalg.eigvalsh(np.cov(rand, rowvar=False))[::-1]
    return np.percentile(eigs, 95, axis=0)


def observed_eigenvalues(X: np.ndarray) -> np.ndarray:
    """列標準化したうえで相関行列の固有値を降順で返す．"""
    Xs = (X - X.mean(axis=0)) / X.std(axis=0)
    return np.linalg.eigvalsh(np.cov(Xs, rowvar=False))[::-1]


# ---------------------------------------------------------------------------
# データ準備: ユーザ単位の中央値（≥5 ワークアウト）
# ---------------------------------------------------------------------------
idx = pd.read_csv(IDX_PATH)
counts = idx.groupby("userId").size()
eligible = counts[counts >= 5].index
sub = idx[idx.userId.isin(eligible)]

med = sub.groupby("userId")[["DI", "FI", "RI"]].median()
med_full = med.dropna()          # DI/FI/RI がすべて有効なユーザ
med_difi = med[["DI", "FI"]].dropna()

header("(d) Data provenance audit")
print(f"  CSV rows                     = {len(idx)}")
print(f"  CSV unique users             = {idx.userId.nunique()}")
print(f"  Users with >= 5 workouts     = {len(eligible)}")
print(f"  PCA sample (DI+FI+RI valid)  = {len(med_full)}")
print(f"  PCA sample (DI+FI valid)     = {len(med_difi)}")
printkey("audit_n_workouts", len(idx), ".0f")
printkey("audit_n_users", idx.userId.nunique(), ".0f")
printkey("audit_n_pca_users", len(med_full), ".0f")
printkey("audit_n_pca_users_difi", len(med_difi), ".0f")

# has_speed=0 は Haversine 由来の速度で補完されたワークアウト（R2 Q1）
if "has_speed" in idx.columns:
    n_imputed = int((idx.has_speed == 0).sum())
    pct_imputed = 100.0 * n_imputed / len(idx)
    print(f"  Haversine-imputed speed      = {n_imputed} ({pct_imputed:.2f}%)")
    printkey("audit_n_haversine_imputed", n_imputed, ".0f")
    printkey("audit_pct_haversine_imputed", pct_imputed, ".2f")

# ---------------------------------------------------------------------------
# (a) 平行分析のブートストラップ推論
# ---------------------------------------------------------------------------
header("(a) Parallel analysis with bootstrap inference (DI, FI, RI)")

X_full = med_full.to_numpy()
n_users, n_var = X_full.shape
rng = np.random.default_rng(SEED)

eig_obs = observed_eigenvalues(X_full)
thr_obs = parallel_threshold(n_users, n_var, rng)

print(f"  N users = {n_users}")
for j in range(n_var):
    print(f"  PC{j+1}: eigenvalue = {eig_obs[j]:.4f}   parallel 95% = {thr_obs[j]:.4f}"
          f"   margin = {eig_obs[j] - thr_obs[j]:+.4f}")
    printkey(f"pca_eig_{j+1}", eig_obs[j])
    printkey(f"pca_thr_{j+1}", thr_obs[j])
    printkey(f"pca_margin_{j+1}", eig_obs[j] - thr_obs[j])

printkey("pca_n_factors_point", int(np.sum(eig_obs > thr_obs)), ".0f")

# ユーザをリサンプリングし，固有値・閾値・保持判定の分布を得る
boot_eig = np.empty((N_BOOT, n_var))
boot_margin = np.empty((N_BOOT, n_var))
boot_nfac = np.empty(N_BOOT, dtype=int)

for b in range(N_BOOT):
    pick = rng.integers(0, n_users, size=n_users)
    Xb = X_full[pick]
    # 標準偏差ゼロの縮退標本は除外して再抽出する
    if np.any(Xb.std(axis=0) == 0):
        continue
    eb = observed_eigenvalues(Xb)
    # 閾値は標本サイズのみに依存するため観測標本の値を再利用する
    boot_eig[b] = eb
    boot_margin[b] = eb - thr_obs
    boot_nfac[b] = int(np.sum(eb > thr_obs))

print()
for j in range(n_var):
    lo, hi = np.percentile(boot_eig[:, j], [2.5, 97.5])
    mlo, mhi = np.percentile(boot_margin[:, j], [2.5, 97.5])
    print(f"  PC{j+1}: eigenvalue 95% CI [{lo:.4f}, {hi:.4f}]"
          f"   margin 95% CI [{mlo:+.4f}, {mhi:+.4f}]")
    printkey(f"pca_eig_{j+1}_ci_lo", lo)
    printkey(f"pca_eig_{j+1}_ci_hi", hi)
    printkey(f"pca_margin_{j+1}_ci_lo", mlo)
    printkey(f"pca_margin_{j+1}_ci_hi", mhi)

pc2_retained_pct = 100.0 * np.mean(boot_margin[:, 1] > 0)
print()
print(f"  Bootstrap replicates retaining PC2 = {pc2_retained_pct:.1f}%")
print(f"  Modal number of factors retained   = {stats.mode(boot_nfac, keepdims=False).mode}")
printkey("pca_pc2_retained_pct", pc2_retained_pct, ".1f")
printkey("pca_nfactors_1_pct", 100.0 * np.mean(boot_nfac == 1), ".1f")
printkey("pca_nfactors_2_pct", 100.0 * np.mean(boot_nfac == 2), ".1f")

# ---------------------------------------------------------------------------
# (b) DI-FI のみの PCA（R1 提案 5）
# ---------------------------------------------------------------------------
header("(b) PCA on DI and FI only (RI excluded: ICC = 0.10)")

X_difi = med_difi.to_numpy()
n_difi = len(X_difi)
rng2 = np.random.default_rng(SEED)

eig_difi = observed_eigenvalues(X_difi)
thr_difi = parallel_threshold(n_difi, 2, rng2)

print(f"  N users = {n_difi}")
for j in range(2):
    print(f"  PC{j+1}: eigenvalue = {eig_difi[j]:.4f}   parallel 95% = {thr_difi[j]:.4f}"
          f"   margin = {eig_difi[j] - thr_difi[j]:+.4f}")
    printkey(f"pca_difi_eig_{j+1}", eig_difi[j])
    printkey(f"pca_difi_thr_{j+1}", thr_difi[j])

printkey("pca_difi_n_factors", int(np.sum(eig_difi > thr_difi)), ".0f")
printkey("pca_difi_var_explained_1", eig_difi[0] / eig_difi.sum())

r_difi = np.corrcoef(X_difi[:, 0], X_difi[:, 1])[0, 1]
printkey("pca_difi_r", r_difi)
printkey("pca_difi_shared_var_pct", 100.0 * r_difi ** 2, ".1f")

# ---------------------------------------------------------------------------
# (c) 降下配置: 層別サイズと調整効果の検定（R2 W6）
# ---------------------------------------------------------------------------
header("(c) Descent placement: subgroup sizes and moderation test")

abc = pd.read_csv(ABC_PATH)
d = abc[["desc_front", "gacd_rate", "grad_std", "sport"]].dropna()


def pearson_with_n(frame: pd.DataFrame) -> tuple:
    """Pearson r，p 値，標本サイズを返す．"""
    if len(frame) < 4:
        return np.nan, np.nan, len(frame)
    r, p = stats.pearsonr(frame.desc_front, frame.gacd_rate)
    return r, p, len(frame)


strata = {
    "gentle": d[d.grad_std < 5],
    "moderate": d[(d.grad_std >= 5) & (d.grad_std < 8)],
    "steep": d[d.grad_std >= 8],
}

results = {}
for name, frame in strata.items():
    r, p, n = pearson_with_n(frame)
    results[name] = (r, n)
    print(f"  {name:9s}: r = {r:+.4f}   p = {p:.3e}   n = {n}")
    printkey(f"desc_{name}_r", r)
    printkey(f"desc_{name}_p", p, ".3e")
    printkey(f"desc_{name}_n", n, ".0f")

# Fisher の z 変換による 2 相関係数の差の検定（gentle vs moderate）
r1, n1 = results["gentle"]
r2, n2 = results["moderate"]
z1, z2 = np.arctanh(r1), np.arctanh(r2)
se_diff = np.sqrt(1.0 / (n1 - 3) + 1.0 / (n2 - 3))
z_stat = (z2 - z1) / se_diff
p_diff = 2 * (1 - stats.norm.cdf(abs(z_stat)))

print()
print(f"  Fisher z test (gentle vs moderate): z = {z_stat:.4f}, p = {p_diff:.4f}")
printkey("desc_moderation_z", z_stat)
printkey("desc_moderation_p", p_diff)

print()
for sport in ["bike", "run", "mountain bike"]:
    frame = d[d.sport == sport]
    r, p, n = pearson_with_n(frame)
    print(f"  {sport:14s}: r = {r:+.4f}   p = {p:.3e}   n = {n}")
    printkey(f"desc_sport_{sport.replace(' ', '_')}_r", r)
    printkey(f"desc_sport_{sport.replace(' ', '_')}_n", n, ".0f")

print()
print("=" * 60)
print("Revision analyses complete.")
print("=" * 60)
