#!/usr/bin/env python
"""Single-trajectory MM-GBSA validation against experimental affinity, for the OpenFF
protein-ligand benchmark. Physics only (no ML). For each ligand:

  antechamber (AM1-BCC) -> parmchk2 -> tleap (ff14SB + GAFF2, mbondi3 radii)
  -> OpenMM GBn2 minimize of the complex -> single-trajectory energies:
       dG_MMGBSA = E(complex) - E(receptor) - E(ligand)     [GBn2 implicit solvent]
       dE_vac    = same, but vacuum real force field (no solvent)
       crude     = the web app's coarse per-element LJ + Coulomb(RDIE) interaction

Writes results CSV. A separate script makes the scatter plots + stats.
Usage: python mmgbsa_validate.py <target> [limit]
"""
import os, sys, math, subprocess
import numpy as np
import yaml
from rdkit import Chem
import openmm as mm
from openmm import app, unit

HOME = os.path.expanduser("~")
ROOT = f"{HOME}/pfg-val"
TARGET = sys.argv[1] if len(sys.argv) > 1 else "thrombin"
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 0
DATA = f"{ROOT}/data/{TARGET}"
WORK = f"{ROOT}/work/{TARGET}"
os.makedirs(WORK, exist_ok=True)
PROT_SRC = f"{DATA}/01_protein/crd/protein.pdb"
RT = 0.001987204 * 298.15  # kcal/mol

# ---- the web app's coarse force field (mirror of src/forcefield.js) ----
LJ = {"H": (0.600, 0.0157), "C": (1.908, 0.086), "N": (1.824, 0.170), "O": (1.661, 0.210),
      "S": (2.000, 0.250), "P": (2.100, 0.200), "F": (1.750, 0.061), "Cl": (1.948, 0.265), "Br": (2.220, 0.320)}
QC = {"O": -0.40, "N": -0.32, "C": 0.10, "H": 0.10, "S": -0.20, "P": 0.45, "F": -0.22, "Cl": -0.13, "Br": -0.10}
KC = 332.0636

def crude_interaction(elems, pos, n_lig):
    """app-style coarse LJ + RDIE-Coulomb interaction energy, ligand vs protein (kcal/mol)."""
    n = len(elems); n_prot = n - n_lig
    rmh = np.array([LJ.get(e, LJ["C"])[0] for e in elems])
    eps = np.array([LJ.get(e, LJ["C"])[1] for e in elems])
    q = np.array([QC.get(e, 0.0) for e in elems])
    L = slice(n_prot, n); P = slice(0, n_prot)
    d2 = ((pos[L][:, None, :] - pos[P][None, :, :]) ** 2).sum(-1)   # (n_lig, n_prot)
    d2c = np.clip(d2, 0.36, None)
    rmin = rmh[L][:, None] + rmh[P][None, :]
    e2 = np.sqrt(eps[L][:, None] * eps[P][None, :])
    sr2 = rmin * rmin / d2c; sr6 = sr2 ** 3
    elj = e2 * (sr6 * sr6 - 2 * sr6)
    ecoul = KC * (q[L][:, None] * q[P][None, :]) * 0.25 / d2c
    return float(np.where(d2 <= 81.0, elj + ecoul, 0.0).sum())

def energy(prmtop_path, positions, gb):
    prm = app.AmberPrmtopFile(prmtop_path)
    kw = dict(nonbondedMethod=app.NoCutoff, constraints=None, removeCMMotion=False)
    if gb: kw["implicitSolvent"] = app.GBn2
    system = prm.createSystem(**kw)
    ctx = mm.Context(system, mm.VerletIntegrator(1 * unit.femtosecond),
                     mm.Platform.getPlatformByName("CUDA"))
    ctx.setPositions(positions)
    e = ctx.getState(getEnergy=True).getPotentialEnergy().value_in_unit(unit.kilocalorie_per_mole)
    del ctx
    return e, system

def minimize_complex(prmtop_path, inpcrd_path):
    prm = app.AmberPrmtopFile(prmtop_path)
    inp = app.AmberInpcrdFile(inpcrd_path)
    system = prm.createSystem(implicitSolvent=app.GBn2, nonbondedMethod=app.NoCutoff,
                              constraints=None, removeCMMotion=False)
    ctx = mm.Context(system, mm.VerletIntegrator(1 * unit.femtosecond),
                     mm.Platform.getPlatformByName("CUDA"))
    ctx.setPositions(inp.positions)
    mm.LocalEnergyMinimizer.minimize(ctx, tolerance=5 * unit.kilojoule_per_mole / unit.nanometer, maxIterations=1000)
    st = ctx.getState(getPositions=True, getEnergy=True)
    pos = st.getPositions(asNumpy=True).value_in_unit(unit.angstrom)
    egb = st.getPotentialEnergy().value_in_unit(unit.kilocalorie_per_mole)
    elems = [a.element.symbol for a in prm.topology.atoms()]
    del ctx
    return pos, egb, elems

