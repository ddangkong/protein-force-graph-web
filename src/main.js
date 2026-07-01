import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { parsePdb } from './pdb.js';
import { parseSdf } from './sdf.js';
import { elem } from './chemistry.js';
import { lj, charge, pair, K, MINR2 } from './forcefield.js';
import { checkHealth, minimize, poseToPdb } from './openmm.js';

const CUTOFF = 9.0;          // Å — live nonbonded interaction range
const PROT_SCALE = 0.42;     // sphere radius = scale * vdW
const LIG_SCALE = 0.68;      // ligand drawn chunkier than the protein so it reads as the focus
const HALO_SCALE = 1.7;      // additive glow shell around each ligand atom
const FMAX = 18.0;           // kcal/mol/Å — heatmap saturation

const app = document.getElementById('app');
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
app.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b0e16);
const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.5, 8000);
camera.position.set(0, 0, 110);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = false;
controls.addEventListener('change', () => requestRender());
scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const key = new THREE.DirectionalLight(0xffffff, 0.85); key.position.set(1, 1, 1.5); scene.add(key);

const sphereGeo = new THREE.SphereGeometry(1, 16, 12);
const protMat = new THREE.MeshStandardMaterial({ roughness: 0.55 });
const ligMat = new THREE.MeshStandardMaterial({ roughness: 0.3, emissive: 0x0c1a12, emissiveIntensity: 1 });
// Soft white-green additive shell — makes the ligand glow above the heatmap palette so it never
// blends into the (also green/cyan) force-colored residues.
const haloMat = new THREE.MeshBasicMaterial({ color: 0xc8ffdd, transparent: true, opacity: 0.33,
  side: THREE.BackSide, depthWrite: false, blending: THREE.AdditiveBlending });

let P = null, L = null, grid = null;
const ligOffset = new THREE.Vector3();
let heatmap = true;
const out = {}, dummy = new THREE.Object3D(), tmpC = new THREE.Color();
let arrow = null;

init();

async function init() {
  arrow = new THREE.ArrowHelper(new THREE.Vector3(0, 0, 1), new THREE.Vector3(), 1, 0x39d6ff, 1, 1);
  arrow.visible = false; scene.add(arrow);
  setupDrag();
  setupUI();
  setupLoaders();
  window.__pfg = {                                   // debug hooks for headless verification
    nudge: (x, y, z) => { ligOffset.set(x, y, z); requestRender(); },
    setHeatmap: (b) => { heatmap = b; document.getElementById('forces').textContent = 'Force heatmap: ' + (b ? 'ON' : 'OFF'); requestRender(); },
    loadProtein: (t) => loadProteinText(t),
    loadLigand: (t, ext) => loadLigandText(t, ext),
  };
  pollHealth();
  addEventListener('resize', onResize);
  // Optional deep-link: ?pdb=<file>[&lig=<file>] — defaults to the bundled 1HSG demo.
  const params = new URLSearchParams(location.search);
  const want = params.get('pdb') || '1HSG.pdb';
  let d = parsePdb(await (await fetch(want)).text());
  if (!d.protein.length) { status('could not load ' + want + ' — showing 1HSG'); d = parsePdb(await (await fetch('1HSG.pdb')).text()); }
  setStructure(d.protein, d.ligand, true);
  const smi = params.get('smiles'), ligUrl = params.get('lig');
  if (smi) buildLigandFromSmiles(smi);
  else if (ligUrl) {
    try { loadLigandText(await (await fetch(ligUrl)).text(), extOf(ligUrl)); }
    catch { status('ligand load failed: ' + ligUrl); }
  }
}

// Rebuild the whole scene from a protein + ligand atom set (centered on the protein centroid).
function setStructure(protAtoms, ligAtoms, refit) {
  let cx = 0, cy = 0, cz = 0; const pn = protAtoms.length || 1;
  for (const a of protAtoms) { cx += a.x; cy += a.y; cz += a.z; } cx /= pn; cy /= pn; cz /= pn;
  for (const a of protAtoms) { a.x -= cx; a.y -= cy; a.z -= cz; }
  for (const a of ligAtoms) { a.x -= cx; a.y -= cy; a.z -= cz; }
  if (P && P.mesh) { scene.remove(P.mesh); P.mesh.dispose(); }
  if (L && L.mesh) { scene.remove(L.mesh); L.mesh.dispose(); if (L.halo) { scene.remove(L.halo); L.halo.dispose(); } }
  ligOffset.set(0, 0, 0);
  buildProtein(protAtoms);
  if (ligAtoms.length) buildLigand(ligAtoms);
  else L = { n: 0, atoms: [], lbase: new Float32Array(0), mesh: null, halo: null };
  buildGrid();
  if (refit) fitCamera();
  requestRender();
}

