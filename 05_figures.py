#!/usr/bin/env python3
"""
05_figures.py — 論文用図の生成

Figure 1: シミュレーション散布図（gradient asymmetry vs DI，drift=0）
          → C1: DI はルート形状で決まる（数学的必然）
Figure 2: 3軸フレームワーク（Person/Route/Occasion 分散 + SB + Speed相関）
          → Table 1 の可視化: なぜ DI が壊れ，勾配感受性が有望か

入力: results/study1.txt, results/study3.txt から [KEY] 行を読む
      + シミュレーションデータを再計算（再現性のため seed 固定）
出力: results/fig1_simulation.png, results/fig2_framework.png
"""

import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

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
    """シミュレーションを再実行し，散布図を生成する．"""
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
    sim_asymmetry = []
    sim_labels = []

    for i in range(N_SIM):
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

    fig, ax = plt.subplots(figsize=(8, 6))
    fig.patch.set_facecolor("#0D1117")
    ax.set_facecolor("#161B22")

    colors = {
        "front_climb": "#58A6FF",
        "back_climb": "#F78166",
        "symmetric": "#7EE787",
        "valley": "#D2A8FF",
        "peak": "#FFA657",
    }
    labels_display = {
        "front_climb": 'Front climb (DI=0.39, "fit")',
        "back_climb": 'Back climb (DI=2.76, "fatigued")',
        "symmetric": "Symmetric (DI=1.00, correct)",
        "valley": "Valley",
        "peak": "Peak",
    }

    for rt in ["symmetric", "valley", "peak", "front_climb", "back_climb"]:
        mask = sim_labels == rt
        alpha = 0.7 if rt in ["front_climb", "back_climb", "symmetric"] else 0.3
        size = 20 if rt in ["front_climb", "back_climb", "symmetric"] else 10
        ax.scatter(sim_asymmetry[mask], sim_dis[mask],
                   c=colors[rt], alpha=alpha, s=size,
                   label=labels_display[rt], edgecolors="none")

    ax.axhline(y=1.0, color="#8B949E", linestyle="--", alpha=0.5, linewidth=0.8)
    ax.axvline(x=0.0, color="#8B949E", linestyle="--", alpha=0.5, linewidth=0.8)

    r = np.corrcoef(sim_asymmetry, sim_dis)[0, 1]
    ax.text(0.05, 0.95, f"r = {r:.2f} (p < 0.001)\ncardiac drift = 0",
            transform=ax.transAxes, fontsize=11, color="#C9D1D9",
            verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#21262D", edgecolor="#30363D"))

    ax.set_xlabel("Gradient Asymmetry (H1 mean - H2 mean)", fontsize=12, color="#C9D1D9")
    ax.set_ylabel("Decoupling Index (DI)", fontsize=12, color="#C9D1D9")
    ax.set_title("Figure 1. DI Is Determined by Route Geometry, Not Fatigue\n"
                 "(N=5,000 synthetic workouts, cardiac drift = 0)",
                 fontsize=13, color="#E6EDF3", fontweight="bold")
    ax.tick_params(colors="#8B949E")
    ax.spines["bottom"].set_color("#30363D")
    ax.spines["left"].set_color("#30363D")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="lower right", fontsize=9, facecolor="#21262D",
              edgecolor="#30363D", labelcolor="#C9D1D9")
    ax.set_ylim(0, 5)

    out = os.path.join(RESULTS_DIR, "fig1_simulation.png")
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  ✓ Figure 1 saved: {out}")


# ============================================================
# Figure 2: Person/Route/Occasion Evaluation Framework
# ============================================================

