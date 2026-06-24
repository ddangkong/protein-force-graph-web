import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { parsePdb } from './pdb.js';
import { parseSdf } from './sdf.js';
import { elem } from './chemistry.js';
import { lj, charge, pair } from './forcefield.js';
import { checkHealth, minimize, poseToPdb } from './openmm.js';

const CUTOFF = 9.0;          // Å — live nonbonded interaction range
const PROT_SCALE = 0.42;     // sphere radius = scale * vdW
const LIG_SCALE = 0.55;
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
const ligMat = new THREE.MeshStandardMaterial({ roughness: 0.4 });

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
  const text = await (await fetch('1HSG.pdb')).text();
  const d = parsePdb(text);
  setStructure(d.protein, d.ligand, true);
}

// Rebuild the whole scene from a protein + ligand atom set (centered on the protein centroid).
function setStructure(protAtoms, ligAtoms, refit) {
  let cx = 0, cy = 0, cz = 0; const pn = protAtoms.length || 1;
  for (const a of protAtoms) { cx += a.x; cy += a.y; cz += a.z; } cx /= pn; cy /= pn; cz /= pn;
  for (const a of protAtoms) { a.x -= cx; a.y -= cy; a.z -= cz; }
  for (const a of ligAtoms) { a.x -= cx; a.y -= cy; a.z -= cz; }
  if (P && P.mesh) { scene.remove(P.mesh); P.mesh.dispose(); }
  if (L && L.mesh) { scene.remove(L.mesh); L.mesh.dispose(); }
  ligOffset.set(0, 0, 0);
  buildProtein(protAtoms);
  if (ligAtoms.length) buildLigand(ligAtoms);
  else L = { n: 0, atoms: [], lbase: new Float32Array(0), mesh: null };
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

function status(t) { const s = document.getElementById('status'); if (s) s.textContent = t; }

function setupLoaders() {
  document.getElementById('loadProt').onclick = () => pickFile('.pdb', (t) => loadProteinText(t));
  document.getElementById('loadLig').onclick = () => pickFile('.sdf,.mol,.mol2,.pdb', (t, name) => loadLigandText(t, extOf(name)));
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
  const base = new Float32Array(3 * n), resKey = new Array(n);
  const mesh = new THREE.InstancedMesh(sphereGeo, protMat, n);
  for (let i = 0; i < n; i++) {
    const a = arr[i];
    pos[3 * i] = a.x; pos[3 * i + 1] = a.y; pos[3 * i + 2] = a.z;
    const lp = lj(a.el); rmin[i] = lp[0]; eps[i] = lp[1]; q[i] = charge(a.el);
    resKey[i] = a.chain + a.resSeq;
    dummy.position.set(a.x, a.y, a.z); dummy.scale.setScalar(elem(a.el).vdw * PROT_SCALE);
    dummy.updateMatrix(); mesh.setMatrixAt(i, dummy.matrix);
    tmpC.set(elem(a.el).color); base[3 * i] = tmpC.r; base[3 * i + 1] = tmpC.g; base[3 * i + 2] = tmpC.b;
    mesh.setColorAt(i, tmpC);
  }
  mesh.instanceMatrix.needsUpdate = true; mesh.instanceColor.needsUpdate = true;
  scene.add(mesh);
  P = { n, pos, rmin, eps, q, base, mesh, resKey, atoms: arr,
        fx: new Float32Array(n), fy: new Float32Array(n), fz: new Float32Array(n) };
}

function buildLigand(arr) {
  const n = arr.length;
  const lbase = new Float32Array(3 * n), rmin = new Float32Array(n), eps = new Float32Array(n), q = new Float32Array(n), rad = new Float32Array(n);
  const mesh = new THREE.InstancedMesh(sphereGeo, ligMat, n);
  for (let i = 0; i < n; i++) {
    const a = arr[i];
    lbase[3 * i] = a.x; lbase[3 * i + 1] = a.y; lbase[3 * i + 2] = a.z;
    const lp = lj(a.el); rmin[i] = lp[0]; eps[i] = lp[1]; q[i] = charge(a.el); rad[i] = elem(a.el).vdw * LIG_SCALE;
    dummy.position.set(a.x, a.y, a.z); dummy.scale.setScalar(rad[i]); dummy.updateMatrix(); mesh.setMatrixAt(i, dummy.matrix);
    mesh.setColorAt(i, tmpC.set(a.el === 'C' ? 0x35e06a : elem(a.el).color));
  }
  mesh.instanceMatrix.needsUpdate = true; mesh.instanceColor.needsUpdate = true;
  scene.add(mesh);
  L = { n, lbase, rmin, eps, q, rad, mesh, atoms: arr,
        resName: arr[0] ? arr[0].resName : 'MK1', resSeq: arr[0] ? arr[0].resSeq : 1, chain: arr[0] ? arr[0].chain : 'B' };
}

function buildGrid() {
  const cs = CUTOFF, map = new Map();
  for (let i = 0; i < P.n; i++) {
    const k = ck(P.pos[3 * i], P.pos[3 * i + 1], P.pos[3 * i + 2], cs);
    let b = map.get(k); if (!b) { b = []; map.set(k, b); } b.push(i);
  }
  grid = { cs, map };
}
const ck = (x, y, z, cs) => Math.floor(x / cs) + ',' + Math.floor(y / cs) + ',' + Math.floor(z / cs);

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
      const bucket = grid.map.get((ix + a) + ',' + (iy + b) + ',' + (iz + c));
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
  }
  L.mesh.instanceMatrix.needsUpdate = true;
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
  document.getElementById('reset').onclick = () => { ligOffset.set(0, 0, 0); requestRender(); };
  const fb = document.getElementById('forces');
  fb.onclick = () => { heatmap = !heatmap; fb.textContent = 'Force heatmap: ' + (heatmap ? 'ON' : 'OFF'); requestRender(); };
  document.getElementById('minimize').onclick = onMinimize;
}

async function pollHealth() {
  const h = await checkHealth();
  const s = document.getElementById('status');
  if (h.ok) { s.textContent = 'worker: ' + (h.cuda ? 'ready (CUDA)' : 'ready'); document.getElementById('minimize').disabled = false; }
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
