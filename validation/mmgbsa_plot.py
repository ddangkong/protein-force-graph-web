#!/usr/bin/env python
"""Scatter + correlation stats: physics scores vs experimental affinity.
Usage: python mmgbsa_plot.py <results.csv> <target> <out.png>"""
import sys
import numpy as np, pandas as pd
from scipy.stats import pearsonr, spearmanr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

csv = sys.argv[1]
target = sys.argv[2] if len(sys.argv) > 2 else "target"
out = sys.argv[3] if len(sys.argv) > 3 else csv.replace(".csv", ".png")

df = pd.read_csv(csv).dropna()
x = df["dG_exp"].values
n = len(df)
methods = [("crude", "App coarse LJ + Coulomb"),
           ("dE_vac", "Real FF, vacuum (no solvent)"),
           ("dG_mmgbsa", "MM-GBSA (GBn2 implicit solvent)")]

plt.rcParams.update({"font.size": 10, "axes.facecolor": "#fbfcfe"})
fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.4))
for ax, (col, title) in zip(axes, methods):
    y = df[col].values
    r, _ = pearsonr(x, y); rho, _ = spearmanr(x, y)
    ax.scatter(x, y, s=36, c="#2f6bff", edgecolor="white", linewidth=0.6, zorder=3)
    b, a = np.polyfit(x, y, 1); xs = np.array([x.min(), x.max()])
    ax.plot(xs, b * xs + a, color="#ff5a4d", lw=1.7, zorder=2)
    ax.set_title(title, fontsize=11)
    ax.set_xlabel("experimental ΔG  (kcal/mol)")
    ax.set_ylabel(f"{col}  (kcal/mol)")
    ax.text(0.045, 0.955, f"Pearson r = {r:.2f}\nSpearman ρ = {rho:.2f}",
            transform=ax.transAxes, va="top", fontsize=10.5,
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#cbd5e1"))
    ax.grid(alpha=0.25)
fig.suptitle(f"{target} (n={n}) — physics-only scores vs experimental binding affinity",
             fontsize=12.5, weight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.94])
fig.savefig(out, dpi=130)
print("wrote", out)

print(f"\n{target}  n={n}")
print(f"{'method':34s} {'Pearson r':>10} {'R^2':>7} {'Spearman':>9}")
for col, title in methods:
    y = df[col].values; r, _ = pearsonr(x, y); rho, _ = spearmanr(x, y)
    print(f"{title:34s} {r:10.3f} {r*r:7.3f} {rho:9.3f}")
