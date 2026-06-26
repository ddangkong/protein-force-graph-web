# Validation — does the physics actually track binding affinity?

The in-app score (coarse per-element LJ + Coulomb) is built for **live intuition**, not prediction.
The fair question is whether *any* of this physics, done properly, tracks real binding data. This
folder answers it with a reproducible study across **eight targets / 184 ligands** — reported
honestly, failures and all.

## Setup

- **Dataset:** the [OpenFF protein–ligand benchmark](https://github.com/openforcefield/protein-ligand-benchmark)
  — eight congeneric series across different protein classes, each with measured affinities
  (IC50 → experimental ΔG) and a prepared receptor: **thrombin** (protease), **mcl1** (PPI),
  **ptp1b** (phosphatase), **p38 / tyk2 / cdk2** (kinases), **tnks2** (PARP glycohydrolase),
  **hif2a** (transcription factor). The same data used to benchmark binding-free-energy methods.
- **Score:** single-trajectory **MM-GBSA**, physics-only, no ML, no fitting —
  `ΔG = E(complex) − E(receptor) − E(ligand)` with **GBn2 implicit solvent**, on the energy-minimized
  complex. For comparison each ligand is also scored with the web app's **coarse LJ + Coulomb**.
- **Pipeline:** `antechamber` (AM1-BCC) → `parmchk2` → `tleap` (ff14SB + phosaa14SB + GAFF2, mbondi3
  radii; structural metal ions stripped) → OpenMM (CUDA) GBn2 minimization + single-point energies.
  Scripts: [`mmgbsa_validate.py`](mmgbsa_validate.py), [`mmgbsa_summary.py`](mmgbsa_summary.py). Raw
  numbers: `*_results.csv`.

## Result

![MM-GBSA vs experimental affinity across eight targets](mmgbsa_targets.png)

| target | class | n | app score (r / ρ) | **MM-GBSA (r / ρ)** |
| --- | --- | :---: | :---: | :---: |
| ptp1b | phosphatase | 22 | 0.58 / 0.38 | **0.69 / 0.70** |
| mcl1 | PPI | 25 | 0.11 / 0.15 | **0.66 / 0.62** |
| tyk2 | kinase | 13 | 0.28 / 0.17 | **0.71 / 0.60** |
| p38 | kinase | 29 | 0.42 / 0.40 | **0.45 / 0.57** |
| tnks2 | PARP | 27 | −0.49 / −0.49 | **0.66 / 0.45** |
| thrombin | protease | 22 | 0.20 / 0.30 | **0.55 / 0.41** |
| hif2a | transcription factor | 36 | 0.10 / 0.19 | 0.13 / 0.09 |
| cdk2 | kinase | 10 | −0.04 / −0.20 | −0.64 / −0.52 |
| **median** | | | **0.14 / 0.18** | **0.60 / 0.51** |

(r = Pearson, ρ = Spearman rank correlation, vs experimental ΔG.)

## What it says — honestly

- On **6 of 8 targets** MM-GBSA recovers a real ranking signal (Spearman **ρ = 0.41 – 0.70**),
  **median ρ ≈ 0.51** across all eight — categorically better than the app's coarse score
  (median ρ ≈ 0.18, never above 0.40). Same physics, taken to a real force field with solvent, goes
  from a qualitative cartoon to a useful ranker — across a protease, a PPI, a phosphatase, three
  kinases, and a glycohydrolase.
- It **fails on 2 of 8**, and we report it rather than cherry-pick: **cdk2** (anti-correlated — the
  *narrowest* affinity range in the set, ~2.8 kcal, with only 10 ligands, so sub-kcal noise dominates)
  and **hif2a** (flat — a hard, very hydrophobic *allosteric* pocket where implicit-solvent MM-GBSA is
  known to struggle). This **target-dependence is exactly the documented behaviour** of single-snapshot
  MM-GBSA; it is a fast estimator, not a universal predictor.

So the coarse browser tool is an honest **intuition** layer, and the underlying physics — taken to a
real force field with solvent — is a **real, if imperfect, affinity ranker**: strong on most targets,
weak on hard ones, and transparent about which is which. Receipts (plots, per-target data, scripts)
are all here.

## Improvement attempts — short MD averaging & entropy (didn't help)

The scores above use one energy-minimized pose per complex. Two standard "cheap" upgrades were tested
on four targets — and **neither reliably helped**:

| target | n | single-snapshot ρ | MD-ensemble ρ (#1) | MD + interaction-entropy ρ (#2) |
| --- | :---: | :---: | :---: | :---: |
| ptp1b | 22 | 0.70 | 0.48 | 0.36 |
| mcl1 | 25 | 0.62 | 0.64 | 0.67 |
| p38 | 29 | 0.57 | 0.54 | 0.35 |
| thrombin | 22 | 0.41 | 0.29 | 0.30 |
| **median** | | **0.59** | 0.51 | 0.35 |

- **#1 short MD-ensemble averaging** (Cα-restrained GBn2 MD, 12 frames): target-dependent — marginally up
  on mcl1, flat on p38, **down** on thrombin and ptp1b; net slightly worse. Short MD adds thermal noise
  that, for sub-kcal congeneric differences, washes out signal more than it averages single-point noise —
  the minimized snapshot is a cleaner, *consistent* reference across ligands.
- **#2 interaction entropy** (Duan 2016, from the same MD): **hurt** (median 0.59 → 0.35) — the known
  instability of IE for flexible complexes.

**Conclusion:** in this cheap regime the **energy-minimized single snapshot is the sweet spot**; reliable
gains need the expensive route (long explicit-solvent MD ensembles, or FEP), out of scope here. A negative
result, reported honestly. Scripts: [`mmgbsa_md.py`](mmgbsa_md.py), [`mmgbsa_compare.py`](mmgbsa_compare.py).

## Honest scope

Single-**snapshot** MM-GBSA — **not** FEP accuracy, and the absolute numbers are **not** ΔG (note the
y-axes: it over-stabilizes by tens of kcal/mol; only *ranking* is meaningful). Short-MD conformational
averaging + an entropy term are the standard next steps to make the ranking more consistent across
targets.

## Reproduce

```bash
# conda env: openmm, ambertools, openff-toolkit, openmmforcefields, rdkit, scipy, matplotlib, pandas, pyyaml
git clone --filter=blob:none --sparse https://github.com/openforcefield/protein-ligand-benchmark ~/pfg-val
cd ~/pfg-val && git sparse-checkout set data
for t in thrombin mcl1 ptp1b p38 tyk2 cdk2 tnks2 hif2a; do python mmgbsa_validate.py $t; done  # resumable
python mmgbsa_summary.py mmgbsa_targets.png thrombin mcl1 ptp1b p38 tyk2 cdk2 tnks2 hif2a
```
