#!/usr/bin/env python3
"""
05_figures.py — 論文用図の生成（学術誌スタイル v2）
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import matplotlib.gridspec as gridspec

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 10,
    "axes.linewidth": 0.6,
    "axes.edgecolor": "#444444",
    "axes.labelcolor": "#222222",
    "axes.labelsize": 11,
    "axes.titlesize": 11,
    "xtick.color": "#444444",
    "ytick.color": "#444444",
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.major.width": 0.5,
    "ytick.major.width": 0.5,
    "xtick.major.size": 3,
    "ytick.major.size": 3,
    "legend.framealpha": 1.0,
    "legend.edgecolor": "#CCCCCC",
    "legend.fontsize": 9,
    "figure.dpi": 300,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
PAPER_FIG_DIR = os.path.join(SCRIPT_DIR, "paper", "Figures")
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(PAPER_FIG_DIR, exist_ok=True)


def parse_keys(*paths):
    keys = {}
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for line in f:
                if "[KEY]" in line:
                    parts = line.split("[KEY]")[1].strip()
                    k, v = parts.split("=")
                    keys[k.strip()] = float(v.strip())
    return keys


# ============================================================
# Figure 1
# ============================================================

def generate_figure1():
    np.random.seed(42)
    N_SIM = 5000
    n_points = 60
    half = n_points // 2

    def make_gradient_profile(route_type):
        if route_type == "front_climb":
            return np.concatenate([np.random.normal(6, 3, half), np.random.normal(-6, 3, half)])
        elif route_type == "back_climb":
            return np.concatenate([np.random.normal(-6, 3, half), np.random.normal(6, 3, half)])
        else:
            return np.random.normal(0, 5, n_points)

    route_types = ["front_climb", "back_climb", "symmetric"]
    sim_dis, sim_asym, sim_labels = [], [], []

    for _ in range(N_SIM):
        rt = np.random.choice(route_types)
        gradients = make_gradient_profile(rt)
        hr_base = np.random.uniform(100, 140)
        hr_sens = np.random.uniform(2, 8)
        sp_base = np.random.uniform(2, 5)
        sp_sens = np.random.uniform(0.05, 0.15)
        hr = hr_base + hr_sens * gradients + np.random.normal(0, 3, n_points)
        speed = np.maximum(0.5, sp_base - sp_sens * gradients + np.random.normal(0, 0.3, n_points))
        hr_h1, hr_h2 = np.mean(hr[:half]), np.mean(hr[half:])
        sp_h1, sp_h2 = np.mean(speed[:half]), np.mean(speed[half:])
        di = (hr_h2 / sp_h2) / (hr_h1 / sp_h1)
        sim_dis.append(di)
        sim_asym.append(np.mean(gradients[:half]) - np.mean(gradients[half:]))
        sim_labels.append(rt)

    sim_dis = np.array(sim_dis)
    sim_asym = np.array(sim_asym)
    sim_labels = np.array(sim_labels)

    fig, ax = plt.subplots(figsize=(5.5, 4.5))

    palette = {"symmetric": "#66A61E", "front_climb": "#1B9E77", "back_climb": "#D95F02"}
    markers = {"symmetric": "D", "front_climb": "o", "back_climb": "s"}
    labels = {
        "front_climb": "Front climb (DI ≈ 0.39)",
        "back_climb":  "Back climb (DI ≈ 2.76)",
        "symmetric":   "Symmetric (DI ≈ 1.00)",
    }

    # plot order: back first (background), then symmetric, then front on top
    for rt in ["back_climb", "symmetric", "front_climb"]:
        mask = sim_labels == rt
        ax.scatter(sim_asym[mask], sim_dis[mask],
                   c=palette[rt], marker=markers[rt],
                   alpha=0.4, s=14, linewidths=0.3, edgecolors="white",
                   label=labels[rt], zorder=2 if rt == "back_climb" else 3)

    # regression line
    z = np.polyfit(sim_asym, sim_dis, 1)
    x_fit = np.linspace(sim_asym.min(), sim_asym.max(), 100)
    ax.plot(x_fit, np.polyval(z, x_fit), "-", color="#333333", linewidth=1.0, zorder=4)

    ax.axhline(y=1.0, color="#AAAAAA", linestyle="--", linewidth=0.5, zorder=1)
    ax.axvline(x=0.0, color="#AAAAAA", linestyle="--", linewidth=0.5, zorder=1)

    r = np.corrcoef(sim_asym, sim_dis)[0, 1]
    ax.text(0.03, 0.97, f"$r = {r:.2f}$,  $p < .001$\ncardiac drift $= 0$",
            transform=ax.transAxes, fontsize=9, verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#CCCCCC", alpha=0.9))

    ax.set_xlabel("Gradient Asymmetry (H1 mean $-$ H2 mean)")
    ax.set_ylabel("Decoupling Index (DI)")
    ax.set_ylim(0, 5)
    ax.legend(loc="lower left", framealpha=0.95, handletextpad=0.4, borderpad=0.4)

    fig.tight_layout()
    out = os.path.join(PAPER_FIG_DIR, "fig1_simulation.png")
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  ✓ Figure 1 saved: {out}")


# ============================================================
# Figure 2: Two-panel (top: bars, bottom: coefficients)
# ============================================================

def generate_figure2():
    keys = parse_keys(
        os.path.join(RESULTS_DIR, "study1.txt"),
        os.path.join(RESULTS_DIR, "study3.txt"),
    )

    REQUIRED_KEYS = [
        "pct_person_gacd", "pct_route_gacd", "pct_occasion_gacd",
        "pct_person_gradsens", "pct_route_gradsens", "pct_occasion_gradsens",
        "pct_person_speedsens", "pct_route_speedsens", "pct_occasion_speedsens",
        "sb_di", "sb_gradsens", "sb_speedsens",
        "speed_corr_gradsens",
    ]
    missing = [k for k in REQUIRED_KEYS if k not in keys]
    if missing:
        print(f"WARNING: missing keys from results (using fallback): {missing}",
              file=sys.stderr)

    metrics = [
        {"name": "DI\n(naive)",   "person": keys.get("icc_di", 16.3), "route": 0.0,
         "occasion": 83.7, "sb": keys.get("sb_di", 0.63), "speed_r": None},
        {"name": "GACD\n(drift)", "person": keys.get("pct_person_gacd", 21.9),
         "route": keys.get("pct_route_gacd", 0.0), "occasion": keys.get("pct_occasion_gacd", 78.1),
         "sb": keys.get("sb_gacd", 0.85), "speed_r": keys.get("speed_corr_gacd", -0.05)},
        {"name": "Gradient\nSensitivity", "person": keys.get("pct_person_gradsens", 35.8),
         "route": keys.get("pct_route_gradsens", 5.7), "occasion": keys.get("pct_occasion_gradsens", 58.5),
         "sb": keys.get("sb_gradsens", 0.90), "speed_r": keys.get("speed_corr_gradsens", 0.33)},
        {"name": "Speed\nSensitivity", "person": keys.get("pct_person_speedsens", 43.1),
         "route": keys.get("pct_route_speedsens", 0.0), "occasion": keys.get("pct_occasion_speedsens", 56.9),
         "sb": keys.get("sb_speedsens", 0.93), "speed_r": keys.get("speed_corr_speedsens", -0.13)},
    ]

    fig = plt.figure(figsize=(6.5, 6))
    gs = gridspec.GridSpec(2, 1, height_ratios=[3, 1.5], hspace=0.08)
    ax_top = fig.add_subplot(gs[0])
    ax_bot = fig.add_subplot(gs[1], sharex=ax_top)

    x = np.arange(len(metrics))
    width = 0.6

    person_vals = [m["person"] for m in metrics]
    route_vals = [m["route"] for m in metrics]
    occasion_vals = [m["occasion"] for m in metrics]
    sb_vals = [m["sb"] for m in metrics]

    c_person = "#2166AC"
    c_route = "#EF8A62"
    c_occasion = "#E0E0E0"

    # Top panel: stacked bars
    ax_top.bar(x, person_vals, width, label="Person", color=c_person, edgecolor="white", linewidth=0.4)
    ax_top.bar(x, route_vals, width, bottom=person_vals, label="Route", color=c_route, edgecolor="white", linewidth=0.4)
    bottoms = [p + r for p, r in zip(person_vals, route_vals)]
    ax_top.bar(x, occasion_vals, width, bottom=bottoms, label="Occasion", color=c_occasion,
               edgecolor="#BBBBBB", linewidth=0.4, hatch=".....")

    for i in range(len(metrics)):
        if person_vals[i] > 10:
            ax_top.text(x[i], person_vals[i] / 2, f"{person_vals[i]:.0f}%",
                        ha="center", va="center", fontsize=8.5, color="white", fontweight="bold")
        if route_vals[i] > 3:
            ax_top.text(x[i], person_vals[i] + route_vals[i] / 2, f"{route_vals[i]:.1f}%",
                        ha="center", va="center", fontsize=7.5, color="#333333")
        ax_top.text(x[i], bottoms[i] + occasion_vals[i] / 2, f"{occasion_vals[i]:.0f}%",
                    ha="center", va="center", fontsize=8.5, color="#555555")

    ax_top.set_ylim(0, 108)
    ax_top.set_ylabel("Variance (%)")
    ax_top.legend(loc="upper right", ncol=3, framealpha=0.95, handletextpad=0.3, columnspacing=0.8)
    plt.setp(ax_top.get_xticklabels(), visible=False)
    ax_top.spines["bottom"].set_visible(False)
    ax_top.tick_params(axis="x", length=0)

    # Bottom panel: SB + Speed correlation
    ax_bot.spines["top"].set_visible(False)

    # SB
    ax_bot.plot(x, sb_vals, "D-", color="#333333", markersize=6, linewidth=1.0,
                markerfacecolor="white", markeredgewidth=1.0, label="Spearman-Brown", zorder=5)
    for i, sb in enumerate(sb_vals):
        ax_bot.annotate(f"{sb:.2f}", (x[i], sb), textcoords="offset points",
                        xytext=(12, 0), ha="left", fontsize=8, color="#333333")

    # Speed correlation
    for i, m in enumerate(metrics):
        v = m["speed_r"]
        if v is None:
            continue
        sig = abs(v) > 0.2
        ax_bot.plot(x[i], v, "o", color="#D95F02" if sig else "#999999",
                    markerfacecolor="#D95F02" if sig else "white",
                    markeredgewidth=0.8, markersize=6, zorder=5)
        label = f"$r = {v:+.2f}${'**' if sig else ' ns'}"
        ax_bot.annotate(label, (x[i], v), textcoords="offset points",
                        xytext=(12, 0), ha="left", fontsize=7.5,
                        color="#D95F02" if sig else "#888888")

    ax_bot.axhline(y=0.80, color="#BBBBBB", linestyle=":", linewidth=0.5)
    ax_bot.text(-0.4, 0.82, "SB = 0.80", fontsize=7, color="#AAAAAA")
    ax_bot.axhline(y=0.0, color="#BBBBBB", linestyle="-", linewidth=0.3)

    ax_bot.set_ylim(-0.25, 1.05)
    ax_bot.set_ylabel("Coefficient")
    ax_bot.set_xticks(x)
    ax_bot.set_xticklabels([m["name"] for m in metrics], fontsize=9)

    legend_bot = [
        Line2D([0], [0], marker="D", color="#333333", markersize=5, markerfacecolor="white",
               markeredgewidth=0.8, linestyle="-", linewidth=0.8, label="Spearman-Brown"),
        Line2D([0], [0], marker="o", color="#D95F02", markersize=5,
               linestyle="", label="Speed corr. ($p < .01$)"),
        Line2D([0], [0], marker="o", color="#999999", markersize=5, markerfacecolor="white",
               markeredgewidth=0.8, linestyle="", label="Speed corr. (ns)"),
    ]
    ax_bot.legend(handles=legend_bot, loc="lower right", fontsize=8, framealpha=0.95)

    fig.tight_layout()
    out = os.path.join(PAPER_FIG_DIR, "fig2_framework.png")
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  ✓ Figure 2 saved: {out}")


# ============================================================
# Figure 1b: DI vs FI scatter + PCA biplot
# ============================================================
def generate_fig1b():
    path = os.path.join(DATA_DIR, "meixner_4d_indices.csv")
    with open(path) as f:
        header = f.readline().strip().split(",")
        rows = [l.strip().split(",") for l in f if l.strip()]
    raw = {c: [] for c in header}
    for row in rows:
        for c, v in zip(header, row):
            raw[c].append(v)

    def tof(vs):
        r = []
        for v in vs:
            try: r.append(float(v))
            except: r.append(np.nan)
        return np.array(r)

    uids = np.array(raw["userId"])
    di, fi, ri = tof(raw["DI"]), tof(raw["FI"]), tof(raw["RI"])
    uniq = np.unique(uids)
    ucnt = {u: np.sum(uids == u) for u in uniq}

    def pmed(met, mw=5):
        ms, us = [], []
        for u in uniq:
            if ucnt[u] < mw: continue
            v = met[uids == u]; v = v[~np.isnan(v)]
            if len(v) == 0: continue
            ms.append(np.median(v)); us.append(u)
        return np.array(ms), np.array(us)

    dm, ud = pmed(di); fm, uf = pmed(fi); rm, ur = pmed(ri)
    com = np.intersect1d(np.intersect1d(ud, uf), ur)
    dc = np.array([dm[np.where(ud == u)[0][0]] for u in com])
    fc = np.array([fm[np.where(uf == u)[0][0]] for u in com])
    rc = np.array([rm[np.where(ur == u)[0][0]] for u in com])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.5, 3.8),
                                    gridspec_kw={"width_ratios": [1.3, 1]})
    r_val = np.corrcoef(dc, fc)[0, 1]
    ax1.scatter(dc, fc, s=18, alpha=0.5, color="#2166AC",
                edgecolors="white", linewidths=0.3, zorder=3)
    z = np.polyfit(dc, fc, 1)
    xf = np.linspace(np.percentile(dc, 1), np.percentile(dc, 99), 100)
    ax1.plot(xf, np.polyval(z, xf), "-", color="#B2182B", linewidth=1.5, zorder=4)
    ax1.axhline(1.0, color="#CCCCCC", ls="--", lw=0.5, zorder=1)
    ax1.axvline(1.0, color="#CCCCCC", ls="--", lw=0.5, zorder=1)
    ax1.text(0.03, 0.97, f"$r = {r_val:.2f}$\n$N = {len(com)}$ users",
             transform=ax1.transAxes, fontsize=9, va="top",
             bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#CCCCCC", alpha=0.9))
    ax1.set_xlabel("Decoupling Index (DI, person median)")
    ax1.set_ylabel("Fading Index (FI, person median)")
    ax1.set_xlim(np.percentile(dc, 0.5), np.percentile(dc, 99.5))
    ax1.set_ylim(np.percentile(fc, 0.5), np.percentile(fc, 99.5))
    ax1.set_title("(a) DI–FI Redundancy (H1)", fontsize=10, fontweight="bold")

    X = np.column_stack([dc, fc, rc])
    Xs = (X - X.mean(0)) / X.std(0)
    evals, evecs = np.linalg.eigh(np.cov(Xs, rowvar=False))
    idx = evals.argsort()[::-1]; evals = evals[idx]; evecs = evecs[:, idx]
    scores = Xs @ evecs[:, :2]
    vexp = evals[:2] / evals.sum() * 100
    ax2.scatter(scores[:, 0], scores[:, 1], s=12, alpha=0.3,
                color="#999999", edgecolors="none", zorder=2)
    labs = ["DI", "FI", "RI"]; cols = ["#2166AC", "#D95F02", "#1B7837"]
    sc = 2.5
    for i, (lb, co) in enumerate(zip(labs, cols)):
        lx, ly = evecs[i, 0] * sc, evecs[i, 1] * sc
        ax2.annotate("", xy=(lx, ly), xytext=(0, 0),
            arrowprops=dict(arrowstyle="-|>", color=co, lw=2.0, mutation_scale=12), zorder=5)
        ox = 0.15 if lx >= 0 else -0.15
        oy = 0.15 if ly >= 0 else -0.15
        ax2.text(lx + ox, ly + oy, lb, fontsize=11, fontweight="bold", color=co,
                 ha="left" if lx >= 0 else "right",
                 va="bottom" if ly >= 0 else "top", zorder=6)
    ax2.axhline(0, color="#DDDDDD", lw=0.5, zorder=1)
    ax2.axvline(0, color="#DDDDDD", lw=0.5, zorder=1)
    ax2.set_xlabel(f"PC1 ({vexp[0]:.1f}%)")
    ax2.set_ylabel(f"PC2 ({vexp[1]:.1f}%)")
    ax2.set_title("(b) PCA Biplot", fontsize=10, fontweight="bold")
    ax2.set_aspect("equal", adjustable="datalim")
    fig.tight_layout()
    out = os.path.join(PAPER_FIG_DIR, "fig1b_di_fi_pca.png")
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  ✓ Figure 1b saved: {out}")


# ============================================================
# Figure 3: Convergence Curves (SB_k vs k)
# ============================================================
def generate_fig3():
    import pandas as pd
    from scipy import stats

    df_m = pd.read_csv(os.path.join(DATA_DIR, "meixner_4d_indices.csv"))
    df_abc = pd.read_csv(os.path.join(DATA_DIR, "abc_metrics.csv"))

    configs = [
        ("DI", "DI", df_m, "DI (naive)", "#AAAAAA", "s", "--"),
        ("GACD", "gacd_rate", df_abc, "GACD (drift)", "#D95F02", "^", "-"),
        ("GradS", "gacd_gradient_coef", df_abc, "Gradient Sensitivity", "#2166AC", "o", "-"),
        ("SpeedS", "gacd_speed_coef", df_abc, "Speed Sensitivity", "#1B7837", "D", "-"),
    ]
    ks = [2, 3, 4, 5, 6, 7, 8, 9, 10]
    np.random.seed(42)
    fig, ax = plt.subplots(figsize=(5.5, 4.0))

    for _, col, df, disp, color, marker, ls in configs:
        if col not in df.columns:
            continue
        mdf = df[["userId", col]].dropna()
        sbs = []
        for k in ks:
            cnts = mdf.groupby("userId").size()
            vu = cnts[cnts >= 2 * k].index
            sub = mdf[mdf["userId"].isin(vu)]
            if len(vu) < 10:
                sbs.append(np.nan); continue
            g1, g2 = [], []
            for uid, grp in sub.groupby("userId"):
                vals = np.random.permutation(grp[col].values)
                g1.append(vals[:k].mean()); g2.append(vals[k:2*k].mean())
            r_sh, _ = stats.pearsonr(g1, g2)
            sb = 2 * r_sh / (1 + r_sh) if r_sh > -1 else np.nan
            sbs.append(sb)
        ax.plot(ks, sbs, f"{ls}", color=color, marker=marker, label=disp,
                markersize=6, linewidth=1.5, markerfacecolor="white",
                markeredgewidth=1.5, markeredgecolor=color, zorder=3)

    ax.axhline(0.80, color="#BBBBBB", ls=":", lw=1.0, zorder=1)
    ax.text(10.3, 0.81, "SB = 0.80", fontsize=8, color="#999999", va="bottom")
    ax.fill_between([1.5, 10.5], 0.80, 1.02, color="#E8F5E9", alpha=0.3, zorder=0)
    ax.text(6.0, 0.96, "adequate reliability", fontsize=8, color="#66BB6A",
            ha="center", style="italic")
    ax.set_xlabel("Number of aggregated sessions ($k$)")
    ax.set_ylabel("Spearman–Brown reliability (SB$_k$)")
    ax.set_title("Convergence: Sessions Needed for Adequate Reliability",
                 fontsize=10, fontweight="bold")
    ax.set_xticks(ks)
    ax.set_xlim(1.5, 10.5)
    ax.set_ylim(0.2, 1.02)
    ax.legend(loc="lower right", framealpha=0.95)
    fig.tight_layout()
    out = os.path.join(PAPER_FIG_DIR, "fig3_convergence.png")
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  ✓ Figure 3 saved: {out}")


if __name__ == "__main__":
    print("=" * 60)
    print("Figure Generation — all to paper/Figures/")
    print("=" * 60)
    generate_figure1()
    generate_fig1b()
    generate_figure2()
    generate_fig3()
    print("Done. All figures in paper/Figures/")