def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {r.stderr[-500:] or r.stdout[-500:]}")

def prep_protein():
    out = f"{WORK}/protein_amber.pdb"
    if not os.path.exists(out):
        run(["pdb4amber", "-i", PROT_SRC, "-o", out, "--nohyd", "--dry"])
    return out

def run_ligand(name, mol, prot_pdb):
    d = f"{WORK}/{name}"; os.makedirs(d, exist_ok=True)
    n_lig = mol.GetNumAtoms()
    nc = Chem.GetFormalCharge(mol)
    Chem.MolToMolFile(mol, f"{d}/lig.mol")
    run(["antechamber", "-i", f"{d}/lig.mol", "-fi", "mdl", "-o", f"{d}/lig.mol2", "-fo", "mol2",
         "-c", "bcc", "-nc", str(nc), "-s", "0", "-pf", "y", "-at", "gaff2"], cwd=d)
    run(["parmchk2", "-i", f"{d}/lig.mol2", "-f", "mol2", "-o", f"{d}/lig.frcmod", "-s", "gaff2"])
    leap = f"""source leaprc.protein.ff14SB
source leaprc.gaff2
set default PBRadii mbondi3
lig = loadmol2 {d}/lig.mol2
loadamberparams {d}/lig.frcmod
rec = loadpdb {prot_pdb}
com = combine {{rec lig}}
saveamberparm lig {d}/lig.prmtop {d}/lig.inpcrd
saveamberparm rec {d}/rec.prmtop {d}/rec.inpcrd
saveamberparm com {d}/com.prmtop {d}/com.inpcrd
quit
"""
    open(f"{d}/leap.in", "w").write(leap)
    run(["tleap", "-s", "-f", f"{d}/leap.in"], cwd=d)

    pos, e_com_gb, elems = minimize_complex(f"{d}/com.prmtop", f"{d}/com.inpcrd")
    n = len(elems); n_prot = n - n_lig
    rec_pos = pos[:n_prot] * unit.angstrom
    lig_pos = pos[n_prot:] * unit.angstrom
    com_pos = pos * unit.angstrom
    e_rec_gb, _ = energy(f"{d}/rec.prmtop", rec_pos, gb=True)
    e_lig_gb, _ = energy(f"{d}/lig.prmtop", lig_pos, gb=True)
    e_com_v, _ = energy(f"{d}/com.prmtop", com_pos, gb=False)
    e_rec_v, _ = energy(f"{d}/rec.prmtop", rec_pos, gb=False)
    e_lig_v, _ = energy(f"{d}/lig.prmtop", lig_pos, gb=False)
    dG_mmgbsa = e_com_gb - e_rec_gb - e_lig_gb
    dE_vac = e_com_v - e_rec_v - e_lig_v
    crude = crude_interaction(elems, pos, n_lig)
    return dG_mmgbsa, dE_vac, crude

def exp_dG(ydat, name):
    m = ydat[name]["measurement"]
    f = {"m": 1, "mm": 1e-3, "um": 1e-6, "nm": 1e-9, "pm": 1e-12}[m["unit"].lower()]
    return RT * math.log(m["value"] * f)

def main():
    ydat = yaml.safe_load(open(f"{DATA}/00_data/ligands.yml"))
    prot_pdb = prep_protein()
    sup = Chem.SDMolSupplier(f"{DATA}/02_ligands/ligands.sdf", removeHs=False)
    mols = [m for m in sup if m is not None]
    if LIMIT: mols = mols[:LIMIT]
    out = f"{WORK}/results.csv"
    done = set()
    if os.path.exists(out):
        for ln in open(out):
            if ln.strip() and not ln.startswith("name,"):
                done.add(ln.split(",")[0])
    fo = open(out, "a" if done else "w")
    if not done:
        fo.write("name,dG_exp,dG_mmgbsa,dE_vac,crude\n"); fo.flush()
    for i, mol in enumerate(mols, 1):
        name = mol.GetProp("_Name")
        if name in done:
            print(f"[{i}/{len(mols)}] {name:10s} (cached)", flush=True); continue
        try:
            dGe = exp_dG(ydat, name)
            g, v, c = run_ligand(name, mol, prot_pdb)
            fo.write(f"{name},{dGe:.3f},{g:.3f},{v:.3f},{c:.3f}\n"); fo.flush()
            print(f"[{i}/{len(mols)}] {name:10s} exp {dGe:6.2f}  MMGBSA {g:8.2f}  vac {v:9.1f}  crude {c:9.1f}", flush=True)
        except Exception as e:
            print(f"[{i}/{len(mols)}] {name:10s} FAILED: {str(e)[:200]}", flush=True)
    fo.close()
    print("wrote", out)

if __name__ == "__main__":
    main()
