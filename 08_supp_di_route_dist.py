#!/usr/bin/env python3
"""
08_supp_di_route_dist.py
========================
Supplementary Figure: DI distribution by route type (front-climb / back-climb / symmetric).

Merges meixner_4d_indices.csv (DI) with abc_metrics.csv (asc_front) on workout id,
then produces a violin + strip plot showing how route geometry drives DI < 1.0.
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

# ── Style (matching 05_figures.py) ──────────────────────────────────────────
for font in ["Helvetica", "Arial", "DejaVu Sans"]:
    try:
        matplotlib.font_manager.findfont(font, fallback_to_default=False)
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = [font]
        break
    except Exception:
        continue

plt.rcParams.update({
    "font.size": 10,
    "axes.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

# ── Paths ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
FIG_DIR = ROOT / "paper" / "Figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# ── Load & merge ────────────────────────────────────────────────────────────
df_4d = pd.read_csv(DATA / "meixner_4d_indices.csv")
df_abc = pd.read_csv(DATA / "abc_metrics.csv")

# Merge on id to get DI + asc_front
df = df_abc.merge(df_4d[["id", "DI"]], on="id", how="inner")
print(f"Merged dataset: {len(df)} workouts")

# ── Classify route types ────────────────────────────────────────────────────
def classify_route(asc_front):
    if asc_front > 0.6:
        return "Front-climb"
    elif asc_front < 0.4:
        return "Back-climb"
    else:
        return "Symmetric"

df["route_type"] = df["asc_front"].apply(classify_route)

# Order for plotting
route_order = ["Front-climb", "Symmetric", "Back-climb"]
colors = {"Front-climb": "#D95F02", "Symmetric": "#66A61E", "Back-climb": "#1B9E77"}

# ── Summary statistics ──────────────────────────────────────────────────────
print("\n=== DI Distribution by Route Type ===")
for rt in route_order:
    sub = df.loc[df["route_type"] == rt, "DI"]
    print(f"  {rt:15s}: N={len(sub):5d}, "
          f"mean={sub.mean():.3f}, median={sub.median():.3f}, "
          f"SD={sub.std():.3f}, IQR=[{sub.quantile(0.25):.3f}, {sub.quantile(0.75):.3f}]")

overall = df["DI"]
print(f"  {'Overall':15s}: N={len(overall):5d}, "
      f"mean={overall.mean():.3f}, median={overall.median():.3f}")

# ── Figure ──────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(5.5, 4.0))

# Prepare data in order
data_groups = [df.loc[df["route_type"] == rt, "DI"].dropna().values for rt in route_order]
positions = [1, 2, 3]

# Violin plot
parts = ax.violinplot(data_groups, positions=positions, showmedians=False,
                       showextrema=False, widths=0.7)
for i, (body, rt) in enumerate(zip(parts["bodies"], route_order)):
    body.set_facecolor(colors[rt])
    body.set_alpha(0.5)
    body.set_edgecolor("none")

# Box plot overlay (thin)
bp = ax.boxplot(data_groups, positions=positions, widths=0.15, 
                patch_artist=True, showfliers=False,
                medianprops=dict(color="white", linewidth=1.5),
                boxprops=dict(linewidth=0.8),
                whiskerprops=dict(linewidth=0.8),
                capprops=dict(linewidth=0.8))
for i, (patch, rt) in enumerate(zip(bp["boxes"], route_order)):
    patch.set_facecolor(colors[rt])
    patch.set_alpha(0.9)

# Reference line at DI = 1.0
ax.axhline(y=1.0, color="#888888", linestyle="--", linewidth=0.8, zorder=0, label="DI = 1.0")

# Annotations: N, %, and median
ax.set_ylim(0.15, 1.85)
for i, rt in enumerate(route_order):
    sub = df.loc[df["route_type"] == rt, "DI"]
    n = len(sub)
    med = sub.median()
    pct = 100.0 * n / len(df)
    ax.text(positions[i], 1.82, f"N={n} ({pct:.0f}%)\nMd={med:.2f}",
            ha="center", va="top", fontsize=8, color=colors[rt], fontweight="bold")

ax.set_xticks(positions)
ax.set_xticklabels(route_order, fontsize=10)
ax.set_ylabel("Decoupling Index (DI)", fontsize=11)
ax.set_title("DI Distribution by Route Type", fontsize=12, fontweight="bold", pad=10)
ax.legend(loc="lower right", fontsize=8, frameon=False)

plt.tight_layout()
out_path = FIG_DIR / "figS_di_route_distribution.png"
fig.savefig(out_path, dpi=300)
print(f"\nFigure saved: {out_path}")
plt.close()
