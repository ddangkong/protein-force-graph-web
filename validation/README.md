# Validation — does the physics actually track binding affinity?

The in-app score (coarse per-element LJ + Coulomb) is built for **live intuition**, not prediction.
The fair question is whether *any* of this physics, done properly, tracks real binding data. This
folder answers it with a small, fully reproducible study.

## Setup

- **Dataset:** the [OpenFF protein–ligand benchmark](https://github.com/openforcefield/protein-ligand-benchmark)
  **thrombin** set — 22 congeneric ligands with measured IC50 (converted to experimental ΔG over a
  ~5.8 kcal/mol range) and a prepared receptor. This is the same kind of data used to benchmark
  binding-free-energy methods.
- **Three physics-only scores** per ligand (no ML, no fitting):
  1. **App coarse FF** — the exact per-element LJ + RDIE-Coulomb interaction the web app shows live.
  2. **Real FF, vacuum** — ff14SB (protein) + GAFF2/AM1-BCC (ligand) interaction energy, no solvent.
  3. **MM-GBSA** — the same real force field with **GBn2 implicit solvent**; single-trajectory
     `ΔG = E(complex) − E(receptor) − E(ligand)` on the energy-minimized complex.
- **Pipeline:** `antechamber` (AM1-BCC) → `parmchk2` → `tleap` (mbondi3 radii) → OpenMM (CUDA) GBn2
  minimization + single-point energies. Scripts: [`mmgbsa_validate.py`](mmgbsa_validate.py) and
  [`mmgbsa_plot.py`](mmgbsa_plot.py); raw numbers in [`thrombin_results.csv`](thrombin_results.csv).

## Result

![Physics-only scores vs experimental affinity for 22 thrombin ligands](thrombin_mmgbsa.png)

| score | Pearson r | R² | Spearman ρ |
| --- | :---: | :---: | :---: |
| App coarse LJ + Coulomb | 0.20 | 0.04 | 0.30 |
| Real FF, vacuum | 0.59&nbsp;* | 0.34 | 0.33 |
| **MM-GBSA (GBn2)** | **0.55** | 0.30 | **0.41** |

\* the vacuum Pearson is inflated by a single high-leverage outlier; on the outlier-robust **rank**
correlation (Spearman), **MM-GBSA is the best (ρ = 0.41)**.

## What it says

- The app's coarse score is **essentially uncorrelated** with affinity (r = 0.20) — exactly as the
  README warns: it is for intuition, not ranking.
- The **same physics done rigorously** — real force field + implicit-solvent MM-GBSA — recovers a
  **real, statistically significant** correlation (Pearson r = 0.55, p ≈ 0.008) while staying
  **physics-only, no ML**.
- This is **typical** for single-snapshot MM-GBSA on a congeneric series. It is **not** FEP accuracy
  and **not** an absolute ΔG — note the y-axes, MM-GBSA over-stabilizes by design, so only the
  *ranking* is meaningful. Short-MD conformational averaging and an entropy term are the obvious next
  steps to push the correlation higher.

So the coarse browser tool is an honest **intuition** layer, and the underlying physics — taken to a
real force field with solvent — crosses from "qualitative cartoon" to a **legitimate fast affinity
ranker** on a standard benchmark, with the receipts in this folder.

## Reproduce

```bash
# conda env with: openmm, ambertools, openff-toolkit, openmmforcefields, rdkit, scipy, matplotlib, pandas, pyyaml
git clone --filter=blob:none --sparse https://github.com/openforcefield/protein-ligand-benchmark ~/pfg-val
cd ~/pfg-val && git sparse-checkout set data        # provides data/thrombin/{00_data,01_protein,02_ligands}
python mmgbsa_validate.py thrombin                   # -> ~/pfg-val/work/thrombin/results.csv
python mmgbsa_plot.py ~/pfg-val/work/thrombin/results.csv thrombin thrombin_mmgbsa.png
```
