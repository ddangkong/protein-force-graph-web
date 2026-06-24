import { elementOf } from './chemistry.js';

// Minimal V2000 SDF / MOL parser (first record): atom element + 3D position. Bonds are ignored
// (rendering uses spheres; the in-app force field is per-atom nonbonded).
export function parseSdf(text) {
  const lines = text.split('\n');
  if (lines.length < 5) return [];
  const na = parseInt(lines[3].slice(0, 3)) || 0;
  const atoms = [], cnt = {};
  for (let i = 0; i < na && 4 + i < lines.length; i++) {
    const ln = lines[4 + i];
    if (ln.length < 34) continue;
    const x = parseFloat(ln.slice(0, 10)), y = parseFloat(ln.slice(10, 20)), z = parseFloat(ln.slice(20, 30));
    if (!isFinite(x) || !isFinite(y) || !isFinite(z)) continue;
    const sym = ln.slice(31, 34).trim();
    const el = elementOf(sym);
    cnt[sym] = (cnt[sym] || 0) + 1;
    atoms.push({ el, x, y, z, name: (sym + cnt[sym]).slice(0, 4) });
  }
  return atoms;
}
