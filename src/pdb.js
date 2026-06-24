import { elementOf } from './chemistry.js';

const WATERS = new Set(['HOH', 'WAT', 'H2O', 'TIP', 'DOD']);
const IONS = new Set(['NA', 'CL', 'K', 'MG', 'ZN', 'CA', 'FE', 'MN']);
const AA = new Set(['ALA','ARG','ASN','ASP','CYS','GLN','GLU','GLY','HIS','ILE','LEU','LYS',
  'MET','PHE','PRO','SER','THR','TRP','TYR','VAL','HID','HIE','HIP','MSE','SEC','PYL']);

// Parse a PDB string into flat atom arrays. Classifies the ligand = any HETATM residue that is
// not water / ion / standard amino acid (e.g. MK1 / indinavir).
export function parsePdb(text) {
  const atoms = [];          // { x,y,z, el, name, resName, resSeq, chain, het, lig }
  const lines = text.split('\n');
  for (const ln of lines) {
    const rec = ln.slice(0, 6);
    const het = rec === 'HETATM';
    if (rec !== 'ATOM  ' && !het) continue;
    const resName = ln.slice(17, 20).trim();
    if (WATERS.has(resName)) continue;                         // drop waters
    const name = ln.slice(12, 16).trim();
    let elSym = ln.slice(76, 78).trim();
    if (!elSym) elSym = name.replace(/[0-9]/g, '').slice(0, 2);
    const el = elementOf(elSym);
    const x = parseFloat(ln.slice(30, 38));
    const y = parseFloat(ln.slice(38, 46));
    const z = parseFloat(ln.slice(46, 54));
    if (!isFinite(x) || !isFinite(y) || !isFinite(z)) continue;
    const isAA = AA.has(resName);
    const isIon = IONS.has(resName);
    const lig = het && !isAA && !isIon;                        // ligand = non-standard HETATM
    atoms.push({ x, y, z, el, name, resName,
      resSeq: parseInt(ln.slice(22, 26)) || 0,
      chain: ln[21] || 'A', het, lig });
  }
  const ligand = atoms.filter(a => a.lig);
  const protein = atoms.filter(a => !a.lig);
  return { atoms, protein, ligand };       // raw coords — caller centers (on the protein)
}