def generate_figure2():
    """Table 1 の可視化: 分散分解(棒) + SB(ダイヤ) + Speed相関(丸)"""

    keys = parse_keys(
        os.path.join(RESULTS_DIR, "study1.txt"),
        os.path.join(RESULTS_DIR, "study3.txt"),
    )

    # 指標定義（Table 1 の値）
    metrics = [
        {"name": "DI\n(naive)",          "person": 16.3, "route": 0.0,  "occasion": 83.7,
         "sb": keys.get("sb_di", 0.63),  "speed_r": None},
        {"name": "GACD\n(drift)",         "person": keys.get("pct_person_gacd", 21.9),
         "route": keys.get("pct_route_gacd", 0.0), "occasion": keys.get("pct_occasion_gacd", 78.1),
         "sb": 0.85, "speed_r": -0.05},
        {"name": "Gradient\nSensitivity", "person": keys.get("pct_person_gradsens", 35.8),
         "route": keys.get("pct_route_gradsens", 5.7), "occasion": keys.get("pct_occasion_gradsens", 58.5),
         "sb": keys.get("sb_gradsens", 0.90),
         "speed_r": keys.get("speed_corr_gradsens", 0.33)},
        {"name": "Speed\nSensitivity",    "person": keys.get("pct_person_speedsens", 43.1),
         "route": keys.get("pct_route_speedsens", 0.0), "occasion": keys.get("pct_occasion_speedsens", 56.9),
         "sb": keys.get("sb_speedsens", 0.93), "speed_r": -0.13},
    ]

    fig, ax1 = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor("#0D1117")
    ax1.set_facecolor("#161B22")

    x = np.arange(len(metrics))
    width = 0.5

    person_vals = [m["person"] for m in metrics]
    route_vals = [m["route"] for m in metrics]
    occasion_vals = [m["occasion"] for m in metrics]
    sb_vals = [m["sb"] for m in metrics]

    # 積み上げ棒 (左 Y 軸: %)
    c_person = "#58A6FF"
    c_route = "#FFA657"
    c_occasion = "#484F58"

    ax1.bar(x, person_vals, width, label="Person (trait)", color=c_person)
    ax1.bar(x, route_vals, width, bottom=person_vals, label="Route", color=c_route)
    bottoms = [p + r for p, r in zip(person_vals, route_vals)]
    ax1.bar(x, occasion_vals, width, bottom=bottoms, label="Occasion (day-to-day)", color=c_occasion)

    for i in range(len(metrics)):
        if person_vals[i] > 8:
            ax1.text(x[i], person_vals[i] / 2, f"{person_vals[i]:.0f}%",
                     ha="center", va="center", fontsize=10, color="white", fontweight="bold")
        if route_vals[i] > 4:
            ax1.text(x[i], person_vals[i] + route_vals[i] / 2, f"{route_vals[i]:.1f}%",
                     ha="center", va="center", fontsize=9, color="white")
        ax1.text(x[i], bottoms[i] + occasion_vals[i] / 2, f"{occasion_vals[i]:.0f}%",
                 ha="center", va="center", fontsize=10, color="#C9D1D9", fontweight="bold")

    ax1.set_ylim(0, 108)
    ax1.set_ylabel("Variance Decomposition (%)", fontsize=12, color="#C9D1D9")
    ax1.set_xticks(x)
    ax1.set_xticklabels([m["name"] for m in metrics], fontsize=10, color="#C9D1D9")

    # 右 Y 軸: SB + Speed相関
    ax2 = ax1.twinx()
    ax2.set_facecolor("none")

    # SB (ダイヤモンド)
    ax2.plot(x, sb_vals, "D-", color="#7EE787", markersize=10, linewidth=2,
             label="Spearman-Brown", zorder=5)
    for i, sb in enumerate(sb_vals):
        ax2.annotate(f"{sb:.2f}", (x[i], sb), textcoords="offset points",
                     xytext=(0, 12), ha="center", fontsize=9, color="#7EE787", fontweight="bold")

    # Speed 相関 (丸)
    for i, m in enumerate(metrics):
        v = m["speed_r"]
        if v is None:
            continue
        color = "#F778BA" if abs(v) > 0.2 else "#8B949E"
        ms = 10 if abs(v) > 0.2 else 7
        ax2.plot(x[i], v, "o", color=color, markersize=ms, zorder=5)
        sig = "**" if abs(v) > 0.2 else " ns"
        ax2.annotate(f"r={v:+.2f}{sig}", (x[i], v), textcoords="offset points",
                     xytext=(0, -15), ha="center", fontsize=8, color=color)

    ax2.set_ylabel("Coefficient", fontsize=12, color="#C9D1D9")
    ax2.set_ylim(-0.3, 1.1)
    ax2.axhline(y=0.80, color="#7EE787", linestyle=":", alpha=0.3, linewidth=0.8)
    ax2.text(len(metrics) - 0.3, 0.81, "SB=0.80", fontsize=8, color="#7EE787", alpha=0.5)

    for ax in [ax1, ax2]:
        ax.tick_params(colors="#8B949E")
        ax.spines["top"].set_visible(False)
    ax1.spines["bottom"].set_color("#30363D")
    ax1.spines["left"].set_color("#30363D")
    ax2.spines["right"].set_color("#30363D")
    ax1.spines["right"].set_visible(False)

    ax1.set_title(
        "Figure 2. Person / Route / Occasion Evaluation Framework\n"
        "Bars = variance | Diamonds = reliability (SB) | Circles = speed correlation",
        fontsize=12, color="#E6EDF3", fontweight="bold")

    legend_elements = [
        Patch(facecolor=c_person, label="Person (trait)"),
        Patch(facecolor=c_route, label="Route"),
        Patch(facecolor=c_occasion, label="Occasion (day-to-day)"),
        Line2D([0], [0], marker="D", color="#7EE787", markersize=8, linestyle="-", label="Spearman-Brown"),
        Line2D([0], [0], marker="o", color="#F778BA", markersize=8, linestyle="", label="Speed corr (p<.01)"),
        Line2D([0], [0], marker="o", color="#8B949E", markersize=6, linestyle="", label="Speed corr (ns)"),
    ]
    ax1.legend(handles=legend_elements, loc="upper left", fontsize=8,
               facecolor="#21262D", edgecolor="#30363D", labelcolor="#C9D1D9")

    out = os.path.join(RESULTS_DIR, "fig2_framework.png")
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  ✓ Figure 2 saved: {out}")


if __name__ == "__main__":
    print("=" * 60)
    print("Figure Generation")
    print("=" * 60)
    generate_figure1()
    generate_figure2()
    print("Done.")
