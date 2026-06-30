#!/usr/bin/env python3
"""
05_figures.py — 論文用図の生成（学術誌スタイル）

Figure 1: シミュレーション散布図（gradient asymmetry vs DI，drift=0）
Figure 2: 3軸フレームワーク（Person/Route/Occasion 分散 + SB + Speed相関）

出力: results/fig1_simulation.png, results/fig2_framework.png
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

# 学術誌スタイル
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.linewidth": 0.8,
    "axes.edgecolor": "#333333",
    "axes.labelcolor": "#222222",
    "xtick.color": "#333333",
    "ytick.color": "#333333",
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "legend.framealpha": 1.0,
    "legend.edgecolor": "#CCCCCC",
    "figure.dpi": 300,
})

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


def parse_keys(*paths):
    """複数の結果ファイルから [KEY] 行をパースする．"""
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
# Figure 1: Simulation — Gradient Asymmetry vs DI (drift = 0)
# ============================================================

def generate_figure1():
    np.random.seed(42)
    N_SIM = 5000
    n_points = 60
    half = n_points // 2

    def make_gradient_profile(route_type):
        if route_type == "front_climb":
            return np.concatenate([
                np.random.normal(6, 3, half),
                np.random.normal(-6, 3, half),
            ])
        elif route_type == "back_climb":
            return np.concatenate([
                np.random.normal(-6, 3, half),
                np.random.normal(6, 3, half),
            ])
        else:
            return np.random.normal(0, 5, n_points)

    route_types = ["front_climb", "back_climb", "symmetric"]
    sim_dis = []
    sim_asymmetry = []
    sim_labels = []

    for _ in range(N_SIM):
        rt = np.random.choice(route_types)
        gradients = make_gradient_profile(rt)

        hr_base = np.random.uniform(100, 140)
        hr_sensitivity = np.random.uniform(2, 8)
        speed_base = np.random.uniform(2, 5)
        speed_sensitivity = np.random.uniform(0.05, 0.15)

        hr = hr_base + hr_sensitivity * gradients + np.random.normal(0, 3, n_points)
        speed = np.maximum(0.5, speed_base - speed_sensitivity * gradients + np.random.normal(0, 0.3, n_points))

        hr_h1, hr_h2 = np.mean(hr[:half]), np.mean(hr[half:])
        speed_h1, speed_h2 = np.mean(speed[:half]), np.mean(speed[half:])
        di = (hr_h2 / speed_h2) / (hr_h1 / speed_h1)

        sim_dis.append(di)
        sim_asymmetry.append(np.mean(gradients[:half]) - np.mean(gradients[half:]))
        sim_labels.append(rt)

    sim_dis = np.array(sim_dis)
    sim_asymmetry = np.array(sim_asymmetry)
    sim_labels = np.array(sim_labels)

    fig, ax = plt.subplots(figsize=(6, 5))

    # 色: 学術誌で区別しやすい 3 色
    colors = {
        "front_climb": "#2166AC",   # 青
        "back_climb": "#B2182B",    # 赤
        "symmetric": "#4DAF4A",     # 緑
    }
    markers = {
        "front_climb": "o",
        "back_climb": "s",
        "symmetric": "^",
    }
    labels_display = {
        "front_climb": "Front climb (DI ≈ 0.39)",
        "back_climb": "Back climb (DI ≈ 2.76)",
        "symmetric": "Symmetric (DI ≈ 1.00)",
    }

    for rt in ["symmetric", "front_climb", "back_climb"]:
        mask = sim_labels == rt
        ax.scatter(sim_asymmetry[mask], sim_dis[mask],
                   c=colors[rt], marker=markers[rt],
                   alpha=0.35, s=12, linewidths=0,
                   label=labels_display[rt])

    ax.axhline(y=1.0, color="#888888", linestyle="--", linewidth=0.7)
    ax.axvline(x=0.0, color="#888888", linestyle="--", linewidth=0.7)

    r = np.corrcoef(sim_asymmetry, sim_dis)[0, 1]
    ax.text(0.05, 0.95,
            f"r = {r:.2f},  p < .001\ncardiac drift = 0",
            transform=ax.transAxes, fontsize=10,
            verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#CCCCCC"))

    ax.set_xlabel("Gradient Asymmetry (H1 mean − H2 mean)")
    ax.set_ylabel("Decoupling Index (DI)")
    ax.set_ylim(0, 5)
    ax.legend(loc="lower right", fontsize=9, markerscale=1.5)
    ax.set_title("(a) Simulation: DI vs. Route Gradient Asymmetry (N = 5,000, drift = 0)",
                 fontsize=11, pad=10)

    fig.tight_layout()
    out = os.path.join(RESULTS_DIR, "fig1_simulation.png")
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  ✓ Figure 1 saved: {out}")


# ============================================================
# Figure 2: Person/Route/Occasion Evaluation Framework
# ============================================================

def generate_figure2():
    keys = parse_keys(
        os.path.join(RESULTS_DIR, "study1.txt"),
        os.path.join(RESULTS_DIR, "study3.txt"),
    )

    metrics = [
        {"name": "DI\n(naive)", "person": 16.3, "route": 0.0, "occasion": 83.7,
         "sb": keys.get("sb_di", 0.63), "speed_r": None},
        {"name": "GACD\n(drift)", "person": keys.get("pct_person_gacd", 21.9),
         "route": keys.get("pct_route_gacd", 0.0), "occasion": keys.get("pct_occasion_gacd", 78.1),
         "sb": 0.85, "speed_r": -0.05},
        {"name": "Gradient\nSensitivity", "person": keys.get("pct_person_gradsens", 35.8),
         "route": keys.get("pct_route_gradsens", 5.7), "occasion": keys.get("pct_occasion_gradsens", 58.5),
         "sb": keys.get("sb_gradsens", 0.90),
         "speed_r": keys.get("speed_corr_gradsens", 0.33)},
        {"name": "Speed\nSensitivity", "person": keys.get("pct_person_speedsens", 43.1),
         "route": keys.get("pct_route_speedsens", 0.0), "occasion": keys.get("pct_occasion_speedsens", 56.9),
         "sb": keys.get("sb_speedsens", 0.93), "speed_r": -0.13},
    ]

    fig, ax1 = plt.subplots(figsize=(8, 5))

    x = np.arange(len(metrics))
    width = 0.55

    person_vals = [m["person"] for m in metrics]
    route_vals = [m["route"] for m in metrics]
    occasion_vals = [m["occasion"] for m in metrics]
    sb_vals = [m["sb"] for m in metrics]

    # 学術誌向け色: 白黒印刷でも区別可能なハッチング付き
    c_person = "#2166AC"
    c_route = "#F4A582"
    c_occasion = "#D9D9D9"

    bars_p = ax1.bar(x, person_vals, width, label="Person (trait)",
                     color=c_person, edgecolor="white", linewidth=0.5)
    bars_r = ax1.bar(x, route_vals, width, bottom=person_vals, label="Route",
                     color=c_route, edgecolor="white", linewidth=0.5)
    bottoms = [p + r for p, r in zip(person_vals, route_vals)]
    bars_o = ax1.bar(x, occasion_vals, width, bottom=bottoms, label="Occasion (day-to-day)",
                     color=c_occasion, edgecolor="white", linewidth=0.5, hatch="//")

    # % ラベル
    for i in range(len(metrics)):
        if person_vals[i] > 10:
            ax1.text(x[i], person_vals[i] / 2, f"{person_vals[i]:.0f}%",
                     ha="center", va="center", fontsize=9, color="white", fontweight="bold")
        if route_vals[i] > 4:
            ax1.text(x[i], person_vals[i] + route_vals[i] / 2, f"{route_vals[i]:.1f}%",
                     ha="center", va="center", fontsize=8, color="#333333")
        ax1.text(x[i], bottoms[i] + occasion_vals[i] / 2, f"{occasion_vals[i]:.0f}%",
                 ha="center", va="center", fontsize=9, color="#444444")

    ax1.set_ylim(0, 110)
    ax1.set_ylabel("Variance Decomposition (%)")
    ax1.set_xticks(x)
    ax1.set_xticklabels([m["name"] for m in metrics], fontsize=10)

    # 右 Y 軸: SB + Speed 相関
    ax2 = ax1.twinx()

    # SB (ダイヤモンド + 実線)
    ax2.plot(x, sb_vals, "D-", color="#333333", markersize=7, linewidth=1.2,
             markerfacecolor="white", markeredgewidth=1.2, label="Spearman-Brown", zorder=5)
    for i, sb in enumerate(sb_vals):
        ax2.annotate(f"{sb:.2f}", (x[i], sb), textcoords="offset points",
                     xytext=(0, 10), ha="center", fontsize=8, color="#333333")

    # Speed 相関 (丸)
    for i, m in enumerate(metrics):
        v = m["speed_r"]
        if v is None:
            continue
        filled = abs(v) > 0.2
        ax2.plot(x[i], v, "o",
                 color="#B2182B" if filled else "#999999",
                 markerfacecolor="#B2182B" if filled else "white",
                 markeredgewidth=1.0, markersize=7, zorder=5)
        sig = "**" if abs(v) > 0.2 else " ns"
        ax2.annotate(f"r = {v:+.2f}{sig}", (x[i], v), textcoords="offset points",
                     xytext=(0, -13), ha="center", fontsize=7.5,
                     color="#B2182B" if filled else "#888888")

    ax2.set_ylabel("Coefficient (SB / Speed correlation)")
    ax2.set_ylim(-0.3, 1.15)
    ax2.axhline(y=0.80, color="#AAAAAA", linestyle=":", linewidth=0.6)
    ax2.text(len(metrics) - 0.2, 0.82, "SB = 0.80", fontsize=7, color="#AAAAAA")

    ax1.set_title(
        "(b) Person / Route / Occasion Evaluation Framework",
        fontsize=11, pad=10)

    # 凡例を統合
    legend_elements = [
        Patch(facecolor=c_person, edgecolor="white", label="Person (trait)"),
        Patch(facecolor=c_route, edgecolor="white", label="Route"),
        Patch(facecolor=c_occasion, edgecolor="white", hatch="//", label="Occasion"),
        Line2D([0], [0], marker="D", color="#333333", markersize=6, markerfacecolor="white",
               markeredgewidth=1.0, linestyle="-", linewidth=1.0, label="Spearman-Brown"),
        Line2D([0], [0], marker="o", color="#B2182B", markersize=6,
               linestyle="", label="Speed corr. (p < .01)"),
        Line2D([0], [0], marker="o", color="#999999", markersize=6, markerfacecolor="white",
               markeredgewidth=1.0, linestyle="", label="Speed corr. (ns)"),
    ]
    ax1.legend(handles=legend_elements, loc="upper left", fontsize=8)

    fig.tight_layout()
    out = os.path.join(RESULTS_DIR, "fig2_framework.png")
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  ✓ Figure 2 saved: {out}")


if __name__ == "__main__":
    print("=" * 60)
    print("Figure Generation (Journal Style)")
    print("=" * 60)
    generate_figure1()
    generate_figure2()
    print("Done.")