function protRadius() {
  let r = 0; if (!P) return 15;
  for (const a of P.atoms) r = Math.max(r, Math.hypot(a.x, a.y, a.z));
  return r || 15;
}

function loadProteinText(text) {
  const d = parsePdb(text);
  if (!d.protein.length) { status('no protein (ATOM) records found'); return; }
  setStructure(d.protein, d.ligand, true);
  status('protein loaded · ' + d.protein.length + ' atoms · ' + (d.ligand.length ? d.ligand.length + '-atom ligand' : 'no ligand — load one'));
}

function loadLigandText(text, e) {
  const raw = (e === 'sdf' || e === 'mol') ? parseSdf(text) : parsePdb(text).atoms;
  const lig = raw.map(a => ({ x: a.x, y: a.y, z: a.z, el: a.el, name: a.name || a.el, resName: 'LIG', resSeq: 1, chain: 'X' }));
  if (!lig.length) { status('no ligand atoms found'); return; }
  if (!P) { status('load a protein first'); return; }
  let lx = 0, ly = 0, lz = 0; for (const a of lig) { lx += a.x; ly += a.y; lz += a.z; } lx /= lig.length; ly /= lig.length; lz /= lig.length;
  const R = protRadius();
  for (const a of lig) { a.x -= lx; a.y -= ly; a.z = a.z - lz + R + 4; }   // float just outside the protein
  setStructure(P.atoms, lig, false);
  status('ligand loaded · ' + lig.length + ' atoms — drag it into the pocket');
}

function status(t) { const s = document.getElementById('loadStatus'); if (s) s.textContent = t; }

const RCSB = 'https://files.rcsb.org/download/';

// Fetch a structure straight from the RCSB PDB bank by its 4-character ID (RCSB serves CORS).
async function fetchPdbById(id) {
  id = (id || '').trim().toUpperCase();
  if (!/^[0-9A-Z]{4}$/.test(id)) { status('enter a 4-character PDB ID (e.g. 1M17)'); return; }
  status('fetching ' + id + ' from RCSB…');
  try {
    const r = await fetch(RCSB + id + '.pdb');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    loadProteinText(await r.text());
  } catch (e) { status('could not fetch ' + id + ' — ' + e.message); }
}

// SMILES → 3D ligand, fully in the browser via OpenChemLib — no server, works offline and on
// NOVEL / synthesized compounds (it builds the 3D conformer + MMFF94-relaxes it from the structure).
// The library + its MMFF94 resource tables (~3 MB) load lazily on first use, then stay cached.
let _ocl = null;
async function getOCL() {
  if (_ocl) return _ocl;
  status('loading the 3D builder (one-time)…');
  const OCL = await import('openchemlib');
  OCL.Resources.register(await (await fetch('ocl-resources.json')).text());
  _ocl = OCL;
  return OCL;
}
async function buildLigandFromSmiles(smiles) {
  smiles = (smiles || '').trim();
  if (!smiles) { status('paste a ligand SMILES first'); return; }
  if (!P) { status('load a protein first'); return; }
  try {
    const OCL = await getOCL();
    status('building 3D from SMILES…');
    const mol = OCL.Molecule.fromSmiles(smiles);
    const m3 = new OCL.ConformerGenerator(0x5eed).getOneConformerAsMolecule(mol);
    if (!m3) throw new Error('could not generate a 3D conformer');
    loadLigandText(m3.toMolfile(), 'mol');
  } catch (e) {
    status('SMILES → 3D failed — ' + String((e && e.message) || e).replace(/^[\w$]+:\s*/, ''));
  }
}

