// Talks to the same external OpenMM worker (pipeline/wsl/openmm_worker.py). The browser POSTs the
// current pose as PDB TEXT (no shared filesystem needed); the worker re-parameterizes with GAFF/AM1-BCC
// and minimizes. Needs the worker's CORS headers + pdb_text support (added for the web frontend).
const WORKER = 'http://127.0.0.1:8765';

export async function checkHealth() {
  try {
    const r = await fetch(WORKER + '/health', { signal: AbortSignal.timeout(3000) });
    const d = await r.json();
    return { ok: !!d.available, cuda: !!d.cuda };
  } catch { return { ok: false }; }
}

export async function minimize(pdbText) {
  try {
    const r = await fetch(WORKER + '/minimize', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pdb_text: pdbText, max_iterations: 200 }),
      signal: AbortSignal.timeout(180000),
    });
    return await r.json();
  } catch (e) { return { ok: false, error: String(e) }; }
}

// Current pose → heavy-atom PDB (protein ATOM + ligand HETATM at its dragged offset).
export function poseToPdb(P, L, off) {
  let s = '', serial = 0;
  for (const a of P.atoms) { serial++; s += line('ATOM  ', serial, a.name, a.resName, a.chain, a.resSeq, a.x, a.y, a.z, a.el); }
  for (const a of L.atoms) { serial++; s += line('HETATM', serial, a.name, a.resName, a.chain, a.resSeq, a.x + off.x, a.y + off.y, a.z + off.z, a.el); }
  return s + 'END\n';
}

function line(rec, serial, name, resName, chain, resSeq, x, y, z, el) {
  return rec
    + String(serial % 100000).padStart(5) + ' '
    + name4(name) + ' '
    + (resName || 'UNK').slice(0, 3).padStart(3) + ' '
    + (chain || 'A')[0]
    + String(resSeq).padStart(4) + '    '
    + f83(x) + f83(y) + f83(z)
    + '  1.00  0.00          '
    + (el || 'C').padStart(2) + '\n';
}
const name4 = (n) => { n = (n || '').trim().slice(0, 4); return n.length < 4 ? n.padStart(4) : n; };
const f83 = (v) => v.toFixed(3).padStart(8);
