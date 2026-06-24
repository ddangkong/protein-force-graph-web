// Classical nonbonded force field — Lennard-Jones 12-6 + Coulomb with a distance-dependent
// dielectric (RDIE, eps_r = 4r). Mirrors the Unity ForceField.cs. Energies in kcal/mol, distances Å.
// Coarse partial charges (FF estimate) — honest scope: this is a nonbonded interaction energy, NOT a ΔG.

const LJ = {  // [rmin/2 (Å), epsilon (kcal/mol)]  — Amber/GAFF-ish
  H: [0.600, 0.0157], C: [1.908, 0.086], N: [1.824, 0.170], O: [1.661, 0.210],
  S: [2.000, 0.250],  P: [2.100, 0.200], F: [1.750, 0.061], Cl: [1.948, 0.265],
  Br: [2.220, 0.320], Na: [1.369, 0.0875], Mg: [0.787, 0.875], Zn: [1.100, 0.0125], Fe: [1.200, 0.05],
};
const Q = { O: -0.40, N: -0.32, C: 0.10, H: 0.10, S: -0.20, P: 0.45, F: -0.22, Cl: -0.13, Br: -0.10 };

const K = 332.0636;     // Coulomb constant (kcal·Å/(mol·e²))
const MINR2 = 0.36;     // clamp r >= 0.6 Å to avoid the singularity

export function lj(sym) { return LJ[sym] || LJ.C; }
export function charge(sym) { return Q[sym] ?? 0.0; }

// Force on atom i from atom j + the pair energy. `out` receives {fx,fy,fz,e} (force ON i, kcal/mol/Å).
export function pair(xi, yi, zi, ri, ei, qi, xj, yj, zj, rj, ej, qj, out) {
  let dx = xi - xj, dy = yi - yj, dz = zi - zj;
  let r2 = dx * dx + dy * dy + dz * dz;
  if (r2 < MINR2) r2 = MINR2;
  const r = Math.sqrt(r2), ir2 = 1 / r2;

  // Lennard-Jones (Lorentz–Berthelot: rmin = (rmin/2)_i + (rmin/2)_j, eps = sqrt)
  const rmin = ri + rj, eps = Math.sqrt(ei * ej);
  const sr2 = rmin * rmin * ir2, sr6 = sr2 * sr2 * sr2, sr12 = sr6 * sr6;
  const eLJ = eps * (sr12 - 2 * sr6);
  const fLJ = (12 * eps / r) * (sr12 - sr6);          // along r̂; + = repulsive

  // Coulomb, RDIE eps_r = 4r  →  E = K q q /(4 r²),  F = K q q /(2 r³)
  const eC = K * qi * qj * 0.25 * ir2;
  const fC = K * qi * qj * 0.5 * ir2 / r;

  const fmag = (fLJ + fC) / r;                        // project onto unit vector
  out.fx = dx * fmag; out.fy = dy * fmag; out.fz = dz * fmag;
  out.eLJ = eLJ; out.eC = eC; out.e = eLJ + eC;
}