function setupLoaders() {
  document.getElementById('loadProt').onclick = () => pickFile('.pdb', (t) => loadProteinText(t));
  document.getElementById('loadLig').onclick = () => pickFile('.sdf,.mol,.mol2,.pdb', (t, name) => loadLigandText(t, extOf(name)));
  const pdbId = document.getElementById('pdbId'), smiles = document.getElementById('smiles');
  document.getElementById('fetchPdb').onclick = () => fetchPdbById(pdbId.value);
  document.getElementById('buildLig').onclick = () => buildLigandFromSmiles(smiles.value);
  pdbId.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') fetchPdbById(pdbId.value); });
  smiles.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') buildLigandFromSmiles(smiles.value); });
  document.addEventListener('dragover', (ev) => ev.preventDefault());
  document.addEventListener('drop', (ev) => {
    ev.preventDefault(); const f = ev.dataTransfer.files[0]; if (!f) return;
    const e = extOf(f.name), r = new FileReader();
    r.onload = () => { if (e === 'pdb') loadProteinText(r.result); else loadLigandText(r.result, e); };
    r.readAsText(f);
  });
}
const extOf = (name) => (name || '').toLowerCase().split('.').pop();
function pickFile(accept, cb) {
  const inp = document.createElement('input'); inp.type = 'file'; inp.accept = accept;
  inp.onchange = () => { const f = inp.files[0]; if (f) { const r = new FileReader(); r.onload = () => cb(r.result, f.name); r.readAsText(f); } };
  inp.click();
}

function buildProtein(arr) {
  const n = arr.length;
  const pos = new Float32Array(3 * n), rmin = new Float32Array(n), eps = new Float32Array(n), q = new Float32Array(n);
  const base = new Float32Array(3 * n);
  const mesh = new THREE.InstancedMesh(sphereGeo, protMat, n);
  for (let i = 0; i < n; i++) {
    const a = arr[i];
    pos[3 * i] = a.x; pos[3 * i + 1] = a.y; pos[3 * i + 2] = a.z;
    const lp = lj(a.el); rmin[i] = lp[0]; eps[i] = lp[1]; q[i] = charge(a.el);
    dummy.position.set(a.x, a.y, a.z); dummy.scale.setScalar(elem(a.el).vdw * PROT_SCALE);
    dummy.updateMatrix(); mesh.setMatrixAt(i, dummy.matrix);
    tmpC.set(elem(a.el).color); base[3 * i] = tmpC.r; base[3 * i + 1] = tmpC.g; base[3 * i + 2] = tmpC.b;
    mesh.setColorAt(i, tmpC);
  }
  mesh.instanceMatrix.needsUpdate = true; mesh.instanceColor.needsUpdate = true;
  scene.add(mesh);
  P = { n, pos, rmin, eps, q, base, mesh, atoms: arr,
        fx: new Float32Array(n), fy: new Float32Array(n), fz: new Float32Array(n) };
}

function buildLigand(arr) {
  const n = arr.length;
  const lbase = new Float32Array(3 * n), rmin = new Float32Array(n), eps = new Float32Array(n), q = new Float32Array(n), rad = new Float32Array(n);
  const mesh = new THREE.InstancedMesh(sphereGeo, ligMat, n);
  const halo = new THREE.InstancedMesh(sphereGeo, haloMat, n);
  halo.renderOrder = 2;                                  // draw the glow after the opaque atoms
  for (let i = 0; i < n; i++) {
    const a = arr[i];
    lbase[3 * i] = a.x; lbase[3 * i + 1] = a.y; lbase[3 * i + 2] = a.z;
    const lp = lj(a.el); rmin[i] = lp[0]; eps[i] = lp[1]; q[i] = charge(a.el); rad[i] = elem(a.el).vdw * LIG_SCALE;
    dummy.position.set(a.x, a.y, a.z);
    dummy.scale.setScalar(rad[i]); dummy.updateMatrix(); mesh.setMatrixAt(i, dummy.matrix);
    dummy.scale.setScalar(rad[i] * HALO_SCALE); dummy.updateMatrix(); halo.setMatrixAt(i, dummy.matrix);
    mesh.setColorAt(i, tmpC.set(a.el === 'C' ? 0x49ff84 : elem(a.el).color));
  }
  mesh.instanceMatrix.needsUpdate = true; mesh.instanceColor.needsUpdate = true;
  halo.instanceMatrix.needsUpdate = true;
  scene.add(mesh); scene.add(halo);
  L = { n, lbase, lbase0: lbase.slice(), rmin, eps, q, rad, mesh, halo, atoms: arr,
        resName: arr[0] ? arr[0].resName : 'MK1', resSeq: arr[0] ? arr[0].resSeq : 1, chain: arr[0] ? arr[0].chain : 'B' };
}

