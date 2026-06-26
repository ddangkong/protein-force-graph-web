#!/usr/bin/env python
"""Aggregate MM-GBSA validation across targets: a per-target correlation table + a grid of
MM-GBSA-vs-experiment scatters. Usage: python mmgbsa_summary.py <out.png> [target ...]"""
import sys, os, glob, math
import numpy as np, pandas as pd
from scipy.stats import pearsonr, spearmanr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HOME = os.path.expanduser("~"); WORKROOT = f"{HOME}/pfg-val/work"
out = sys.argv[1] if len(sys.argv) > 1 else "/mnt/d/ProteinForceGraphWeb/validation/mmgbsa_targets.png"
targets = sys.argv[2:] or sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(f"{WORKROOT}/*/results.csv"))

data = {}
for t in targets:
    p = f"{WORKROOT}/{t}/results.csv"
    if not os.path.exists(p): continue
    df = pd.read_csv(p).dropna()
    if len(df) >= 5: data[t] = df

print(f"{'target':10} {'n':>3} | {'crude r':>8} {'crude rho':>9} | {'MMGBSA r':>8} {'MMGBSA rho':>10}")
rows = []
for t, df in data.items():
    x = df["dG_exp"].values
    cr, _ = pearsonr(x, df["crude"]); crho, _ = spearmanr(x, df["crude"])
    gr, _ = pearsonr(x, df["dG_mmgbsa"]); grho, _ = spearmanr(x, df["dG_mmgbsa"])
    rows.append((cr, crho, gr, grho))
    print(f"{t:10} {len(df):3d} | {cr:8.2f} {crho:9.2f} | {gr:8.2f} {grho:10.2f}")
if rows:
    m = np.array(rows).mean(0)
    print(f"{'MEAN':10} {'':>3} | {m[0]:8.2f} {m[1]:9.2f} | {m[2]:8.2f} {m[3]:10.2f}")

n = len(data); ncol = 2; nrow = math.ceil(n / ncol)
fig, axes = plt.subplots(nrow, ncol, figsize=(8.6, 3.5 * nrow))
axes = np.atleast_1d(axes).ravel()
for ax, (t, df) in zip(axes, data.items()):
    x = df["dG_exp"].values; y = df["dG_mmgbsa"].values
    r, _ = pearsonr(x, y); rho, _ = spearmanr(x, y)
    ax.scatter(x, y, s=30, c="#2f6bff", edgecolor="white", lw=0.5, zorder=3)
    b, a = np.polyfit(x, y, 1); xs = np.array([x.min(), x.max()])
    ax.plot(xs, b * xs + a, color="#ff5a4d", lw=1.5, zorder=2)
    ax.set_title(f"{t}  (n={len(df)})", fontsize=11)
    ax.set_xlabel("experimental ΔG (kcal/mol)"); ax.set_ylabel("MM-GBSA (kcal/mol)")
    ax.text(0.04, 0.95, f"r = {r:.2f}\nρ = {rho:.2f}", transform=ax.transAxes, va="top", fontsize=10,
            bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="#cbd5e1"))
    ax.grid(alpha=0.25)
for ax in axes[n:]:
    ax.axis("off")
fig.suptitle("MM-GBSA (physics only, no ML) vs experimental affinity — OpenFF benchmark",
             fontsize=12.5, weight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.97 if nrow > 1 else 0.92])
fig.savefig(out, dpi=130)
print("wrote", out)
