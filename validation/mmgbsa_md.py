#!/usr/bin/env python
"""MD-ensemble MM-GBSA (+ interaction entropy) — the improvement experiment over single-snapshot.

Reuses the cached tleap prmtops in work/<target>/<lig>/ (no antechamber). For each complex:
minimize -> short GBn2 MD (HMR, 4 fs) -> score K frames -> average. From the gas-phase interaction
energy fluctuations over the same frames it also computes the interaction-entropy correction
-TdS_IE (Duan 2016), at no extra MD cost.

Columns: name, dG_md (#1 MD-averaged MM-GBSA), dG_ie (#2 = dG_md + (-TdS_IE)), minusTdS.
Usage: python mmgbsa_md.py <target> [limit]
"""
import os, sys, math
import numpy as np
from scipy.special import logsumexp
import openmm as mm
from openmm import app, unit

HOME = os.path.expanduser("~"); ROOT = f"{HOME}/pfg-val"
TARGET = sys.argv[1]; LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 0
WORK = f"{ROOT}/work/{TARGET}"
RT = 0.001987204 * 298.15
KCAL = unit.kilocalorie_per_mole
EQUIL_PS, FRAMES, GAP_PS = 10, 12, 4          # 10 ps equil, then 12 frames every 4 ps (48 ps prod)
DT = 0.004                                     # ps (HMR allows 4 fs)
CUDA = mm.Platform.getPlatformByName("CUDA")

def score_ctx(prmtop, gb):
    kw = dict(nonbondedMethod=app.NoCutoff, constraints=None, removeCMMotion=False)
    if gb: kw["implicitSolvent"] = app.GBn2
    sysm = prmtop.createSystem(**kw)
    return mm.Context(sysm, mm.VerletIntegrator(1 * unit.femtosecond), CUDA)

def E(ctx, pos):
    ctx.setPositions(pos)
    return ctx.getState(getEnergy=True).getPotentialEnergy().value_in_unit(KCAL)

def run_ligand(d):
    cpx = app.AmberPrmtopFile(f"{d}/com.prmtop")
    rec = app.AmberPrmtopFile(f"{d}/rec.prmtop")
    lig = app.AmberPrmtopFile(f"{d}/lig.prmtop")
    inp = app.AmberInpcrdFile(f"{d}/com.inpcrd")
    n_lig = lig.topology.getNumAtoms(); n_prot = cpx.topology.getNumAtoms() - n_lig

    md_sys = cpx.createSystem(implicitSolvent=app.GBn2, nonbondedMethod=app.NoCutoff,
                              constraints=app.HBonds, hydrogenMass=3.5 * unit.amu, removeCMMotion=True)
    # weak positional restraint on protein C-alpha -> keep the fold/pose bound while sampling
    rest = mm.CustomExternalForce("k*((x-x0)^2+(y-y0)^2+(z-z0)^2)")
    rest.addGlobalParameter("k", 5.0 * 4.184 * 100.0)          # 5 kcal/mol/A^2 in kJ/mol/nm^2
    for p in ("x0", "y0", "z0"): rest.addPerParticleParameter(p)
    ca = [a.index for a in cpx.topology.atoms() if a.name == "CA" and a.index < n_prot]
    for i in ca: rest.addParticle(i, (0.0, 0.0, 0.0))
    md_sys.addForce(rest)
    integ = mm.LangevinMiddleIntegrator(300 * unit.kelvin, 1.0 / unit.picosecond, DT * unit.picosecond)
    sim = app.Simulation(cpx.topology, md_sys, integ, CUDA)
    sim.context.setPositions(inp.positions)
    p0 = sim.context.getState(getPositions=True).getPositions(asNumpy=True).value_in_unit(unit.nanometer)
    for j, i in enumerate(ca):
        rest.setParticleParameters(j, i, p0[i].tolist())       # anchor at the initial bound pose
    rest.updateParametersInContext(sim.context)
    sim.minimizeEnergy(maxIterations=1000)
    sim.context.setVelocitiesToTemperature(300 * unit.kelvin)
    sim.step(int(EQUIL_PS / DT))

    cg, cv = score_ctx(cpx, True), score_ctx(cpx, False)
    rg, rv = score_ctx(rec, True), score_ctx(rec, False)
    lg, lv = score_ctx(lig, True), score_ctx(lig, False)
    dGs, Eints = [], []
    for _ in range(FRAMES):
        sim.step(int(GAP_PS / DT))
        pos = sim.context.getState(getPositions=True).getPositions(asNumpy=True)
        rp, lp = pos[:n_prot], pos[n_prot:]
        dGs.append(E(cg, pos) - E(rg, rp) - E(lg, lp))            # MM-GBSA binding for this frame
        Eints.append(E(cv, pos) - E(rv, rp) - E(lv, lp))         # gas-phase MM interaction
    for c in (cg, cv, rg, rv, lg, lv): del c
    dGs = np.array(dGs); Eints = np.array(Eints)
    dG_md = float(dGs.mean())
    dE = (Eints - Eints.mean()) / RT                              # interaction entropy (log-sum-exp)
    minusTdS = float(RT * (logsumexp(dE) - math.log(len(dE))))
    return dG_md, dG_md + minusTdS, minusTdS

def main():
    out = f"{WORK}/results_md.csv"
    done = set()
    if os.path.exists(out):
        for ln in open(out):
            if ln.strip() and not ln.startswith("name,"):
                done.add(ln.split(",")[0])
    # ligand list = the dirs that already have cached prmtops
    ligs = sorted(n for n in os.listdir(WORK)
                  if os.path.isfile(f"{WORK}/{n}/com.prmtop"))
    if LIMIT: ligs = ligs[:LIMIT]
    fo = open(out, "a" if done else "w")
    if not done:
        fo.write("name,dG_md,dG_ie,minusTdS\n"); fo.flush()
    for i, name in enumerate(ligs, 1):
        if name in done:
            print(f"[{i}/{len(ligs)}] {name} (cached)", flush=True); continue
        try:
            md, ie, ts = run_ligand(f"{WORK}/{name}")
            fo.write(f"{name},{md:.3f},{ie:.3f},{ts:.3f}\n"); fo.flush()
            print(f"[{i}/{len(ligs)}] {name:10s} dG_md {md:8.2f}  +IE {ie:8.2f}  (-TdS {ts:6.2f})", flush=True)
        except Exception as e:
            print(f"[{i}/{len(ligs)}] {name:10s} FAILED: {str(e)[:160]}", flush=True)
    fo.close(); print("wrote", out)

if __name__ == "__main__":
    main()