function buildGrid() {
  const cs = CUTOFF, map = new Map();
  for (let i = 0; i < P.n; i++) {
    const k = cellKey(Math.floor(P.pos[3 * i] / cs), Math.floor(P.pos[3 * i + 1] / cs), Math.floor(P.pos[3 * i + 2] / cs));
    let b = map.get(k); if (!b) { b = []; map.set(k, b); } b.push(i);
  }
  grid = { cs, map };
}
// integer cell key (base-512 pack; avoids per-lookup string allocation in the hot loops)
const cellKey = (ix, iy, iz) => (ix + 256) * 262144 + (iy + 256) * 512 + (iz + 256);

function computeForces() {
  P.fx.fill(0); P.fy.fill(0); P.fz.fill(0);
  if (!L || !L.n) return { nx: 0, ny: 0, nz: 0, evdw: 0, eelec: 0, mag: 0 };
  let nx = 0, ny = 0, nz = 0, evdw = 0, eelec = 0;
  const cs = grid.cs, c2 = CUTOFF * CUTOFF;
  for (let i = 0; i < L.n; i++) {
    const lx = L.lbase[3 * i] + ligOffset.x, ly = L.lbase[3 * i + 1] + ligOffset.y, lz = L.lbase[3 * i + 2] + ligOffset.z;
    const lr = L.rmin[i], le = L.eps[i], lq = L.q[i];
    const ix = Math.floor(lx / cs), iy = Math.floor(ly / cs), iz = Math.floor(lz / cs);
    for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) for (let c = -1; c <= 1; c++) {
      const bucket = grid.map.get(cellKey(ix + a, iy + b, iz + c));
      if (!bucket) continue;
      for (const pj of bucket) {
        const px = P.pos[3 * pj], py = P.pos[3 * pj + 1], pz = P.pos[3 * pj + 2];
        const dx = lx - px, dy = ly - py, dz = lz - pz;
        if (dx * dx + dy * dy + dz * dz > c2) continue;
        pair(lx, ly, lz, lr, le, lq, px, py, pz, P.rmin[pj], P.eps[pj], P.q[pj], out);
        nx += out.fx; ny += out.fy; nz += out.fz;                 // force on the ligand
        P.fx[pj] -= out.fx; P.fy[pj] -= out.fy; P.fz[pj] -= out.fz; // reaction on the protein atom
        evdw += out.eLJ; eelec += out.eC;
      }
    }
  }
  return { nx, ny, nz, evdw, eelec, mag: Math.hypot(nx, ny, nz) };
}

// ---- Physics binding-site scan ------------------------------------------------------------
// Rigidly steps the ligand over the protein (a grid of positions × a few orientations) and evaluates
// the SAME LJ+Coulomb interaction energy shown live, then snaps it to the most favorable (lowest-E)
// spot. A transparent scan of our own force field — NOT docking, NOT ML, and NOT a binding ΔG.
// Energy-only (no force, no sqrt) — this runs millions of times during a scan, so it inlines the
// LJ + RDIE-Coulomb energy from forcefield.js (kept in sync with pair()).
function rigidEnergy(base, gx, gy, gz) {
  const cs = grid.cs, c2 = CUTOFF * CUTOFF, pos = P.pos, prm = P.rmin, pep = P.eps, pq = P.q, map = grid.map;
  let e = 0;
  for (let i = 0; i < L.n; i++) {
    const lx = base[3 * i] + gx, ly = base[3 * i + 1] + gy, lz = base[3 * i + 2] + gz;
    const lr = L.rmin[i], le = L.eps[i], lq = L.q[i];
    const ix = Math.floor(lx / cs), iy = Math.floor(ly / cs), iz = Math.floor(lz / cs);
    for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) for (let c = -1; c <= 1; c++) {
      const bucket = map.get(cellKey(ix + a, iy + b, iz + c));
      if (!bucket) continue;
      for (let k = 0; k < bucket.length; k++) {
        const pj = bucket[k];
        const dx = lx - pos[3 * pj], dy = ly - pos[3 * pj + 1], dz = lz - pos[3 * pj + 2];
        let r2 = dx * dx + dy * dy + dz * dz;
        if (r2 > c2) continue;
        if (r2 < MINR2) r2 = MINR2;
        const ir2 = 1 / r2, rmin = lr + prm[pj];
        const sr2 = rmin * rmin * ir2, sr6 = sr2 * sr2 * sr2;
        e += Math.sqrt(le * pep[pj]) * (sr6 * sr6 - 2 * sr6) + K * lq * pq[pj] * 0.25 * ir2;
        if (e > 1000) return e;                  // steric clash — abandon this pose early
      }
    }
  }
  return e;
}

