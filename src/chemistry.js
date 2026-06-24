// CPK colors + van der Waals / covalent radii (Å). Mirrors the Unity ChemistryDB.
export const ELEMENTS = {
  H:  { color: 0xf5f5f5, vdw: 1.20, cov: 0.31 },
  C:  { color: 0x909090, vdw: 1.70, cov: 0.76 },
  N:  { color: 0x3050f8, vdw: 1.55, cov: 0.71 },
  O:  { color: 0xff2d2d, vdw: 1.52, cov: 0.66 },
  S:  { color: 0xf5d020, vdw: 1.80, cov: 1.05 },
  P:  { color: 0xff8000, vdw: 1.80, cov: 1.07 },
  F:  { color: 0x90e050, vdw: 1.47, cov: 0.57 },
  Cl: { color: 0x1ff01f, vdw: 1.75, cov: 1.02 },
  Br: { color: 0xa62929, vdw: 1.85, cov: 1.20 },
  Na: { color: 0xab5cf2, vdw: 2.27, cov: 1.66 },
  Mg: { color: 0x8aff00, vdw: 1.73, cov: 1.41 },
  Zn: { color: 0x7d80b0, vdw: 1.39, cov: 1.22 },
  Fe: { color: 0xe06633, vdw: 1.40, cov: 1.32 },
};

export function elem(sym) {
  return ELEMENTS[sym] || ELEMENTS.C;
}

// Try to read an element from a PDB atom (element column or atom name fallback).
export function elementOf(sym) {
  if (!sym) return 'C';
  sym = sym.trim();
  const norm = sym.length === 1 ? sym.toUpperCase() : sym[0].toUpperCase() + sym.slice(1).toLowerCase();
  if (ELEMENTS[norm]) return norm;
  const first = sym[0].toUpperCase();
  return ELEMENTS[first] ? first : 'C';
}
