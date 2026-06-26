#!/usr/bin/env python
"""Compare single-snapshot vs MD-averaged (#1) vs MD-averaged+interaction-entropy (#2) MM-GBSA,
per target, against experimental affinity. Usage: python mmgbsa_compare.py [target ...]"""
import sys, os
import numpy as np, pandas as pd
from scipy.stats import pearsonr, spearmanr

HOME = os.path.expanduser("~"); W = f"{HOME}/pfg-val/work"
targets = sys.argv[1:] or sorted(d for d in os.listdir(W) if os.path.exists(f"{W}/{d}/results_md.csv"))

print(f"{'target':9} {'n':>3} |  single r/rho |  MD-avg r/rho |  MD+IE r/rho")
S = {"single": [], "md": [], "ie": []}
for t in targets:
    s, m = f"{W}/{t}/results.csv", f"{W}/{t}/results_md.csv"
    if not (os.path.exists(s) and os.path.exists(m)): continue
    df = pd.read_csv(s).merge(pd.read_csv(m), on="name").dropna()
    if len(df) < 5: continue
    x = df["dG_exp"].values
    def rr(c): return pearsonr(x, df[c])[0], spearmanr(x, df[c])[0]
    a, b, c = rr("dG_mmgbsa"), rr("dG_md"), rr("dG_ie")
    S["single"].append(a[1]); S["md"].append(b[1]); S["ie"].append(c[1])
    print(f"{t:9} {len(df):3d} |  {a[0]:5.2f} {a[1]:5.2f}  |  {b[0]:5.2f} {b[1]:5.2f}  |  {c[0]:5.2f} {c[1]:5.2f}")
if S["single"]:
    print(f"{'MEDIAN rho':9} {'':>3} |        {np.median(S['single']):5.2f}  |        "
          f"{np.median(S['md']):5.2f}  |        {np.median(S['ie']):5.2f}")