// energy + net force on the ligand for a rigid pose (drives the local settle)
function rigidForce(base, gx, gy, gz, f) {
  const cs = grid.cs, c2 = CUTOFF * CUTOFF, pos = P.pos, prm = P.rmin, pep = P.eps, pq = P.q, map = grid.map;
  let e = 0, fx = 0, fy = 0, fz = 0;
  for (let i = 0; i < L.n; i++) {
    const lx = base[3 * i] + gx, ly = base[3 * i + 1] + gy, lz = base[3 * i + 2] + gz;
    const lr = L.rmin[i], le = L.eps[i], lq = L.q[i];
    const ix = Math.floor(lx / cs), iy = Math.floor(ly / cs), iz = Math.floor(lz / cs);
    for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) for (let c = -1; c <= 1; c++) {
      const bucket = map.get(cellKey(ix + a, iy + b, iz + c));
      if (!bucket) continue;
      for (let k = 0; k < bucket.length; k++) {
        const pj = bucket[k];
        const dx = lx - pos[3 * pj], dy = ly - pos[3 * pj + 1], dz = lz - pos[3 * pj + 2];
        if (dx * dx + dy * dy + dz * dz > c2) continue;
        pair(lx, ly, lz, lr, le, lq, pos[3 * pj], pos[3 * pj + 1], pos[3 * pj + 2], prm[pj], pep[pj], pq[pj], out);
        fx += out.fx; fy += out.fy; fz += out.fz; e += out.e;
      }
    }
  }
  f.x = fx; f.y = fy; f.z = fz; return e;
}
// translational gradient descent on the net force; returns the settled centroid + energy (pure — no global state)
function settlePose(base, gx, gy, gz) {
  const f = { x: 0, y: 0, z: 0 };
  let e = rigidForce(base, gx, gy, gz, f);
  for (let s = 0; s < 50; s++) {
    const m = Math.hypot(f.x, f.y, f.z);
    if (m < 3) break;
    const d = 0.25 / m;
    gx += f.x * d; gy += f.y * d; gz += f.z * d;
    e = rigidForce(base, gx, gy, gz, f);
  }
  return { gx, gy, gz, e };
}

const ROT = (() => {                             // 12 orientations covering rough SO(3)
  const m = [], P2 = Math.PI;
  for (const ay of [0, P2 / 3, 2 * P2 / 3, P2, 4 * P2 / 3, 5 * P2 / 3])
    for (const ax of [0, P2 / 2]) {
      const cy = Math.cos(ay), sy = Math.sin(ay), cx = Math.cos(ax), sx = Math.sin(ax);
      m.push([cy, 0, sy, sx * sy, cx, -sx * cy, -cx * sy, sx, cx * cy]);
    }
  return m;
})();

