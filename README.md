# Protein Force Graph — web

Interactive, **physics-only** visualization of protein–ligand interactions, in the browser.

Drag a ligand around a protein and watch the **force on every residue update in real time** —
each atom colored blue→red by how hard the ligand pushes or pulls it. Every number on screen is a
transparent physical rule (Lennard-Jones + Coulomb), **not** a machine-learning prediction.

> This is an **explainer / intuition** tool — *not* a docking or binding-affinity predictor.
> See [Honest scope](#honest-scope).

The default scene is **1HSG**: HIV-1 protease bound to the inhibitor indinavir (MK1).

---

## Features

- **Live per-residue force heatmap.** The net force each protein atom feels from the ligand
  (Newton's 3rd law) is mapped blue (low) → red (high). The binding pocket lights up as the ligand
  approaches, and flares red on a steric clash.
- **Drag the ligand.** Grab the green ligand and move it; the van der Waals + electrostatic energy
  and the net-force arrow recompute on every pointer move — no precomputation, no lookup tables.
- **Transparent energy panel.** van der Waals and electrostatic interaction energy in kcal/mol,
  plus the net-force magnitude. (A force-field *estimate* — not ΔG.)
- **Net-force arrow.** Direction + magnitude of the total force on the ligand; cyan when
  net-attractive, red when net-repulsive.
- **Load any structure.** Load an arbitrary protein **PDB**, and a ligand from **SDF / MOL / PDB**,
  via the buttons or by drag-and-drop. A loaded ligand is a full participant in the force field —
  identical physics to the built-in one.

## The physics

Everything is computed live in the browser; you can read every term in [`src/forcefield.js`](src/forcefield.js).

- **van der Waals** — Lennard-Jones 12-6, per-element parameters combined with Lorentz–Berthelot
  mixing rules.
- **Electrostatics** — Coulomb with a distance-dependent dielectric (RDIE, ε_r = 4r) and coarse
  per-element partial charges.
- **Neighbor search** — a uniform spatial grid (cell = 9 Å cutoff) keeps the per-frame force
  evaluation fast enough for real-time dragging.
- **Rendering** — Three.js `InstancedMesh` (one draw call for thousands of atoms), CPK coloring,
  and on-demand rendering (the scene re-renders only when something actually changes).

## Run it

```bash
npm install
npm run dev
# then open the printed localhost URL
```

**Controls:** drag the green ligand to move it · drag empty space to orbit · scroll to zoom ·
bottom buttons to load files, reset the pose, and toggle the heatmap.

## Honest scope

The energies here are **nonbonded interaction energies** from a coarse classical force field —
useful for *intuition* about where a ligand clashes or binds, and fully transparent.

They are **not** binding free energies (ΔG). A real ΔG = ΔH − TΔS needs explicit solvent, entropy,
and conformational sampling (MM/GBSA, FEP/TI) — none of which this tool attempts. That is
deliberate: the goal is an **explainable, real-time, physics-only** picture, not an affinity
predictor.

An optional [OpenMM](https://openmm.org/) worker ([`src/openmm.js`](src/openmm.js)) can relax a
dragged pose with a real ff14SB + GAFF force field, but it requires running a separate Python
worker and is **not** needed for the in-browser physics.

## Project layout

```
index.html         overlay UI (energy panel, controls, legend)
src/main.js        scene, force loop, ligand drag, heatmap, file loaders
src/forcefield.js  Lennard-Jones + Coulomb
src/pdb.js         PDB parser (protein / ligand split)
src/sdf.js         minimal V2000 SDF / MOL parser
src/chemistry.js   element table (radii, colors)
src/openmm.js      optional OpenMM worker client
public/            demo structures (1HSG protease + MK1 ligand)
```

## Tech

Vite · Three.js · plain ES modules.