async function findSite() {
  if (!L || !L.n) { status('load a ligand first'); return; }
  status('scanning for the most favorable site…');
  await new Promise(r => setTimeout(r, 0));      // let the status paint (rAF is unreliable headless)

  // ligand atoms relative to their own centroid, pre-rotated into each sampled orientation
  let cx = 0, cy = 0, cz = 0;
  for (let i = 0; i < L.n; i++) { cx += L.lbase[3 * i]; cy += L.lbase[3 * i + 1]; cz += L.lbase[3 * i + 2]; }
  cx /= L.n; cy /= L.n; cz /= L.n;
  const local = new Float32Array(3 * L.n);
  for (let i = 0; i < L.n; i++) { local[3 * i] = L.lbase[3 * i] - cx; local[3 * i + 1] = L.lbase[3 * i + 1] - cy; local[3 * i + 2] = L.lbase[3 * i + 2] - cz; }
  const rotated = ROT.map(m => {
    const rb = new Float32Array(3 * L.n);
    for (let i = 0; i < L.n; i++) {
      const x = local[3 * i], y = local[3 * i + 1], z = local[3 * i + 2];
      rb[3 * i] = m[0] * x + m[1] * y + m[2] * z;
      rb[3 * i + 1] = m[3] * x + m[4] * y + m[5] * z;
      rb[3 * i + 2] = m[6] * x + m[7] * y + m[8] * z;
    }
    return rb;
  });

  // protein bounding box (+ margin); step adapts to size so the pose count stays bounded
  let mnx = 1e9, mny = 1e9, mnz = 1e9, mxx = -1e9, mxy = -1e9, mxz = -1e9;
  for (let i = 0; i < P.n; i++) {
    const x = P.pos[3 * i], y = P.pos[3 * i + 1], z = P.pos[3 * i + 2];
    if (x < mnx) mnx = x; if (y < mny) mny = y; if (z < mnz) mnz = z;
    if (x > mxx) mxx = x; if (y > mxy) mxy = y; if (z > mxz) mxz = z;
  }
  const M = 3; mnx -= M; mny -= M; mnz -= M; mxx += M; mxy += M; mxz += M;
  const span = Math.max(mxx - mnx, mxy - mny, mxz - mnz);
  const step = Math.max(3.2, span / 13);           // coarse positions; the per-candidate settle refines them
  const t0 = performance.now(), BUDGET = 2200;     // wall-clock cap

  // pass 1 — coarse scan; collect a few spatially-separated favorable positions, the single global-min
  // position, AND the current pose (so the result is never worse than where the ligand already sits).
  const cgx = cx + ligOffset.x, cgy = cy + ligOffset.y, cgz = cz + ligOffset.z;
  const SEP2 = 25, K = 6;
  const cands = [];
  const consider = (e, gx, gy, gz) => {
    for (let i = 0; i < cands.length; i++) {
      const c = cands[i], dx = c.gx - gx, dy = c.gy - gy, dz = c.gz - gz;
      if (dx * dx + dy * dy + dz * dz < SEP2) { if (e < c.e) { c.e = e; c.gx = gx; c.gy = gy; c.gz = gz; } return; }
    }
    cands.push({ e, gx, gy, gz });
    cands.sort((p, q) => p.e - q.e);
    if (cands.length > K) cands.length = K;
  };
  const coarseOri = Math.min(6, rotated.length);
  let gbe = Infinity, gbx = cgx, gby = cgy, gbz = cgz, stop = false;
  for (let ri = 0; ri < coarseOri && !stop; ri++) {
    const rb = rotated[ri];
    for (let gx = mnx; gx <= mxx && !stop; gx += step) {
      for (let gy = mny; gy <= mxy; gy += step)
        for (let gz = mnz; gz <= mxz; gz += step) {
          const e = rigidEnergy(rb, gx, gy, gz);
          if (e < gbe) { gbe = e; gbx = gx; gby = gy; gbz = gz; }
          if (e < -0.5) consider(e, gx, gy, gz);
        }
      if (performance.now() - t0 > BUDGET) stop = true;
    }
    status('scanning… ' + Math.round(80 * (ri + 1) / coarseOri) + '%');
    await new Promise(r => setTimeout(r, 0));
  }
  if (isFinite(gbe)) consider(gbe, gbx, gby, gbz);
  cands.push({ e: rigidEnergy(rotated[0], cgx, cgy, cgz), gx: cgx, gy: cgy, gz: cgz });

  // pass 2 — for each candidate: pick the best orientation there, then settle into the local well;
  // keep the deepest settled pose
  let best = null;
  for (let ci = 0; ci < cands.length; ci++) {
    const cnd = cands[ci];
    let ori = 0, oe = Infinity;
    for (let ri = 0; ri < rotated.length; ri++) {
      const e = rigidEnergy(rotated[ri], cnd.gx, cnd.gy, cnd.gz);
      if (e < oe) { oe = e; ori = ri; }
    }
    const s = settlePose(rotated[ori], cnd.gx, cnd.gy, cnd.gz);
    if (!best || s.e < best.e) best = { e: s.e, gx: s.gx, gy: s.gy, gz: s.gz, ori };
    status('settling… ' + Math.round(80 + 20 * (ci + 1) / cands.length) + '%');
    await new Promise(r => setTimeout(r, 0));
  }

  if (!best || !isFinite(best.e) || best.e >= 0) { status('no clearly favorable site found — try another conformation'); return; }
  // bake the winning orientation about the ligand's home centroid, snap to the settled centroid
  const rb = rotated[best.ori];
  for (let i = 0; i < L.n; i++) { L.lbase[3 * i] = rb[3 * i] + cx; L.lbase[3 * i + 1] = rb[3 * i + 1] + cy; L.lbase[3 * i + 2] = rb[3 * i + 2] + cz; }
  ligOffset.set(best.gx - cx, best.gy - cy, best.gz - cz);
  requestRender();
  status('best site · interaction E ' + best.e.toFixed(1) + ' kcal/mol (rigid scan + settle — drag to fine-tune)');
}

function updateProteinColors() {
  for (let i = 0; i < P.n; i++) {
    if (heatmap) heat(Math.hypot(P.fx[i], P.fy[i], P.fz[i]) / FMAX, tmpC);
    else tmpC.setRGB(P.base[3 * i], P.base[3 * i + 1], P.base[3 * i + 2]);
    P.mesh.setColorAt(i, tmpC);
  }
  P.mesh.instanceColor.needsUpdate = true;
}

// blue → cyan → green → yellow → red
function heat(t, c) {
  t = Math.min(1, Math.sqrt(Math.max(0, t)));
  const s = [[0.12, 0.18, 0.55], [0.10, 0.55, 0.95], [0.20, 0.85, 0.30], [0.97, 0.85, 0.16], [0.97, 0.22, 0.16]];
  const f = t * 4, i = Math.min(3, Math.floor(f)), u = f - i;
  c.setRGB(s[i][0] + (s[i + 1][0] - s[i][0]) * u, s[i][1] + (s[i + 1][1] - s[i][1]) * u, s[i][2] + (s[i + 1][2] - s[i][2]) * u);
}

function updateLigand() {
  if (!L || !L.mesh) return;
  for (let i = 0; i < L.n; i++) {
    dummy.position.set(L.lbase[3 * i] + ligOffset.x, L.lbase[3 * i + 1] + ligOffset.y, L.lbase[3 * i + 2] + ligOffset.z);
    dummy.scale.setScalar(L.rad[i]); dummy.updateMatrix(); L.mesh.setMatrixAt(i, dummy.matrix);
    dummy.scale.setScalar(L.rad[i] * HALO_SCALE); dummy.updateMatrix(); L.halo.setMatrixAt(i, dummy.matrix);
  }
  L.mesh.instanceMatrix.needsUpdate = true;
  L.halo.instanceMatrix.needsUpdate = true;
  L.mesh.computeBoundingSphere();
}

function ligCentroid(v) {
  if (!L || !L.n) return v.set(0, 0, 0);
  let cx = 0, cy = 0, cz = 0;
  for (let i = 0; i < L.n; i++) { cx += L.lbase[3 * i]; cy += L.lbase[3 * i + 1]; cz += L.lbase[3 * i + 2]; }
  return v.set(cx / L.n + ligOffset.x, cy / L.n + ligOffset.y, cz / L.n + ligOffset.z);
}

function updateArrow(f) {
  if (f.mag < 0.2) { arrow.visible = false; return; }
  arrow.visible = true;
  ligCentroid(arrow.position);
  arrow.setDirection(tmpV.set(f.nx, f.ny, f.nz).normalize());
  const len = Math.min(28, f.mag * 0.35);
  arrow.setLength(len, len * 0.32, len * 0.18);
  arrow.setColor(f.evdw + f.eelec < 0 ? 0x39d6ff : 0xff5a4d);  // net attractive cyan / repulsive red
}
const tmpV = new THREE.Vector3();

function updateUI(f) {
  ui('evdw', f.evdw.toFixed(1) + ' kcal/mol');
  ui('eelec', f.eelec.toFixed(1) + ' kcal/mol');
  ui('etot', (f.evdw + f.eelec).toFixed(1) + ' kcal/mol');
  ui('fnet', f.mag.toFixed(1));
}
const ui = (id, t) => { document.getElementById(id).textContent = t; };

// On-demand rendering via microtask (NOT requestAnimationFrame — rAF is throttled/paused in
// background/headless tabs, which would freeze the view). Coalesces bursts into one render.
let pending = false;
function requestRender() {
  if (pending) return;
  pending = true;
  queueMicrotask(() => { pending = false; renderFrame(); });
}
function renderFrame() {
  const f = computeForces();
  updateLigand();
  updateProteinColors();
  updateArrow(f);
  updateUI(f);
  renderer.render(scene, camera);
}

function setupDrag() {
  const ray = new THREE.Raycaster(), ptr = new THREE.Vector2();
  const plane = new THREE.Plane(), hit = new THREE.Vector3(), startHit = new THREE.Vector3(), startOff = new THREE.Vector3();
  let dragging = false;
  const set = (e) => ptr.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  renderer.domElement.addEventListener('pointerdown', (e) => {
    set(e); ray.setFromCamera(ptr, camera);
    if (L && L.mesh && ray.intersectObject(L.mesh).length) {
      dragging = true; controls.enabled = false;
      plane.setFromNormalAndCoplanarPoint(camera.getWorldDirection(tmpV).clone(), ligCentroid(new THREE.Vector3()));
      ray.ray.intersectPlane(plane, startHit); startOff.copy(ligOffset);
    }
  });
  addEventListener('pointermove', (e) => {
    if (!dragging) return;
    set(e); ray.setFromCamera(ptr, camera);
    if (ray.ray.intersectPlane(plane, hit)) { ligOffset.copy(startOff).add(hit).sub(startHit); requestRender(); }
  });
  addEventListener('pointerup', () => { dragging = false; controls.enabled = true; });
}

function fitCamera() {
  let r = 0;
  for (const a of P.atoms) r = Math.max(r, Math.hypot(a.x, a.y, a.z));
  if (L && L.atoms) for (const a of L.atoms) r = Math.max(r, Math.hypot(a.x, a.y, a.z));
  camera.position.set(0, 0, (r || 40) * 2.6); controls.update(); requestRender();
}

function onResize() {
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight); requestRender();
}

function setupUI() {
  document.getElementById('reset').onclick = () => {
    if (L && L.lbase0) L.lbase.set(L.lbase0);      // also undo a scan's baked rotation
    ligOffset.set(0, 0, 0); requestRender();
  };
  document.getElementById('findSite').onclick = findSite;
  const fb = document.getElementById('forces');
  fb.onclick = () => { heatmap = !heatmap; fb.textContent = 'Force heatmap: ' + (heatmap ? 'ON' : 'OFF'); requestRender(); };
  document.getElementById('minimize').onclick = onMinimize;
}

async function pollHealth() {
  const s = document.getElementById('status'), btn = document.getElementById('minimize');
  // the OpenMM worker is a local-only dev feature; hide it on a deployed site (an HTTPS page can't
  // reach http://127.0.0.1 anyway — mixed content — so the button would just sit dead + confusing).
  if (location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
    s.style.display = 'none'; btn.style.display = 'none'; return;
  }
  const h = await checkHealth();
  if (h.ok) { s.textContent = 'worker: ' + (h.cuda ? 'ready (CUDA)' : 'ready'); btn.disabled = false; }
  else s.textContent = 'worker: offline (start_worker.bat)';
}

async function onMinimize() {
  const btn = document.getElementById('minimize'), s = document.getElementById('status');
  if (!L || !L.n) { s.textContent = 'load a ligand first'; return; }
  btn.disabled = true; s.textContent = 'worker: minimizing…';
  const pdb = poseToPdb(P, L, ligOffset);
  const r = await minimize(pdb);
  if (r.ok) s.textContent = `OpenMM PE ${r.energy_after_kcal?.toFixed?.(0) ?? r.energy_after_kcal} kcal/mol (${r.platform}, ${r.seconds}s)`;
  else s.textContent = 'minimize failed: ' + (r.error || '?');
  btn.disabled = false;
}
