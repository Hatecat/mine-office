// Oficina de agentes: escena, personajes, salas y comportamiento.
import * as V from './voxel.js';
import { roomShell, doorCells } from './shell.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { initCosts, loadUsage, memberCost, money } from './costs.js';
import { initListen } from './listen.js';
const { THREE, rng, hash, shade, pick, px, noiseFill, pixelTex, lam, box, instCubes, disposeTree, MAT, UNIT } = V;

const DEMO = new URLSearchParams(location.search).has('demo');
const TOKEN = document.querySelector('meta[name=office-token]')?.content || '';
async function api(path, body) {
  const res = await fetch(path, body === undefined ? { cache: 'no-store' } : {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Office-Token': TOKEN }, body: JSON.stringify(body),
  });
  if (res.status === 403 && body !== undefined) throw new Error('La oficina se reinició y esta pestaña tiene un permiso caducado: recarga la página (F5)');
  const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
  if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}
export { api };
const POLL_MS = 2000;
const IDLE_LEAVE = new URLSearchParams(location.search).has('fast') ? 0.5 : DEMO ? 3 : 8;      // s en espera antes de levantarse de la mesa
const WALK_SPEED = new URLSearchParams(location.search).has('fast') ? 20 : 2.6;               // bloques por segundo

// ---------- salas del ala nueva ----------
// col: columna del ala (A junto a la oficina, B al fondo). size: tamaño previsto (el módulo manda si carga).
// side: L = a la izquierda de la oficina (en espejo, puerta mirando a la oficina), R = a la derecha.
const ROOMS = [
  { file: 'cafeteria', side: 'L', size: [10, 8], weight: 4 },
  { file: 'juegos', side: 'L', size: [10, 8], weight: 2.5 },
  { file: 'vestuario', side: 'L', size: [8, 6], weight: 0 },
  { file: 'descanso', side: 'R', size: [8, 6], weight: 2.5 },
  { file: 'reuniones', variant: 'A', side: 'R', size: [8, 5], weight: 0.6 },
  { file: 'reuniones', variant: 'B', side: 'R', size: [8, 5], weight: 0.6 },
];
const WHERE = { cafeteria: 'en la cafetería', juegos: 'en la sala de juegos', descanso: 'descansando', reuniones: 'en una reunión', vestuario: 'en el vestuario' };

// ---------- familias de modelos ----------
const FAM = {
  opus: { col: '#9b6cff', name: 'Opus' }, sonnet: { col: '#f08a3c', name: 'Sonnet' }, haiku: { col: '#45c47a', name: 'Haiku' },
  fable: { col: '#2bb5c4', name: 'Fable' }, opencode: { col: '#3d7bf0', name: 'OpenCode' }, other: { col: '#a0a8b8', name: 'Otro' },
};
function family(a) {
  if (a.kind === 'opencode') return 'opencode';
  const m = (a.model || '').toLowerCase();
  for (const f of ['opus', 'sonnet', 'haiku', 'fable']) if (m.includes(f)) return f;
  return 'other';
}
document.getElementById('legend').innerHTML = Object.values(FAM).map(f => `<span><i style="background:${f.col}"></i>${f.name}</span>`).join('');

// ---------- escena ----------
const renderer = new THREE.WebGLRenderer({ antialias: false });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
document.getElementById('view').appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x8ec5ff);
scene.fog = new THREE.Fog(0x8ec5ff, 60, 140);
const camera = new THREE.PerspectiveCamera(42, innerWidth / innerHeight, 0.1, 300);
camera.position.set(14, 13, 18);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.maxPolarAngle = Math.PI * 0.46; controls.minDistance = 3; controls.maxDistance = 95;
scene.add(new THREE.HemisphereLight(0xe4f1ff, 0x6b5843, 1.5));
const sun = new THREE.DirectionalLight(0xfff0d0, 2.2);
sun.castShadow = true; sun.shadow.mapSize.set(4096, 4096); sun.shadow.bias = -0.0005;
scene.add(sun, sun.target);
addEventListener('resize', () => { camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight); });

// ---------- pantallas animadas (compartidas) ----------
function screenCanvas() { const c = document.createElement('canvas'); c.width = 64; c.height = 36; return c; }
const busyCanvas = screenCanvas(), idleCanvas = screenCanvas();
const busyTex = new THREE.CanvasTexture(busyCanvas), idleTex = new THREE.CanvasTexture(idleCanvas);
for (const t of [busyTex, idleTex]) { t.magFilter = t.minFilter = THREE.NearestFilter; t.colorSpace = THREE.SRGBColorSpace; t.generateMipmaps = false; }
const codeLines = Array.from({ length: 40 }, (_, i) => { const r = rng(i + 99); return { indent: Math.floor(r() * 4) * 4, segs: Array.from({ length: 1 + Math.floor(r() * 3) }, () => ({ w: 4 + Math.floor(r() * 16), c: pick(['#7ee787', '#79c0ff', '#ffa657', '#d2a8ff', '#e6edf3'], r) })) }; });
let scrollT = -1;
function drawScreens(t) {
  const step = Math.floor(t * 8);
  if (step === scrollT) return; scrollT = step;
  let g = busyCanvas.getContext('2d');
  g.fillStyle = '#0d1117'; g.fillRect(0, 0, 64, 36);
  for (let row = 0; row < 9; row++) {
    const ln = codeLines[(row + step) % codeLines.length]; let x = 3 + ln.indent;
    for (const s of ln.segs) { g.fillStyle = s.c; g.fillRect(x, 2 + row * 4, Math.min(s.w, 62 - x), 2); x += s.w + 3; if (x > 60) break; }
  }
  if (step % 2) { g.fillStyle = '#fff'; g.fillRect(4, 30, 3, 2); }
  busyTex.needsUpdate = true;
  g = idleCanvas.getContext('2d');
  g.fillStyle = '#10182c'; g.fillRect(0, 0, 64, 36);
  const bx = Math.abs(((step * 0.7) % 104) - 52) + 2, by = Math.abs(((step * 0.45) % 56) - 28) + 2;
  g.fillStyle = '#ffb347'; g.fillRect(Math.floor(bx), Math.floor(by), 6, 4);
  idleTex.needsUpdate = true;
}
const zTex = pixelTex(8, 8, (g) => { g.fillStyle = '#fff'; g.fillRect(1, 1, 6, 1); g.fillRect(5, 2, 1, 1); g.fillRect(4, 3, 1, 1); g.fillRect(3, 4, 1, 1); g.fillRect(2, 5, 1, 1); g.fillRect(1, 6, 6, 1); }, 3);

// ---------- personajes ----------
const SKIN = ['#f1c9a5', '#e0ac85', '#c68863', '#8d5a3b', '#f5d7bd', '#b07250'];
const HAIR = ['#2b1d14', '#5a3a1e', '#c7a15a', '#151515', '#8a2b1b', '#d6d6d6', '#3b2a5a', '#2f5d8a'];
const PANTS = ['#3b4a6b', '#2d2d33', '#4a3b2d', '#30473a'];
const SEAT_HIP = 0.11, STAND_HIP = 0.8;
function shirtTex(c, seed) { return pixelTex(8, 8, (g, r) => { noiseFill(g, r, 8, 8, c, 0.12); px(g, 3, 0, shade(c, 0.6)); px(g, 4, 0, shade(c, 0.6)); }, seed); }

function makeCharacter(seed, look = {}) {
  const r = rng(seed);
  let skin = pick(SKIN, r), hair = pick(HAIR, r), pants = pick(PANTS, r); const eye = '#1d1d2b';
  skin = look.skin || skin; hair = look.hair || hair; pants = look.pants || pants;
  const face = pixelTex(8, 8, (g, rr) => {
    noiseFill(g, rr, 8, 8, skin, 0.06);
    for (let x = 0; x < 8; x++) { px(g, x, 0, hair); px(g, x, 1, shade(hair, 0.9 + rr() * 0.2)); }
    px(g, 0, 2, hair); px(g, 7, 2, hair);
    px(g, 1, 4, '#fff'); px(g, 2, 4, eye); px(g, 5, 4, eye); px(g, 6, 4, '#fff');
    px(g, 3, 6, shade(skin, 0.7)); px(g, 4, 6, shade(skin, 0.7));
  }, seed);
  const side = pixelTex(8, 8, (g, rr) => { noiseFill(g, rr, 8, 8, skin, 0.06); for (let y = 0; y < 3; y++) for (let x = 0; x < 8; x++) px(g, x, y, shade(hair, 0.85 + rr() * 0.3)); }, seed + 1);
  const back = pixelTex(8, 8, (g, rr) => { noiseFill(g, rr, 8, 8, skin, 0.06); for (let y = 0; y < 6; y++) for (let x = 0; x < 8; x++) px(g, x, y, shade(hair, 0.85 + rr() * 0.3)); }, seed + 2);
  const top = pixelTex(8, 8, (g, rr) => noiseFill(g, rr, 8, 8, hair, 0.3), seed + 3);
  const skinM = new THREE.MeshLambertMaterial({ color: skin });
  const shirtM = lam(null);
  const pantsM = lam(pixelTex(8, 8, (g, rr) => noiseFill(g, rr, 8, 8, pants, 0.12), seed + 4));
  const own = [face, side, back, top];

  const root = new THREE.Group();          // cadera
  const body = new THREE.Group(); root.add(body);
  const torso = box(0.5, 0.7, 0.28, shirtM, 0, 0.35, 0);
  const head = new THREE.Mesh(UNIT, [lam(side), lam(side), lam(top), skinM, lam(face), lam(back)]);
  head.scale.setScalar(0.5); head.position.y = 0.95; head.castShadow = true;
  const arms = [-1, 1].map(s => {
    const pivot = new THREE.Group(); pivot.position.set(0.36 * s, 0.65, 0);
    pivot.add(box(0.2, 0.6, 0.2, shirtM, 0, -0.3, 0), box(0.2, 0.12, 0.2, skinM, 0, -0.66, 0));
    body.add(pivot); return pivot;
  });
  const legs = [-1, 1].map(s => {
    const hip = new THREE.Group(); hip.position.set(0.13 * s, 0, 0);
    hip.add(box(0.22, 0.32, 0.22, pantsM, 0, -0.15, 0));
    const knee = new THREE.Group(); knee.position.y = -0.3;
    knee.add(box(0.22, 0.5, 0.22, pantsM, 0, -0.25, 0));
    hip.add(knee); root.add(hip);
    return { hip, knee };
  });
  body.add(torso, head);
  // objetos de mano (ocultos salvo en ciertas actividades)
  const cup = new THREE.Group();
  cup.add(box(0.14, 0.16, 0.14, V.col(0xf2efe8), 0, 0, 0), box(0.1, 0.02, 0.1, V.col(0x4a2c17), 0, 0.075, 0));
  cup.position.set(0, -0.72, 0.1); cup.visible = false; arms[1].add(cup);
  const book = box(0.32, 0.05, 0.24, V.col(0x3a6bb2), 0, -0.7, 0.12); book.visible = false; arms[0].add(book);
  // accesorios (van en la cabeza: la cabeza es un cubo unidad escalado a 0.5, así que se ponen en el cuerpo)
  const acc = look.accessory;
  if (acc === 'gafas') {
    const fr = V.col(0x15151a), lens = V.glow(0x9fd8ff);
    body.add(box(0.5, 0.05, 0.03, fr, 0, 1.0, 0.265), box(0.15, 0.11, 0.02, lens, -0.11, 0.99, 0.27), box(0.15, 0.11, 0.02, lens, 0.11, 0.99, 0.27));
  } else if (acc === 'gorra') {
    const capM = V.col(look.shirt ? shade(look.shirt, 0.7) : 0xb03030);
    body.add(box(0.54, 0.14, 0.54, capM, 0, 1.24, 0), box(0.44, 0.04, 0.24, capM, 0, 1.19, 0.36));
  } else if (acc === 'auriculares') {
    const hm = V.col(0x24242c), pad = V.col(0xe94f8a);
    body.add(box(0.64, 0.07, 0.1, hm, 0, 1.24, 0), box(0.08, 0.2, 0.2, pad, -0.29, 0.97, 0), box(0.08, 0.2, 0.2, pad, 0.29, 0.97, 0));
  }
  // capa del jefe: cuelga de los hombros y se mece al andar; lleva bordada una chispa
  let cape = null;
  if (acc === 'capa') {
    const cc = look.cape || '#d97757';
    const capeTex = pixelTex(8, 12, (g, rr) => {
      noiseFill(g, rr, 8, 12, cc, 0.08);
      for (let y = 0; y < 12; y++) { px(g, 0, y, shade(cc, 0.78)); px(g, 7, y, shade(cc, 0.78)); }
      for (let x = 0; x < 8; x++) px(g, x, 11, shade(cc, 0.7));
      const st = '#fff3dc';
      for (const [x, y] of [[3, 3], [4, 3], [3, 4], [4, 4], [3, 2], [4, 2], [3, 5], [4, 5], [2, 3], [5, 3], [2, 4], [5, 4], [3, 1], [4, 6]]) px(g, x, y, st);
    }, seed + 9);
    own.push(capeTex);
    const capeM = lam(capeTex), inner = V.col(shade(cc, 0.6));
    cape = new THREE.Group(); cape.position.set(0, 0.68, -0.17);
    // la cara de fuera (-z) lleva la chispa; por dentro, tono más oscuro
    const cm = new THREE.Mesh(UNIT, [inner, inner, inner, inner, inner, capeM]);
    cm.scale.set(0.64, 1.02, 0.04); cm.position.set(0, -0.5, 0); cm.castShadow = true; cape.add(cm);
    body.add(cape);
    const gold = V.col(0xf0c419);
    body.add(box(0.58, 0.07, 0.34, V.col(shade(cc, 0.85)), 0, 0.7, -0.02), box(0.1, 0.1, 0.04, gold, -0.2, 0.62, 0.15), box(0.1, 0.1, 0.04, gold, 0.2, 0.62, 0.15));
  }
  return { root, body, head, torso, arms, legs, cup, book, shirtM, own, cape };
}

function setPose(ch, pose) {
  const sit = pose === 'sit';
  for (const l of ch.legs) { l.hip.rotation.x = sit ? -Math.PI / 2 : 0; l.knee.rotation.x = sit ? Math.PI / 2 : 0; }
}

// ---------- etiquetas ----------
function labelSprite(w = 512, h = 128, sx = 3.4, sy = 0.85) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, depthTest: false, depthWrite: false }));
  s.scale.set(sx, sy, 1); s.renderOrder = 10;
  return { sprite: s, canvas: c, tex: t };
}
function fit(g, text, maxW) { if (g.measureText(text).width <= maxW) return text; while (text.length > 1 && g.measureText(text + '…').width > maxW) text = text.slice(0, -1); return text + '…'; }
function statusLine(a, where) {
  if (a.status === 'busy') return a.tool ? `${a.tool}${a.detail ? ': ' + a.detail : ''}` : 'pensando…';
  if (a.status === 'offline') return where || 'descansando';
  return where || 'en espera';
}
const STATUS_TXT = { busy: 'trabajando', idle: 'en espera', offline: 'descansando' };
function drawLabel(L, a, colr, selected, where) {
  const g = L.canvas.getContext('2d'); g.clearRect(0, 0, 512, 128);
  g.fillStyle = 'rgba(15,18,26,0.86)'; g.fillRect(6, 10, 500, 108);
  g.strokeStyle = selected ? '#ffe14d' : '#000'; g.lineWidth = 6; g.strokeRect(6, 10, 500, 108);
  g.fillStyle = colr; g.fillRect(16, 22, 12, 84);
  g.font = '50px VT323, monospace'; g.fillStyle = '#fff';
  const nm = fit(g, a.name + (a.kind === 'subagent' ? ' (sub)' : ''), 300);
  g.fillText(nm, 42, 60);
  if (a.job) {   // cargo al lado del nombre, más pequeño
    const x = 42 + g.measureText(nm).width + 12;
    g.font = '34px VT323, monospace'; g.fillStyle = '#ffd98a';
    g.fillText(fit(g, '· ' + a.job, 466 - x), x, 58);
  }
  g.font = '38px VT323, monospace'; g.fillStyle = a.status === 'busy' ? '#7dffa0' : a.status === 'offline' ? '#a9c4ff' : '#ffc77a';
  g.fillText(fit(g, statusLine(a, where), 450), 42, 100);
  L.tex.needsUpdate = true;
}

// ---------- globos de aviso ----------
const ATT = {
  listo:   { title: '¡Terminé!', sub: 'mira lo que hice', bg: '#fff6d6', edge: '#e0a030', icon: '✔', ic: '#2f9a4a' },
  permiso: { title: '¡Necesito permiso!', sub: 'confírmame algo', bg: '#ffe0e0', edge: '#e66767', icon: '!', ic: '#d23c3c' },
  pregunta:{ title: '¡Una pregunta!', sub: 'te estoy esperando', bg: '#e3ecff', edge: '#3987e5', icon: '?', ic: '#2a62c9' },
  atasco:  { title: '¿Me he colgado?', sub: '', bg: '#f1e6ff', edge: '#9085e9', icon: '…', ic: '#6a55c8' },
  rescate: { title: '¡Desatasco!', sub: '', bg: '#fff0dc', edge: '#d95926', icon: '↺', ic: '#b8481c' },
  peticion:{ title: 'Esperando al jefe', sub: 'le pedí algo a Claude', bg: '#fff6d6', edge: '#c98500', icon: '✉', ic: '#8a5c00' },
  buzon:   { title: '¡Tengo peticiones!', sub: '', bg: '#fff6d6', edge: '#d97757', icon: '✉', ic: '#b5532f' },
  voz:     { title: 'Liberty dice:', sub: '', bg: '#f4ecff', edge: '#9085e9', icon: '♪', ic: '#6a55c8' },
  cambio:  { title: '¡Cambio de modelo!', sub: '', bg: '#e2f6ea', edge: '#199e70', icon: '⇄', ic: '#16805a' },
};
const ackedLocal = new Map();   // sid -> t del aviso ya visto
const liveAttention = a => a?.attention && (ackedLocal.get(a.attention.sid) || 0) < a.attention.t ? a.attention : null;
function attentionSub(att) {
  const m = att.msg || '';
  if (att.kind === 'permiso') {
    const tool = m.match(/(?:to use|para)\s+([A-Za-z_]+)/i);
    return tool ? `para usar ${tool[1]}` : ATT.permiso.sub;
  }
  if (att.kind === 'cambio' || att.kind === 'rescate') return m || 'reorganicé el trabajo';
  if (att.kind === 'voz' || att.kind === 'buzon') return m;
  if (att.kind === 'peticion') return m.replace(/^.*? le pide al jefe: /, '') || ATT.peticion.sub;
  if (att.kind === 'atasco') return (m || 'sin avanzar') + ' en mi ventana';
  return ATT[att.kind].sub;
}
function drawBubble(B, att) {
  const k = ATT[att.kind] || ATT.listo, g = B.canvas.getContext('2d');
  g.clearRect(0, 0, 512, 192);
  // cuerpo con esquinas recortadas (pixel art) y piquito hacia abajo
  const path = () => { g.beginPath(); g.moveTo(18, 8); g.lineTo(494, 8); g.lineTo(504, 18); g.lineTo(504, 126); g.lineTo(494, 136);
    g.lineTo(278, 136); g.lineTo(256, 172); g.lineTo(234, 136); g.lineTo(18, 136); g.lineTo(8, 126); g.lineTo(8, 18); g.closePath(); };
  path(); g.fillStyle = k.bg; g.fill(); g.lineWidth = 8; g.strokeStyle = '#0b0d13'; g.stroke();
  g.fillStyle = k.edge; g.fillRect(16, 16, 8, 112);
  g.fillStyle = k.ic; g.fillRect(36, 34, 72, 72);
  g.fillStyle = '#fff'; g.font = '68px VT323, monospace'; g.textAlign = 'center'; g.fillText(k.icon, 72, 92);
  g.textAlign = 'left'; g.fillStyle = '#14161c';
  if (att.kind === 'voz') {   // lo que dice Liberty: texto en dos líneas
    g.font = '36px VT323, monospace';
    const words = (att.msg || '').split(' '); const lines = ['']; 
    for (const w of words) { const t = (lines.at(-1) + ' ' + w).trim(); if (g.measureText(t).width > 370 && lines.at(-1)) lines.push(w); else lines[lines.length - 1] = t; }
    lines.slice(0, 3).forEach((l, i) => g.fillText(i === 2 && lines.length > 3 ? fit(g, l + '…', 370) : l, 120, 48 + i * 36));
    B.tex.needsUpdate = true; return;
  }
  g.font = '50px VT323, monospace';
  g.fillText(fit(g, k.title, 370), 120, 70);
  g.font = '36px VT323, monospace'; g.fillStyle = '#4a5064';
  g.fillText(fit(g, attentionSub(att), 370), 120, 110);
  B.tex.needsUpdate = true;
}
function ackAttention(a) {
  const att = liveAttention(a); if (!att) return;
  ackedLocal.set(att.sid, att.t);
  if (!DEMO) api('/api/ack', { sid: att.sid }).catch(() => {});
  stations.get(a.id)?.update(a);
}

// ---------- plano ----------
const SPX = 2.4, SPZ = 4, MAXC = 5;
let plan = null;           // { office bounds, c1, c2, frontZ, rooms: [{...cfg, ox, oz, W, D, doorZ, doorX, corridorX}] }
const roomsLoaded = new Map(); // file -> module | null
const occupied = new Map();    // spotKey -> agentId

function computePlan(b) {
  const sizeOf = r => (roomsLoaded.get(r.file)?.meta?.size) || r.size;
  const rooms = [];
  const stack = (list, side) => {
    let z = b.minZ;
    list.forEach((r, i) => {
      const [W, D] = sizeOf(r);
      const [d0, d1] = doorCells({ size: [W, D] });
      const room = { ...r, W, D, oz: z, first: i === 0, doorZ: z + (d0 + d1) / 2, key: r.file + (r.variant || '') };
      if (side === 'L') {           // espejo: x_mundo = ox - x_local; la pared de la puerta queda en ox + 1
        room.mirror = true; room.ox = b.minX - 5; room.doorX = b.minX - 4; room.inX = room.ox - 0.6;
        room.x0 = room.ox - W; room.x1 = room.ox + 1;
      } else {
        room.mirror = false; room.ox = b.maxX + 4; room.doorX = b.maxX + 3; room.inX = room.ox + 0.6;
        room.x0 = room.ox - 1; room.x1 = room.ox + W;
      }
      rooms.push(room);
      z += D + 1;
    });
    return z;
  };
  const endL = stack(ROOMS.filter(r => r.side === 'L'), 'L');
  const endR = stack(ROOMS.filter(r => r.side === 'R'), 'R');
  return {
    b, rooms, endL, endR, cL: b.minX - 2.5, c1: b.maxX + 1.5,
    minX: Math.min(...rooms.map(r => r.x0)), maxX: Math.max(...rooms.map(r => r.x1)),
    minZ: b.minZ - 1, maxZ: Math.max(b.maxZ, endL, endR),
  };
}
// filas de pasillo entre mesas (donde la pared izquierda de la oficina tiene puerta)
function aisleZs(b) { const out = []; for (let r = 0; r * SPZ - 1.6 <= b.maxZ; r++) out.push(r * SPZ - 1.6); return out; }

function officeLayout(agents, teams = []) {
  const groups = [], placed = new Set();
  const boss = agents.find(a => a.boss);
  if (boss) {
    const ms = [boss, ...agents.filter(a => a.secretary), ...agents.filter(a => a.parent === boss.id)];
    groups.push({ name: 'Dirección', color: '#d97757', members: ms }); ms.forEach(a => placed.add(a.id));
  }
  for (const t of teams) {
    const members = agents.filter(a => a.kind === 'member' && a.team === t.id);
    const withSubs = members.flatMap(m => [m, ...agents.filter(a => a.parent === m.id)]);
    if (withSubs.length) groups.push({ name: t.name, color: t.color, members: withSubs });
  }
  groups.forEach(g => g.members.forEach(m => placed.add(m.id)));
  const loose = agents.filter(a => a.kind === 'member' && !placed.has(a.id));
  if (loose.length) { groups.push({ name: 'Sin equipo', fam: 'other', members: loose }); loose.forEach(a => placed.add(a.id)); }
  for (const s of agents.filter(a => a.kind === 'session' && !placed.has(a.id))) {
    const ms = [s, ...agents.filter(a => a.parent === s.id)];
    groups.push({ name: s.name + ' (visita)', fam: family(s), members: ms }); ms.forEach(a => placed.add(a.id));
  }
  const orphans = agents.filter(a => a.kind === 'subagent' && !placed.has(a.id));
  if (orphans.length) { groups.push({ name: 'Subagentes', fam: 'other', members: orphans }); orphans.forEach(a => placed.add(a.id)); }
  const oc = agents.filter(a => !placed.has(a.id));
  if (oc.length) groups.push({ name: 'Zona OpenCode', fam: 'opencode', members: oc });
  let row = 0, maxCol = 0; const pos = new Map(), rugs = [];
  for (const g of groups) {
    const n = g.members.length, rows = Math.ceil(n / MAXC);
    g.members.forEach((m, i) => { const c = i % MAXC; pos.set(m.id, [c * SPX, (row + Math.floor(i / MAXC)) * SPZ]); maxCol = Math.max(maxCol, c); });
    rugs.push({ x0: -1.1, x1: (Math.min(n, MAXC) - 1) * SPX + 1.1, z0: row * SPZ - 0.75, z1: (row + rows - 1) * SPZ + 1.75, fam: g.fam, color: g.color, name: g.name });
    row += rows;
  }
  const bounds = { minX: -3, maxX: Math.ceil(Math.max(maxCol, 2) * SPX + 0.9) + 1, minZ: -3, maxZ: Math.ceil(Math.max(row - 1, 1) * SPZ + 1.75) + 1 };
  return { pos, rugs, bounds };
}

// ---------- construcción del edificio ----------
let world = null, worldKey = '', rugGroup = null, rugKey = '', firstFrame = true;
const roomTicks = [];
function buildWorld(b) {
  const key = JSON.stringify(b) + [...roomsLoaded.keys()].join(); if (key === worldKey) return; worldKey = key;
  if (world) { scene.remove(world); disposeTree(world); }
  roomTicks.length = 0;
  occupied.clear();
  for (const s of stations.values()) s.sendHome(true);
  plan = computePlan(b);
  world = new THREE.Group();
  const footprint = new Set();
  for (const r of plan.rooms) for (let x = r.x0; x <= r.x1; x++) for (let z = r.oz - 1; z <= r.oz + r.D; z++) footprint.add(x + ',' + z);
  const floor = [], grass = [], dirt = [];
  for (let x = plan.minX - 6; x <= plan.maxX + 6; x++) for (let z = plan.minZ - 6; z <= plan.maxZ + 6; z++) {
    const inOffice = x >= b.minX - 1 && x <= b.maxX && z >= b.minZ - 1 && z <= b.maxZ;
    const inCL = (x === b.minX - 3 || x === b.minX - 2) && z >= b.minZ - 1 && z <= plan.endL;
    const inCR = (x === b.maxX + 1 || x === b.maxX + 2) && z >= b.minZ - 1 && z <= plan.endR;
    if (footprint.has(x + ',' + z)) { /* la sala pone su suelo */ }
    else if (inOffice || inCL || inCR) floor.push([x, -0.5, z]);
    else grass.push([x, -0.5, z]);
    dirt.push([x, -1.5, z]);
  }
  world.add(instCubes(floor, MAT.planks), instCubes(grass, MAT.grass), instCubes(dirt, MAT.dirt, false));
  // paredes de la oficina: fondo, e izquierda con una puerta por pasillo
  const doorCellsL = new Set(aisleZs(b).flatMap(z => [Math.floor(z), Math.floor(z) + 1]));
  const plaster = [], trim = [], glass = [], lamps = [];
  const wall = (x, z, along, isLeft) => {
    if (isLeft && doorCellsL.has(z)) { trim.push([x, 3.5, z]); return; }   // dintel sobre la puerta
    for (let y = 0; y < 4; y++) {
      const c = [x, y + 0.5, z];
      if (y === 0 || y === 3) trim.push(c);
      else if ((y === 1 || y === 2) && along % 4 === 2) glass.push(c);
      else plaster.push(c);
    }
    if (along % 4 === 0 && along > 0) lamps.push(isLeft ? [x + 0.58, 2.6, z, 0.16, 0.3, 0.3] : [x, 2.6, z + 0.58, 0.3, 0.3, 0.16]);
  };
  for (let x = b.minX - 1; x <= b.maxX; x++) wall(x, b.minZ - 1, x - (b.minX - 1), false);
  for (let z = b.minZ; z <= b.maxZ; z++) wall(b.minX - 1, z, z - (b.minZ - 1), true);
  world.add(instCubes(plaster, MAT.plaster), instCubes(trim, MAT.darkwood), instCubes(glass, MAT.glass, false), instCubes(lamps, MAT.lamp, false));
  const shelves = [];
  for (let x = b.maxX - 2; x <= b.maxX; x++) for (let y = 0; y < 2; y++) shelves.push([x, y + 0.5, b.minZ]);
  world.add(instCubes(shelves, MAT.shelf));
  const pots = [], leaves = [];
  for (const az of aisleZs(b)) { const z = az + 2; if (z <= b.maxZ - 0.5) { pots.push([b.minX, 0.25, z, 0.5, 0.5, 0.5]); leaves.push([b.minX, 0.9, z, 0.8, 0.8, 0.8], [b.minX, 1.45, z, 0.5, 0.4, 0.5]); } }
  if (pots.length) world.add(instCubes(pots, MAT.pot), instCubes(leaves, MAT.leaves));
  world.add(box(0.5, 0.9, 0.5, MAT.white, b.maxX, 0.45, b.minZ + 1), box(0.36, 0.45, 0.36, MAT.water, b.maxX, 1.13, b.minZ + 1));
  // salas
  for (const r of plan.rooms) {
    const mod = roomsLoaded.get(r.file);
    const meta = mod?.meta ? { ...mod.meta, size: [r.W, r.D] } : { id: r.file, title: r.file + ' (en obras)', size: [r.W, r.D], floor: 'planks' };
    const holder = new THREE.Group(); holder.position.set(r.ox, 0, r.oz);
    if (r.mirror) holder.scale.x = -1;
    // en el lado izquierdo la pared de la puerta (w) da a la oficina: baja para ver dentro; la exterior (e), alta
    holder.add(roomShell(meta, { walls: r.first ? ['n', 's', 'e', 'w'] : ['s', 'e', 'w'], ...(r.mirror ? { wH: 1, eH: 2 } : {}) }));
    r.spots = [];
    if (mod) {
      try {
        const g = mod.default(V, { variant: r.variant || 'A' });
        holder.add(g);
        if (g.userData.tick) roomTicks.push(g.userData.tick);
        r.spots = (g.userData.spots || []).map((s, i) => ({
          ...s, key: `${r.key}#${i}`, room: r,
          wx: r.mirror ? r.ox - s.x : r.ox + s.x, wz: r.oz + s.z, wrot: r.mirror ? -(s.rotY || 0) : (s.rotY || 0),
        }));
      } catch (e) { console.error('sala', r.file, e); }
    } else {
      const cone = V.col(0xff8a1f);
      for (let i = 0; i < 3; i++) holder.add(box(0.3, 0.5, 0.3, cone, 2 + i * 2, 0.25, r.D / 2));
    }
    // los textos no deben leerse al revés: se vuelven a dar la vuelta
    if (r.mirror) holder.traverse(o => { if (o.isMesh && o.material?.map?.userData?.aspect) o.scale.x *= -1; });
    world.add(holder);
  }
  scene.add(world);
  // sol y cámara
  const cx = (plan.minX + plan.maxX) / 2, cz = (plan.minZ + plan.maxZ) / 2;
  const size = Math.max(plan.maxX - plan.minX, plan.maxZ - plan.minZ) / 2 + 6;
  sun.position.set(cx - 18, 34, cz + 22); sun.target.position.set(cx, 0, cz);
  Object.assign(sun.shadow.camera, { left: -size, right: size, top: size, bottom: -size, near: 1, far: 120 });
  sun.shadow.camera.updateProjectionMatrix();
  if (firstFrame) {
    firstFrame = false;
    const shift = innerWidth > 760 ? size * 0.2 : 0;   // el panel tapa la derecha
    const ox = (b.minX + b.maxX) / 2;                   // centrar en la oficina
    controls.target.set(ox + shift, 0.5, cz);
    camera.position.set(ox + shift + size * 0.2, size * 1.0 + 4, cz + size * 1.3);
  }
}
function buildRugs(rugs) {
  const key = JSON.stringify(rugs); if (key === rugKey) return; rugKey = key;
  if (rugGroup) { scene.remove(rugGroup); rugGroup.traverse(o => { if (o.isMesh) { o.geometry.dispose(); o.material.map?.dispose(); o.material.dispose(); } }); }
  rugGroup = new THREE.Group();
  rugs.forEach((r, i) => {
    const w = r.x1 - r.x0, d = r.z1 - r.z0;
    const t = V.carpetTex(shade(r.color || FAM[r.fam].col, 0.75), 500 + i); t.repeat.set(w, d);
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, d), new THREE.MeshLambertMaterial({ map: t }));
    m.rotation.x = -Math.PI / 2; m.position.set((r.x0 + r.x1) / 2, 0.012, (r.z0 + r.z1) / 2); m.receiveShadow = true;
    rugGroup.add(m);
    const c = document.createElement('canvas'); c.width = 512; c.height = 64; const g = c.getContext('2d');
    g.font = '52px VT323, monospace'; g.fillStyle = 'rgba(0,0,0,0.45)'; g.fillText(fit(g, r.name, 500), 6, 52); g.fillStyle = '#fff'; g.fillText(fit(g, r.name, 500), 3, 49);
    const lt = new THREE.CanvasTexture(c); lt.colorSpace = THREE.SRGBColorSpace;
    const lw = Math.min(4, w - 0.3);
    const lm = new THREE.Mesh(new THREE.PlaneGeometry(4, 0.5), new THREE.MeshBasicMaterial({ map: lt, transparent: true, depthWrite: false }));
    lm.rotation.x = -Math.PI / 2; lm.scale.set(lw / 4, lw / 4, 1);
    lm.position.set(r.x0 + 0.15 + lw / 2, 0.02, r.z1 - 0.3); rugGroup.add(lm);
  });
  scene.add(rugGroup);
}

// ---------- caminos ----------
function roomPath(fromAisle, spot) {
  const r = spot.room, cx = r.side === 'L' ? plan.cL : plan.c1;
  return [[cx, fromAisle[1]], [cx, r.doorZ], [r.doorX, r.doorZ], [r.inX, r.doorZ], [spot.wx, spot.wz]];
}

// ---------- puesto de trabajo + agente ----------
const stations = new Map();
let selectedId = null;
const tmpV = new THREE.Vector3();

class Station {
  constructor(a, pos) {
    this.id = a.id; this.seed = hash(a.id);
    const r = rng(this.seed);
    this.group = new THREE.Group();
    const G = this.group;
    G.add(box(0.62, 0.1, 0.6, MAT.chair, 0, 0.45, 0), box(0.62, 0.62, 0.08, MAT.chair, 0, 0.82, -0.28), box(0.08, 0.4, 0.08, MAT.metal, 0, 0.2, 0), box(0.5, 0.06, 0.08, MAT.metal, 0, 0.03, 0));
    G.add(box(1.8, 0.1, 0.8, MAT.darkwood, 0, 0.85, 0.75));
    for (const sx of [-0.82, 0.82]) for (const sz of [0.42, 1.08]) G.add(box(0.08, 0.8, 0.08, MAT.darkwood, sx, 0.4, sz));
    G.add(box(0.12, 0.1, 0.12, MAT.dark, 0, 0.95, 0.98), box(0.82, 0.48, 0.07, MAT.dark, 0, 1.24, 0.98));
    this.screen = new THREE.Mesh(new THREE.PlaneGeometry(0.72, 0.4), new THREE.MeshBasicMaterial({ map: idleTex }));
    this.screen.position.set(0, 1.24, 0.94); this.screen.rotation.y = Math.PI;
    G.add(this.screen);
    G.add(box(0.62, 0.03, 0.2, MAT.dark, 0, 0.915, 0.5));
    G.add(box(0.11, 0.13, 0.11, V.col(pick(['#e94f4f', '#f5f5f5', '#4f8fe9', '#f0c419'], r)), 0.62, 0.965, 0.6));
    if (a.boss) {   // mesa del jefe: ribete dorado y placa
      const gold = V.col(0xf0c419);
      G.add(box(1.86, 0.04, 0.86, gold, 0, 0.79, 0.75));
      const plate = V.sign('JEFE', 0.2, { color: '#3a2a08', bg: '#f0c419', px: 40 });
      plate.position.set(0, 0.62, 1.17); G.add(plate);
    }
    this.lampMat = new THREE.MeshBasicMaterial({ color: 0xffb347 });
    G.add(box(0.16, 0.16, 0.16, this.lampMat, -0.68, 0.98, 0.9));
    this.ring = new THREE.Mesh(new THREE.RingGeometry(0.62, 0.78, 4, 1), new THREE.MeshBasicMaterial({ color: 0xffe14d }));
    this.ring.rotation.set(-Math.PI / 2, 0, Math.PI / 4); this.ring.position.y = 0.02; this.ring.visible = false;
    G.add(this.ring);
    this.parts = Array.from({ length: 8 }, () => { const m = box(0.07, 0.07, 0.07, new THREE.MeshBasicMaterial({ transparent: true }), 0, -10, 0); m.castShadow = false; m.life = 0; G.add(m); return m; });
    // personaje: vive en la silla (hijo del puesto) o en el mundo cuando pasea
    this.lookKey = JSON.stringify(a.look || {});
    this.ch = makeCharacter(this.seed, a.look || {});
    this.label = labelSprite(); this.label.sprite.position.set(0, 1.9, 0.15); this.ch.root.add(this.label.sprite);
    this.bubble = labelSprite(512, 192, 2.5, 0.94); this.bubble.sprite.renderOrder = 11; this.bubble.sprite.visible = false;
    this.bubble.sprite.position.set(0, 2.75, 0.15); this.ch.root.add(this.bubble.sprite); this.bubbleKey = '';
    this.zs = Array.from({ length: 3 }, (_, i) => { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: zTex, transparent: true, depthWrite: false })); s.scale.setScalar(0.22); s.phase = i / 3; this.ch.root.add(s); return s; });
    this.sitAtDesk();
    G.add(this.ch.root);
    this.selRing = new THREE.Mesh(new THREE.RingGeometry(0.42, 0.55, 4, 1), new THREE.MeshBasicMaterial({ color: 0xffe14d }));
    this.selRing.rotation.set(-Math.PI / 2, 0, Math.PI / 4); this.selRing.visible = false; scene.add(this.selRing);

    this.mode = 'desk';   // desk | walking | away
    this.path = []; this.spot = null; this.idleFor = 0; this.returning = false;
    this.spawnT = 0; this.appear = 0; this.leaving = false; this.phase = r() * 10;
    this.target = new THREE.Vector3(); this.placed = false;
    G.scale.setScalar(0.001);
    for (const o of [G, this.ch.root]) o.traverse(m => { if (m.isMesh) m.userData.stationId = a.id; });
    scene.add(G);
    this.fam = null; this.shirtKey = ''; this.labelKey = ''; this.dressing = false; this.fresh = true;
    if (pos) this.setTarget(pos[0], pos[1]);
    this.update(a);
    this.fresh = false;
  }
  sitAtDesk() {
    const { root } = this.ch;
    root.position.set(0, 0.5 + SEAT_HIP, 0); root.rotation.set(0, 0, 0);
    setPose(this.ch, 'sit'); this.pose = 'sit'; this.activity = 'desk';
    this.ch.cup.visible = this.ch.book.visible = false;
  }
  get where() {
    if (this.mode === 'desk') return null;
    if (this.agent?.status === 'offline' && this.mode === 'away') return 'descansando (sin ventana abierta)';
    return this.spot ? WHERE[this.spot.room.file] : 'paseando';
  }
  update(a) {
    const prevStatus = this.agent?.status;
    this.agent = a;
    const lk = JSON.stringify(a.look || {});
    if (lk !== this.lookKey) { this.lookKey = lk; this.rebuildCharacter(a.look || {}); }
    this.fam = family(a);
    const shirt = a.look?.shirt || FAM[this.fam].col;
    if (shirt !== this.shirtKey) {
      this.shirtKey = shirt;
      if (this.ch.shirtM.map) this.ch.shirtM.map.dispose();
      this.ch.shirtM.map = shirtTex(shirt, this.seed + 7); this.ch.shirtM.needsUpdate = true;
    }
    const busy = a.status === 'busy';
    this.screen.material.map = busy ? busyTex : idleTex;
    this.lampMat.color.set(busy ? 0x4cff7a : a.status === 'offline' ? 0x444a58 : 0xffb347);
    this.applyDesire(prevStatus);
    this.refreshLabel();
    const att = liveAttention(a), bk = att ? `${att.kind}|${att.t}|${att.msg}` : '';
    if (bk !== this.bubbleKey) { this.bubbleKey = bk; if (att) { drawBubble(this.bubble, att); this.bubbleT0 = performance.now() / 1000; } }
    this.bubble.sprite.visible = !!att;
    this.ring.visible = selectedId === a.id && this.mode === 'desk';
  }
  // dónde debería estar según su estado
  desire() {
    if (this.dressing) return 'dress';
    if (this.agent.status === 'busy') return 'desk';
    if (this.agent.status === 'offline') return 'rest';
    return 'free';
  }
  applyDesire(prevStatus) {
    if (!plan) return;
    const want = this.desire();
    const at = this.spot?.room.file;
    if (want === 'desk') { if (this.mode !== 'desk' && !this.returning) this.sendHome(false); return; }
    if (want === 'dress') { if (at !== 'vestuario') this.goTo(chooseSpot(this, 'dress')); return; }
    if (want === 'rest') {
      if (this.spot && (this.spot.activity === 'rest' || at === 'descanso')) return;
      const spot = chooseSpot(this, 'rest');
      if (this.mode === 'desk' && (this.fresh || this.justReset)) this.placeAt(spot);
      else this.goTo(spot);
      this.justReset = false;
      return;
    }
    // libre: si acaba de abrir su ventana (venía de descansar o del vestuario), vuelve a la mesa
    if ((prevStatus === 'offline' || at === 'vestuario') && this.mode !== 'desk' && !this.returning) this.sendHome(false);
  }
  rebuildCharacter(look) {
    const old = this.ch, parent = old.root.parent;
    const nu = makeCharacter(this.seed, look);
    nu.root.position.copy(old.root.position); nu.root.rotation.copy(old.root.rotation); nu.root.scale.copy(old.root.scale);
    nu.root.add(this.label.sprite, this.bubble.sprite); for (const z of this.zs) nu.root.add(z);
    nu.shirtM.map = shirtTex(look.shirt || FAM[this.fam || 'other'].col, this.seed + 7);
    this.shirtKey = look.shirt || FAM[this.fam || 'other'].col;
    if (parent) { parent.add(nu.root); parent.remove(old.root); }
    disposeTree(old.root); old.own.forEach(t => t.dispose()); old.shirtM.map?.dispose();
    this.ch = nu;
    setPose(nu, this.pose || 'sit');
    nu.cup.visible = this.activity === 'coffee' || this.activity === 'eat';
    nu.book.visible = this.activity === 'read';
    nu.root.traverse(m => { if (m.isMesh) m.userData.stationId = this.id; });
  }
  refreshLabel() {
    const a = this.agent; const where = this.mode === 'walking' ? (this.returning ? 'volviendo a su mesa' : 'de camino') : this.where;
    const key = [a.name, a.status, a.tool, a.detail, this.fam, selectedId === a.id, where].join('|');
    if (key !== this.labelKey) { this.labelKey = key; drawLabel(this.label, a, a.look?.cape || a.look?.shirt || FAM[this.fam].col, selectedId === a.id, where); }
  }
  setTarget(x, z) { this.target.set(x, 0, z); if (!this.placed) { this.group.position.copy(this.target); this.placed = true; } }
  worldPos(out) { return this.ch.root.getWorldPosition(out); }

  // levantarse e ir a un sitio libre
  goOut(pref) { if (plan) this.goTo(chooseSpot(this, pref)); }
  // ir andando a un sitio, desde la mesa o desde otra sala
  goTo(spot) {
    if (!spot || spot === this.spot) return;
    if (this.mode === 'walking') { this.after = spot; return; }   // se encadena al llegar
    const seat = this.group.position;
    const aisle = [seat.x, seat.z - 1.6];
    const { root } = this.ch;
    let pts;
    if (this.mode === 'desk') {
      scene.attach(root);
      root.position.set(seat.x, STAND_HIP, seat.z); root.rotation.set(0, 0, 0);
      pts = [[seat.x, seat.z - 0.9], aisle, ...roomPath(aisle, spot)];
    } else {
      occupied.delete(this.spot.key);
      root.position.y = STAND_HIP + (this.spot.y || 0);
      pts = [...roomPath(aisle, this.spot).reverse().slice(1, -1), ...roomPath(aisle, spot)];
    }
    occupied.set(spot.key, this.id); this.spot = spot;
    setPose(this.ch, 'stand'); this.pose = 'stand';
    this.ch.cup.visible = this.ch.book.visible = false;
    this.path = pts; this.walked = [];
    this.mode = 'walking'; this.returning = false; this.activity = 'walk';
    this.refreshLabel();
  }
  // aparecer directamente en un sitio (al cargar la página)
  placeAt(spot) {
    if (!spot) return;
    if (this.mode === 'away' && this.spot) occupied.delete(this.spot.key);
    occupied.set(spot.key, this.id); this.spot = spot;
    scene.attach(this.ch.root); this.returning = false; this.path = [];
    this.arrive();
  }
  // volver a la mesa (instant: sin animación, p. ej. al rehacer el plano)
  sendHome(instant) {
    if (this.mode === 'desk') return;
    if (this.spot) { occupied.delete(this.spot.key); }
    const { root } = this.ch;
    if (instant || !plan) { this.group.attach(root); this.sitAtDesk(); this.mode = 'desk'; this.spot = null; this.path = []; this.returning = false; this.after = null; this.justReset = true; return; }
    this.after = null;
    const seat = this.group.position;
    const aisle = [seat.x, seat.z - 1.6];
    const pts = this.spot ? roomPath(aisle, this.spot).reverse() : [];
    if (this.mode === 'walking' && !this.returning) {
      // a medio camino: deshacer lo andado
      pts.length = 0; pts.push(...this.walked.slice().reverse());
    }
    pts.push(aisle, [seat.x, seat.z - 0.9], [seat.x, seat.z]);
    if (this.pose === 'sit') { root.position.y = STAND_HIP + (this.spot?.y || 0); setPose(this.ch, 'stand'); this.pose = 'stand'; }
    this.ch.cup.visible = this.ch.book.visible = false;
    this.spot = null; this.path = pts; this.mode = 'walking'; this.returning = true; this.activity = 'walk';
    this.refreshLabel();
  }
  arrive() {
    const { root } = this.ch;
    if (this.returning) {
      this.group.attach(root); this.sitAtDesk(); this.mode = 'desk'; this.returning = false; this.idleFor = 0; this.refreshLabel();
      if (this.after) { const n = this.after; this.after = null; this.goTo(n); } else this.applyDesire();
      return;
    }
    const s = this.spot;
    root.position.set(s.wx, (s.y || 0) + (s.pose === 'sit' ? SEAT_HIP : STAND_HIP), s.wz);
    root.rotation.set(0, s.wrot, 0);
    setPose(this.ch, s.pose); this.pose = s.pose; this.activity = s.activity || 'chat';
    this.ch.cup.visible = this.activity === 'coffee' || this.activity === 'eat';
    this.ch.book.visible = this.activity === 'read';
    this.mode = 'away'; this.refreshLabel();
    if (this.after) { const n = this.after; this.after = null; if (n !== this.spot) { this.goTo(n); return; } }
    this.applyDesire();
  }

  tick(dt, t) {
    const G = this.group;
    this.appear = this.leaving ? Math.max(0, this.appear - dt * 2.5) : Math.min(1, this.appear + dt * 2);
    const e = this.appear; const s = e < 1 ? 1 - Math.pow(1 - e, 3) * (1 - 1.7 * e * (1 - e)) : 1;
    G.scale.setScalar(Math.max(0.001, s));
    if (this.mode !== 'desk') this.ch.root.scale.setScalar(Math.max(0.001, s));
    G.position.lerp(this.target, Math.min(1, dt * 4));
    const busy = this.agent.status === 'busy';
    // decidir si salir
    // con reloj real (no dt), para que no dependa de los fps
    const now = performance.now() / 1000;
    if (this.mode === 'desk' && this.desire() === 'free' && !this.leaving) {
      this.idleSince ||= now;
      if (now - this.idleSince > IDLE_LEAVE + (this.seed % 5)) { this.idleSince = 0; this.goOut(); }
    } else this.idleSince = 0;
    this.idleFor = this.idleSince ? now - this.idleSince : 0;
    if (this.mode === 'walking') this.walk(dt, t);
    this.animate(dt, t, busy);
    this.effects(dt, t, busy);
    if (this.ch.cape) {
      const walking = this.mode === 'walking';
      const base = this.pose === 'sit' ? 0.9 : walking ? 0.42 : 0.1;
      const want = base + Math.sin(t * (walking ? 7 : 1.6) + this.phase) * (walking ? 0.12 : 0.04);
      this.ch.cape.rotation.x += (want - this.ch.cape.rotation.x) * Math.min(1, dt * 6);
    }
    if (this.bubble.sprite.visible) {   // salta al aparecer y luego flota y late
      const age = now - (this.bubbleT0 || now), pop = Math.min(1, age * 4);
      const bounce = age < 1.2 ? Math.abs(Math.sin(age * 9)) * (1.2 - age) * 0.35 : 0;
      const pulse = 1 + Math.max(0, Math.sin(t * 5)) * 0.06;
      this.bubble.sprite.position.y = 2.75 + bounce + Math.sin(t * 2.4 + this.phase) * 0.06;
      this.bubble.sprite.scale.set(2.5 * pop * pulse, 0.94 * pop * pulse, 1);
    }
    // anillo de selección bajo el personaje cuando pasea
    const sel = selectedId === this.id;
    this.ring.visible = sel && this.mode === 'desk';
    this.selRing.visible = sel && this.mode !== 'desk';
    if (this.selRing.visible) { this.worldPos(tmpV); this.selRing.position.set(tmpV.x, 0.03, tmpV.z); }
    return !(this.leaving && this.appear <= 0);
  }
  walk(dt, t) {
    const { root } = this.ch;
    if (!this.walked) this.walked = [];
    let step = WALK_SPEED * dt;
    while (step > 0 && this.path.length) {
      const [tx, tz] = this.path[0];
      const dx = tx - root.position.x, dz = tz - root.position.z, d = Math.hypot(dx, dz);
      if (d < 1e-3) { this.walked.push(this.path.shift()); continue; }
      const mv = Math.min(step, d);
      root.position.x += dx / d * mv; root.position.z += dz / d * mv; step -= mv;
      const want = Math.atan2(dx, dz);
      let diff = want - root.rotation.y; diff = Math.atan2(Math.sin(diff), Math.cos(diff));
      root.rotation.y += diff * Math.min(1, dt * 12);
      if (mv >= d) this.walked.push(this.path.shift());
    }
    root.position.y = STAND_HIP + Math.abs(Math.sin(t * 10)) * 0.04;
    if (!this.path.length) { this.walked = []; this.arrive(); }
  }
  animate(dt, t, busy) {
    const { arms, head, body, torso, legs } = this.ch;
    const tt = t + this.phase, L = THREE.MathUtils.lerp, k = Math.min(1, dt * 4);
    let a0 = -0.1, a1 = -0.1, hx = 0, hy = Math.sin(tt * 0.4) * 0.25, lean = 0;
    switch (this.mode === 'walking' ? 'walk' : this.activity) {
      case 'desk':
        if (busy) { a0 = -1.0 + Math.sin(tt * 17) * 0.13; a1 = -1.0 + Math.sin(tt * 17 + 2) * 0.13; hx = Math.sin(tt * 3) * 0.05 + 0.08; hy = Math.sin(tt * 0.7) * 0.15; lean = 0.06; }
        else { a0 = a1 = -0.15; hx = -0.25; lean = -0.14; }
        break;
      case 'walk': {
        const sw = Math.sin(tt * 10) * 0.6;
        a0 = sw; a1 = -sw; hx = 0; hy = 0;
        legs[0].hip.rotation.x = -sw; legs[1].hip.rotation.x = sw;
        break;
      }
      case 'coffee': case 'eat': {
        const sip = Math.max(0, Math.sin(tt * 0.9)) ** 4;
        a1 = -0.5 - sip * 1.9; a0 = -0.2; hx = -sip * 0.25;
        break;
      }
      case 'play': a0 = -1.2 + Math.sin(tt * 14) * 0.15; a1 = -1.2 + Math.sin(tt * 11 + 1) * 0.2; hx = 0.05; hy = Math.sin(tt * 2) * 0.08; break;
      case 'pool': a0 = -0.9; a1 = -1.1 + Math.max(0, Math.sin(tt * 1.3)) * 0.4; lean = 0.35; hx = 0.1; hy = 0; break;
      case 'rest': a0 = a1 = -0.05; hx = 0.35; hy = 0.3; lean = -0.1; break;
      case 'dress': a0 = -0.2; a1 = -0.6 + Math.sin(tt * 1.5) * 0.4; hy = Math.sin(tt * 0.8) * 0.5; hx = -0.05; break;
      case 'read': a0 = a1 = -0.9; hx = 0.35; hy = 0; break;
      case 'meeting': case 'chat': default: {
        const talk = Math.sin(tt * 0.5) > 0;
        a0 = -0.15; a1 = talk ? -0.6 + Math.sin(tt * 4) * 0.35 : -0.15; hx = Math.sin(tt * (talk ? 5 : 1)) * 0.07; hy = Math.sin(tt * 0.6) * 0.3;
      }
    }
    if (this.mode !== 'walking' && this.pose === 'stand') { for (const l of legs) l.hip.rotation.x = L(l.hip.rotation.x, 0, k); }
    arms[0].rotation.x = this.mode === 'walking' ? a0 : L(arms[0].rotation.x, a0, k * 2);
    arms[1].rotation.x = this.mode === 'walking' ? a1 : L(arms[1].rotation.x, a1, k * 2);
    head.rotation.x = L(head.rotation.x, hx, k); head.rotation.y = L(head.rotation.y, hy, k);
    body.rotation.x = L(body.rotation.x, lean, k);
    torso.scale.y = 1 + Math.sin(tt * 2) * 0.015;
  }
  effects(dt, t, busy) {
    this.spawnT -= dt;
    if (busy && this.mode === 'desk' && this.spawnT <= 0) {
      this.spawnT = 0.22;
      const p = this.parts.find(p => p.life <= 0);
      if (p) { p.life = 1; p.position.set((Math.random() - 0.5) * 0.6, 1.5, 0.98); p.material.color.set(pick(['#7ee787', '#79c0ff', '#ffa657', '#d2a8ff'], Math.random)); }
    }
    for (const p of this.parts) {
      if (p.life <= 0) { p.visible = false; continue; }
      p.visible = true; p.life -= dt * 0.8; p.position.y += dt * 0.55; p.material.opacity = Math.max(0, p.life);
    }
    const sleepy = !busy && (this.mode === 'desk' || this.activity === 'rest');
    for (const z of this.zs) {
      z.visible = sleepy;
      if (!sleepy) continue;
      const k = (t * 0.35 + z.phase) % 1;
      z.position.set(0.25 + k * 0.4, 1.25 + k * 0.7, 0.05);
      z.material.opacity = Math.sin(k * Math.PI); z.scale.setScalar(0.14 + k * 0.16);
    }
  }
  dispose() {
    if (this.spot) occupied.delete(this.spot.key);
    scene.remove(this.group); scene.remove(this.ch.root); scene.remove(this.selRing);
    disposeTree(this.group); disposeTree(this.ch.root); disposeTree(this.selRing);
    for (const t of this.ch.own) t.dispose();
    this.label.tex.dispose(); this.bubble.tex.dispose(); if (this.ch.shirtM.map) this.ch.shirtM.map.dispose();
  }
}

function chooseSpot(st, pref) {
  const free = r => (r.spots || []).filter(s => !occupied.has(s.key) || occupied.get(s.key) === st.id);
  const all = plan.rooms.flatMap(free);
  if (pref === 'dress') {
    const v = all.filter(s => s.room.file === 'vestuario');
    return pick(v.filter(s => s.activity === 'dress').length ? v.filter(s => s.activity === 'dress') : v.length ? v : all, Math.random) || null;
  }
  if (pref === 'rest') {
    const rest = all.filter(s => s.activity === 'rest');
    const desc = all.filter(s => s.room.file === 'descanso');
    const any = all.filter(s => s.room.weight !== 0);
    const list = rest.length ? rest : desc.length ? desc : any;
    return list.length ? pick(list, Math.random) : null;
  }
  const rooms = plan.rooms.filter(r => r.weight !== 0 && free(r).length);
  if (!rooms.length) return null;
  const group = st.agent.parent || st.agent.team || st.id;
  // si un compañero de su grupo o equipo está en una reunión con sitio, suele unirse
  for (const other of stations.values()) {
    if (other === st || !other.spot || other.spot.room.file !== 'reuniones') continue;
    if ((other.agent.parent || other.agent.team || other.id) !== group && other.agent.parent !== st.id && st.agent.parent !== other.id) continue;
    const f = free(other.spot.room);
    if (f.length && Math.random() < 0.7) return pick(f, Math.random);
  }
  const total = rooms.reduce((n, r) => n + (r.weight || 1), 0);
  let x = Math.random() * total, room = rooms[0];
  for (const r of rooms) { x -= r.weight || 1; if (x <= 0) { room = r; break; } }
  return pick(free(room), Math.random);
}

// ---------- panel ----------
const $ = id => document.getElementById(id);
const listEl = $('list'), sumEl = $('summary'), teamsEl = $('teams'), connEl = $('conn'), panelEl = $('panel');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
let lastData = { agents: [], teams: [] };
let rosterCache = null, modelsCache = null;

function toast(msg, ms = 3500) {
  const t = $('toast'); t.textContent = msg; t.style.display = 'block';
  clearTimeout(toast.h); toast.h = setTimeout(() => { t.style.display = 'none'; }, ms);
}
const agentById = id => lastData.agents.find(a => a.id === id);

function itemHtml(a) {
  const f = FAM[family(a)];
  const kind = a.secretary ? `secretaria · voz ${a.voice ? 'activada' : 'silenciada'}` : a.boss ? `jefe · ${a.sessionName ? 'sesión ' + a.sessionName : 'sin ventana'}` : { session: 'sesión', subagent: 'subagente', opencode: 'opencode', member: (a.role === 'pm' ? 'PM · ' : '') + ({ opencode: 'OpenCode', kimi: 'Kimi' }[a.engine] || 'Claude') + (a.original ? ' (cambiado por el PM)' : '') }[a.kind] || a.kind;
  const model = (a.model || '').replace(/^claude-/, '') || '¿modelo?';
  const tok = a.tokens ? ` · ${Math.round(a.tokens / 1000)}k ctx` : '';
  const where = stations.get(a.id)?.where;
  const act = a.status === 'busy' ? statusLine(a) : (where || (a.kind === 'member' ? a.title : a.title) || '');
  const sub = a.kind === 'subagent' || (a.kind === 'opencode' && a.parent);
  const st = a.status === 'busy' ? 'busy' : a.status === 'offline' ? 'offline' : 'idle';
  return `<div class="item ${sub ? 'sub' : ''} ${a.id === selectedId ? 'sel' : ''}" data-id="${esc(a.id)}">
    <div class="dot" style="background:${esc(a.look?.cape || a.look?.shirt || f.col)}"></div>
    <div class="name">${esc(a.name)}${a.job ? ` <span class="job">${esc(a.job)}</span>` : ''}${a.window ? ' <span title="ventana abierta">▣</span>' : ''}${liveAttention(a) ? ` <span class="att ${liveAttention(a).kind}" title="${esc(ATT[liveAttention(a).kind].title)}">${{ listo: '✔ listo', permiso: '! permiso', pregunta: '? pregunta', cambio: '⇄ cambio', rescate: '↺ reinicio', atasco: '… atascado', voz: '♪ hablando', peticion: '✉ pidió', buzon: '✉ buzón' }[liveAttention(a).kind]}</span>` : ''}</div>
    <div class="st ${st}">■ ${STATUS_TXT[st]}</div>
    <div class="meta">${esc(kind)} · ${esc(model)}${tok}</div>
    <div class="meta">${esc(act)}</div></div>`;
}

function renderPanel(data = lastData) {
  const ag = data.agents;
  const busy = ag.filter(a => a.status === 'busy').length;
  const members = ag.filter(a => a.kind === 'member').length;
  sumEl.style.color = '';
  const staff = ag.filter(a => a.boss || a.secretary).length;
  sumEl.textContent = `${members} en plantilla · ${ag.length - members - staff} de visita · ${busy} trabajando`;
  let html = '';
  const boss = ag.find(a => a.boss);
  if (boss) {
    html += '<div class="team"><span class="tdot" style="background:#d97757"></span><span class="grow">Dirección</span></div>' + itemHtml(boss);
    for (const s of ag.filter(a => a.secretary)) html += itemHtml(s);
    for (const s of ag.filter(a => a.parent === boss.id)) html += itemHtml(s);
  }
  for (const t of data.teams || []) {
    html += `<div class="team"><span class="tdot" style="background:${esc(t.color)}"></span><span class="grow">${esc(t.name)}</span><button class="mini" data-hire="${esc(t.id)}">+ contratar</button></div>`;
    for (const m of ag.filter(a => a.kind === 'member' && a.team === t.id)) {
      html += itemHtml(m);
      for (const s of ag.filter(a => a.parent === m.id)) html += itemHtml(s);
    }
  }
  const memberIds = new Set(ag.filter(a => a.kind === 'member').map(a => a.id));
  const others = ag.filter(a => a.kind !== 'member' && !a.boss && !a.secretary && !memberIds.has(a.parent) && a.parent !== boss?.id);
  if (others.length) {
    html += '<div class="team"><span class="grow">Visitantes</span></div>';
    const order = [];
    for (const s of others.filter(a => a.kind === 'session')) { order.push(s); order.push(...others.filter(a => a.parent === s.id)); }
    for (const a of others) if (!order.includes(a)) order.push(a);
    html += order.map(itemHtml).join('');
  }
  if (!html) html = '<div class="empty">La oficina está vacía.<br>Contrata a alguien con el botón de arriba.</div>';
  listEl.innerHTML = html;
  teamsEl.innerHTML = (data.claudeTeams || []).map(t => `<p><b>Agent team ${esc(t.name)}</b>: ${t.members.map(m => esc(m.name)).join(', ') || '—'}</p>`).join('');
  if (chatId) updateChatHeader();
}
listEl.addEventListener('click', e => {
  const hire = e.target.closest('[data-hire]');
  if (hire) return openDress(null, hire.dataset.hire);
  const it = e.target.closest('.item'); if (!it) return;
  const a = agentById(it.dataset.id);
  if (a?.memberId) openChat(a.id); else select(it.dataset.id);
});
$('btnHire').onclick = () => openDress(null);
$('btnTeam').onclick = async () => {
  const name = prompt('Nombre del nuevo equipo'); if (!name) return;
  if (DEMO) return toast('Modo demo: no se guarda nada');
  const color = pick(['#e0a030', '#3db0a0', '#d0508a', '#6a8cff', '#8ac040', '#c0603a'], Math.random);
  try { await api('/api/team', { name, color }); toast(`Equipo «${name}» creado`); poll(); } catch (e) { toast(e.message); }
};

function select(id) {
  selectedId = selectedId === id ? null : id;
  if (selectedId) ackAttention(agentById(id));
  for (const s of stations.values()) s.update(s.agent);
  document.querySelectorAll('.item').forEach(el => el.classList.toggle('sel', el.dataset.id === selectedId));
}
const ray = new THREE.Raycaster(), mouse = new THREE.Vector2(); let downAt = null;
renderer.domElement.addEventListener('pointerdown', e => { downAt = [e.clientX, e.clientY]; });
renderer.domElement.addEventListener('pointerup', e => {
  if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 5) return;
  mouse.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  ray.setFromCamera(mouse, camera);
  const objs = []; for (const s of stations.values()) objs.push(s.group, s.ch.root);
  const hit = ray.intersectObjects(objs, true).find(h => h.object.userData.stationId);
  if (hit) {
    const a = agentById(hit.object.userData.stationId);
    if (a?.memberId) openChat(a.id); else select(a.id);
  } else if (selectedId && !chatId) select(selectedId);
});

// ---------- chat ----------
let chatId = null, chatTimer = null, chatSig = '';
function openChat(id) {
  const a = agentById(id); if (!a) return;
  chatId = id; if (selectedId !== id) select(id); else ackAttention(a);
  panelEl.classList.add('chatting');
  const log = $('chatLog'); log.innerHTML = ''; delete log.dataset.init; chatSig = '';
  $('chatTyping').textContent = '';
  $('chatInput').placeholder = a.kind === 'member' ? `Dale una orden a ${a.name}…` : `Escríbele a ${a.name}…`;
  updateChatHeader(); loadChat();
  loadUsage().then(updateChatHeader).catch(() => {});
  clearInterval(chatTimer); chatTimer = setInterval(loadChat, 1500);
  setTimeout(() => $('chatInput').focus(), 50);
}
function closeChat() {
  chatId = null; clearInterval(chatTimer);
  panelEl.classList.remove('chatting');
  if (selectedId) select(selectedId);
  renderPanel();
}
$('chatBack').onclick = closeChat;
$('btnRestore').onclick = async () => {
  const a = agentById(chatId); if (!a?.original) return;
  if (DEMO) return toast('Modo demo: no se guarda');
  try { await api('/api/restore', { id: a.memberId }); toast(`${a.name} vuelve a ${a.original}`); poll(); } catch (e) { toast(e.message); }
};
function updateChatHeader() {
  const a = agentById(chatId); if (!a) return closeChat();
  $('chatName').textContent = a.name; $('chatName').style.color = a.look?.shirt || FAM[family(a)].col;
  const team = (lastData.teams || []).find(t => t.id === a.team);
  const where = stations.get(a.id)?.where;
  $('chatSub').textContent = `${team ? team.name + ' · ' : ''}${(a.model || '').replace(/^claude-/, '')} · ${STATUS_TXT[a.status] || a.status}${a.window ? ' · ventana abierta' : ''}${where && a.status !== 'busy' ? ' · ' + where : ''}`;
  $('btnStop').disabled = a.status !== 'busy';
  const rb = $('btnRestore');
  rb.hidden = !a.original; if (a.original) rb.textContent = `Volver a ${a.original.split('/').pop().replace(/^claude-/, '')}`;
  const c = a.memberId && memberCost(a.memberId);
  if (c) $('chatSub').textContent += ` · ≈ ${money(c.total)} gastado`;
}
async function loadChat() {
  const a = agentById(chatId); if (!a) return;
  const log = $('chatLog');
  if (DEMO) { if (!log.childElementCount) log.innerHTML = '<div class="msg note">En el modo demo el chat no está conectado.</div>'; return; }
  try {
    const d = await api('/api/chat?id=' + encodeURIComponent(a.memberId));
    if (chatId !== a.id) return;
    const r = d.run;
    $('chatTyping').textContent = r?.running ? `${a.name} está trabajando${r.tool ? ` · ${r.tool}${r.detail ? ': ' + r.detail : ''}` : '…'}` : '';
    const sig = d.messages.length + '|' + JSON.stringify(d.messages.slice(-2)) + '|' + !!r?.running;
    if (sig === chatSig) return; chatSig = sig;
    const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 60;
    log.innerHTML = d.messages.length
      ? d.messages.map(m => `<div class="msg ${esc(m.role)}">${m.role === 'tool' ? '⚙ ' : ''}${esc(m.text)}</div>`).join('')
      : `<div class="msg note">Todavía no habéis hablado. Escríbele una orden abajo.<br>Trabaja en ${esc(a.cwd)}.</div>`;
    if (atBottom || !log.dataset.init) { log.scrollTop = log.scrollHeight; log.dataset.init = '1'; }
  } catch (e) { $('chatTyping').textContent = 'Error: ' + e.message; }
}
$('chatForm').onsubmit = async e => {
  e.preventDefault();
  const a = agentById(chatId); const text = $('chatInput').value.trim();
  if (!text || !a) return;
  if (DEMO) return toast('Modo demo: no se envían órdenes');
  $('chatSend').disabled = true;
  try {
    await api('/api/order', { id: a.memberId, text });
    $('chatInput').value = ''; chatSig = '';
    $('chatLog').insertAdjacentHTML('beforeend', `<div class="msg user">${esc(text)}</div>`);
    $('chatLog').scrollTop = 1e9;
    $('chatTyping').textContent = `${a.name} se pone con ello…`;
    setTimeout(poll, 400);
  } catch (err) { toast(err.message, 5000); }
  finally { $('chatSend').disabled = false; }
};
$('chatInput').onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('chatForm').requestSubmit(); } };
$('btnStop').onclick = async () => { try { await api('/api/stop', { id: agentById(chatId).memberId }); toast('Detenido'); } catch (e) { toast(e.message); } };
$('btnWindow').onclick = async () => {
  if (DEMO) return toast('Modo demo: no se abren ventanas');
  try { await api('/api/open', { id: agentById(chatId).memberId }); toast('Abriendo su ventana…'); } catch (e) { toast(e.message, 5000); }
};
$('btnDress').onclick = () => openDress(agentById(chatId)?.memberId);

// ---------- vestuario (editor) ----------
const LOOK_OPTS = {
  skin: SKIN, hair: HAIR, pants: PANTS,
  shirt: ['#9b6cff', '#f08a3c', '#45c47a', '#2bb5c4', '#3d7bf0', '#e94f4f', '#f0c419', '#e0e0e0', '#2d2d33', '#d0508a'],
};
let dressMember = null, dressLook = {}, dressStation = null, dressOrigLook = null;
async function ensureModels() {
  if (!modelsCache) modelsCache = DEMO
    ? { claude: [{ id: 'claude-sonnet-5-5', name: 'Sonnet 5.5' }, { id: 'claude-haiku-5-5', name: 'Haiku 5.5' }], opencode: [{ id: 'opencode/big-pickle', name: 'opencode/big-pickle' }], permissions: [{ id: 'default', name: 'Solo leer' }] }
    : await api('/api/models');
  return modelsCache;
}
function fillModels(engine, current, keepFilter = false) {
  const f = $('fModelFilter');
  if (!keepFilter) f.value = '';
  f.hidden = engine !== 'opencode';
  const words = f.value.toLowerCase().split(/\s+/).filter(Boolean);
  const all = (engine === 'claude' ? modelsCache.claude : engine === 'kimi' ? modelsCache.kimi : modelsCache.opencode) || [];
  const list = all.filter(m => words.every(w => m.id.toLowerCase().includes(w)));
  $('fModelCount').textContent = engine !== 'opencode' ? '' : words.length ? `${list.length} de ${all.length}` : `${all.length} modelos`;
  const sel = $('fModel');
  const opt = m => `<option value="${esc(m.id)}">${esc(engine !== 'opencode' ? m.name : m.id.slice(m.id.indexOf('/') + 1))}</option>`;
  if (engine !== 'opencode') sel.innerHTML = list.map(opt).join('');
  else {   // OpenCode: agrupados por proveedor
    const NAMES = { opencode: 'OpenCode (gratis)', openai: 'OpenAI · ChatGPT', 'github-copilot': 'GitHub Copilot', openrouter: 'OpenRouter', nvidia: 'NVIDIA' };
    const groups = new Map();
    for (const m of list) { const p = m.id.split('/')[0]; if (!groups.has(p)) groups.set(p, []); groups.get(p).push(m); }
    sel.innerHTML = [...groups].map(([p, ms]) => `<optgroup label="${esc(NAMES[p] || p)} (${ms.length})">${ms.map(opt).join('')}</optgroup>`).join('');
  }
  if (current && !list.some(m => m.id === current)) sel.insertAdjacentHTML('afterbegin', `<option value="${esc(current)}">${esc(current)} (actual)</option>`);
  sel.value = current || list[0]?.id || '';
}
$('fModelFilter').addEventListener('input', () => {
  const engine = document.querySelector('input[name=fEngine]:checked')?.value || 'opencode';
  fillModels(engine, $('fModel').value, true);
});
$('fModelFilter').addEventListener('keydown', e => { if (e.key === 'Enter') e.preventDefault(); });
function permHint() {
  const v = $('fPerm').value;
  $('permHint').innerHTML = v === 'bypassPermissions'
    ? '<span class="warn">Podrá ejecutar comandos y borrar archivos sin preguntarte. Úsalo solo en carpetas de prueba.</span>'
    : v === 'acceptEdits' ? 'Edita archivos de su carpeta. Cuando trabaja desde el chat, los comandos de terminal los tiene bloqueados.'
    : 'Puede leer y responder, pero no cambiar nada.';
}
function renderSwatches() {
  document.querySelectorAll('[data-look]').forEach(el => {
    const k = el.dataset.look;
    el.innerHTML = LOOK_OPTS[k].map(c => `<button type="button" class="sw ${dressLook[k] === c ? 'on' : ''}" style="background:${c}" data-c="${c}" title="${c}"></button>`).join('');
  });
}
document.querySelectorAll('[data-look]').forEach(el => el.addEventListener('click', e => {
  const c = e.target.dataset?.c; if (!c) return;
  dressLook[el.dataset.look] = c; renderSwatches(); previewLook();
}));
$('fAcc').onchange = () => { dressLook.accessory = $('fAcc').value; previewLook(); };
function previewLook() { if (dressStation) dressStation.rebuildCharacter({ ...dressLook }); }
function skillsVisible(engine) {
  $('fSkillsRow').hidden = $('fSkills').hidden = $('fSkillsHint').hidden = engine !== 'claude';
}
// modelos de reserva del PM
let dressFb = [];
function renderFb() {
  const ol = $('fFbList');
  ol.innerHTML = dressFb.length
    ? dressFb.map((f, i) => `<li><span title="${esc(f)}">${esc(f)}</span>`
      + `<button type="button" class="mini" data-fb="up" data-i="${i}" title="Subir"${i ? '' : ' disabled'}>↑</button>`
      + `<button type="button" class="mini" data-fb="down" data-i="${i}" title="Bajar"${i < dressFb.length - 1 ? '' : ' disabled'}>↓</button>`
      + `<button type="button" class="mini" data-fb="del" data-i="${i}" title="Quitar">✕</button></li>`).join('')
    : '<li class="mut">Vacía: usará la lista de serie</li>';
  $('fPm').classList.toggle('off', !$('fAutoSwap').checked);
}
$('fFbList').addEventListener('click', e => {
  const b = e.target.closest('button[data-fb]'); if (!b) return;
  const i = +b.dataset.i, j = b.dataset.fb === 'up' ? i - 1 : i + 1;
  if (b.dataset.fb === 'del') dressFb.splice(i, 1);
  else if (j >= 0 && j < dressFb.length) [dressFb[i], dressFb[j]] = [dressFb[j], dressFb[i]];
  renderFb();
});
$('fFbAddBtn').onclick = () => {
  const v = $('fFbAdd').value;
  if (v && !dressFb.includes(v)) { dressFb.push(v); renderFb(); }
};
$('fAutoSwap').onchange = renderFb;
function fillFbAdd() {
  const ms = (modelsCache.opencode || []).map(m => m.id);
  const free = ms.filter(id => /free/i.test(id)), rest = ms.filter(id => !/free/i.test(id));
  const opts = l => l.map(id => `<option value="${esc(id)}">${esc(id)}</option>`).join('');
  $('fFbAdd').innerHTML = (free.length ? `<optgroup label="Gratis (${free.length})">${opts(free)}</optgroup>` : '')
    + (rest.length ? `<optgroup label="Otros (${rest.length})">${opts(rest)}</optgroup>` : '');
}
function pmVisible(isPm) {
  for (const id of ['fPmRow', 'fPm', 'fPmHint']) $(id).hidden = !isPm;
}
document.querySelectorAll('input[name=fEngine]').forEach(r => { r.onchange = () => { fillModels(r.value, null); skillsVisible(r.value); }; });
$('fPerm').onchange = permHint;

async function openDress(memberId, teamId) {
  try { await ensureModels(); } catch (e) { return toast(e.message); }
  applyMotores();
  try { rosterCache = DEMO ? demoRoster() : await api('/api/roster'); } catch (e) { return toast(e.message); }
  const m = memberId ? rosterCache.members.find(x => x.id === memberId) : null;
  if (!rosterCache.teams.length) return toast('Crea primero un equipo');
  dressMember = m;
  $('dressTitle').textContent = m ? `Vestuario · ${m.name}` : 'Contratar agente';
  $('fName').value = m?.name || '';
  $('fTeam').innerHTML = rosterCache.teams.map(t => `<option value="${esc(t.id)}">${esc(t.name)}</option>`).join('');
  $('fTeam').value = m?.team || teamId || rosterCache.teams[0].id;
  $('fPersona').value = m?.personality || '';
  $('fJob').value = m?.job || '';
  const engine = m?.engine || 'claude';
  document.querySelector(`input[name=fEngine][value=${engine}]`).checked = true;
  fillModels(engine, m?.model || (engine === 'claude' ? 'claude-sonnet-5-5' : null));
  $('fPerm').innerHTML = modelsCache.permissions.map(p => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
  $('fPerm').value = m?.permission || 'default'; permHint();
  $('fCwd').value = m?.cwd || '~';
  const have = new Set(m?.skills || []);
  $('fSkills').innerHTML = (modelsCache.skills || []).map(k => `<label><input type="checkbox" value="${esc(k.id)}"${have.has(k.id) ? ' checked' : ''}> ${esc(k.name)}</label>`).join('') || '<span class="mut">—</span>';
  skillsVisible(engine);
  const isPm = m?.role === 'pm';
  pmVisible(isPm);
  if (isPm) {
    const fb = (m.fallbacks || []).filter(f => f !== '__ninguno__');
    dressFb = fb.length ? fb : [...(modelsCache.defaultFallbacks || [])];
    $('fAutoSwap').checked = 'autoSwap' in m ? !!m.autoSwap : JSON.stringify(m.fallbacks) !== '["__ninguno__"]';
    fillFbAdd(); renderFb();
  }
  dressLook = { ...(m?.look || {}) };
  const r = rng(Date.now());
  for (const k of ['skin', 'hair', 'pants', 'shirt']) if (!dressLook[k]) dressLook[k] = pick(LOOK_OPTS[k], r);
  dressLook.accessory ||= 'ninguno';
  $('fAcc').value = dressLook.accessory; renderSwatches();
  $('dressFire').style.display = m ? '' : 'none';
  dressOrigLook = m?.look || {};
  dressStation = m ? stations.get('m:' + m.id) : null;
  if (dressStation) { dressStation.dressing = true; dressStation.applyDesire(); previewLook(); }
  $('dress').returnValue = '';
  $('dress').showModal();
}
$('dress').addEventListener('close', async () => {
  const st = dressStation; dressStation = null;
  if ($('dress').returnValue === 'save') {
    const body = {
      id: dressMember?.id, name: $('fName').value, team: $('fTeam').value, personality: $('fPersona').value, job: $('fJob').value,
      skills: [...document.querySelectorAll('#fSkills input:checked')].map(i => i.value),
      engine: document.querySelector('input[name=fEngine]:checked').value, model: $('fModel').value,
      permission: $('fPerm').value, cwd: $('fCwd').value, look: { ...dressLook },
    };
    if (dressMember?.role === 'pm') { body.fallbacks = [...dressFb]; body.autoSwap = $('fAutoSwap').checked; }
    if (DEMO) { toast('Modo demo: no se guarda'); st?.rebuildCharacter(dressOrigLook); }
    else {
      try { const m = await api('/api/member', body); toast(dressMember ? 'Guardado' : `${m.name} se une al equipo`); await poll(); }
      catch (e) { toast(e.message, 6000); st?.rebuildCharacter(dressOrigLook); }
    }
  } else st?.rebuildCharacter(dressOrigLook);
  if (st) setTimeout(() => { st.dressing = false; st.applyDesire(); }, 2500);
});
$('dressFire').onclick = async () => {
  if (!dressMember) return;
  if (!confirm(`¿Despedir a ${dressMember.name}? Desaparece de la oficina (su conversación sigue guardada en disco).`)) return;
  if (DEMO) return toast('Modo demo: no se guarda');
  try {
    await api('/api/delete', { kind: 'member', id: dressMember.id });
    if (chatId === 'm:' + dressMember.id) closeChat();
    $('dress').close('cancel'); toast('Despedido'); poll();
  } catch (e) { toast(e.message); }
};

// ---------- Liberty (voz) ----------
async function refreshVoice() {
  try { const c = DEMO ? { voz: false } : await api('/api/voice'); $('btnVoice').textContent = c.voz ? '♪ Voz: sí' : '♪ Voz: no'; $('btnVoice').dataset.on = c.voz ? '1' : ''; } catch (e) { /* sin servidor */ }
}
$('btnVoice').onclick = async () => {
  if (DEMO) return toast('Modo demo: Liberty no habla');
  const on = !$('btnVoice').dataset.on;
  try {
    await api('/api/voice', { on }); await refreshVoice();
    if (on) await api('/api/say', {});
    toast(on ? 'Liberty te avisará en voz alta' : 'Liberty se queda en silencio (los globos siguen)');
  } catch (e) { toast(e.message); }
};
refreshVoice();

// ---------- gastos ----------
initCosts({ api, DEMO, toast });
initListen({
  api, toast, token: TOKEN, demo: DEMO,
  libertyBusy: () => (lastData.agents || []).find(a => a.secretary)?.status === 'busy',
  send: async text => {
    try { await api('/api/order', { id: 'liberty', text: '(Te lo dice el usuario en voz alta, por el micrófono) ' + text }); setTimeout(poll, 400); }
    catch (e) { toast(e.message, 5000); }
  },
});

// ---------- datos ----------
function apply(data) {
  lastData = data;
  const L = officeLayout(data.agents, data.teams || []);
  buildWorld(L.bounds);
  const seen = new Set();
  for (const a of data.agents) {
    seen.add(a.id);
    const pos = L.pos.get(a.id);
    let s = stations.get(a.id);
    if (!s) { s = new Station(a, pos); stations.set(a.id, s); }
    else { s.leaving = false; if (pos) s.setTarget(pos[0], pos[1]); s.update(a); }
  }
  for (const [id, s] of stations) if (!seen.has(id)) { s.leaving = true; if (selectedId === id) selectedId = null; }
  buildRugs(L.rugs); renderPanel(data);
  if (chatId && !agentById(chatId)) closeChat();
}

const demoT0 = performance.now();
const DEMO_MEMBERS = [
  { id: 'rocio', name: 'Rocío', team: 'alfa', engine: 'claude', model: 'claude-sonnet-5-5', personality: 'Programadora meticulosa y tranquila.', look: { skin: '#e0ac85', hair: '#2b1d14', shirt: '#f08a3c', pants: '#3b4a6b', accessory: 'gafas' } },
  { id: 'bruno', name: 'Bruno', team: 'alfa', engine: 'claude', model: 'claude-haiku-5-5', personality: 'Tester gruñón pero entrañable.', look: { skin: '#c68863', hair: '#151515', shirt: '#45c47a', pants: '#2d2d33', accessory: 'gorra' } },
  { id: 'nube', name: 'Nube', team: 'alfa', engine: 'opencode', model: 'opencode/big-pickle', personality: 'Documentalista soñadora.', look: { skin: '#f5d7bd', hair: '#d6d6d6', shirt: '#3d7bf0', pants: '#30473a', accessory: 'auriculares' } },
  { id: 'iker', name: 'Iker', team: 'beta', engine: 'claude', model: 'claude-opus-5-5', personality: 'Arquitecto con visión de conjunto.', look: { skin: '#8d5a3b', hair: '#5a3a1e', shirt: '#9b6cff', pants: '#3b4a6b', accessory: 'ninguno' } },
];
function demoRoster() {
  return { teams: [{ id: 'alfa', name: 'Equipo Alfa', color: '#e0a030' }, { id: 'beta', name: 'Equipo Beta', color: '#3db0a0' }], members: DEMO_MEMBERS.map(m => ({ ...m, cwd: '~', permission: 'default' })) };
}
function demoData() {
  const ph = Math.floor((performance.now() - demoT0) / 7000);
  const tools = ['Read', 'Edit', 'Bash', 'Grep', 'Write', 'Agent', 'WebSearch'];
  const t = i => tools[(i + ph) % tools.length];
  const st = (period, off) => ((ph + off) % period) < period / 2 ? 'busy' : 'idle';
  const status = { rocio: st(4, 0), bruno: 'offline', nube: ph % 6 < 3 ? 'offline' : 'busy', iker: st(5, 2) };
  const members = DEMO_MEMBERS.map((m, i) => ({
    id: 'm:' + m.id, memberId: m.id, kind: 'member', parent: null, team: m.team, name: m.name, title: m.personality,
    model: m.model, engine: m.engine, status: status[m.id], tool: t(i), detail: ['src/app.ts', '', 'README.md', 'docs/arquitectura.md'][i],
    tokens: 20000 + i * 9000, cwd: '~', look: m.look, window: status[m.id] !== 'offline',
  }));
  const demoAtt = { rocio: { kind: 'listo', msg: '' }, iker: { kind: 'permiso', msg: 'Claude needs your permission to use Bash' } };
  for (const m of members) { const d = demoAtt[m.memberId]; if (d && m.status !== 'busy') m.attention = { ...d, sid: m.id, t: ph }; }
  const visitors = [
    { id: 'boss-demo', kind: 'session', boss: true, name: 'Claude', sessionName: 'mi-sesion', title: '~', model: 'claude-opus-5-5', status: st(4, 3), tool: t(3), detail: 'lib/app.js', tokens: 120000,
      look: { skin: '#e8b48a', hair: '#4a3326', shirt: '#f4efe6', pants: '#2d2f3a', accessory: 'capa', cape: '#d97757' } },
    { id: 's1', kind: 'session', name: 'poke-tactics', title: '~/Documentos/poke-tactics', model: 'claude-opus-5-5', status: st(4, 1), tool: t(0), detail: 'scripts/battle/effects.gd', tokens: 84000 },
    { id: 'a1', kind: 'subagent', parent: 's1', name: 'modelador', title: 'Props del mapa', model: 'claude-sonnet-5-5', status: st(3, 1), tool: t(2), detail: 'blender -b tiles.blend' },
    { id: 'oc1', kind: 'opencode', name: 'opencode · build', title: 'Documentar effects.gd', model: 'opencode/deepseek-v4.1-flash-free', status: st(3, 0), tool: 'shell', detail: 'Documentar effects.gd' },
  ];
  return { agents: [...members, ...visitors], teams: demoRoster().teams, claudeTeams: [] };
}

async function poll() {
  try {
    const data = DEMO ? demoData() : await api('/api/agents');
    apply(data);
    connEl.textContent = DEMO ? '● modo demo' : '● en directo'; connEl.style.color = DEMO ? '#ffe14d' : '#4cff7a';
  } catch (e) {
    console.error(e);
    connEl.textContent = '● sin conexión con server.py'; connEl.style.color = '#ff6b6b';
    if (!worldKey) buildWorld(officeLayout([]).bounds);
  }
}

// ---------- bucle ----------
const clock = new THREE.Clock();
let panelT = 0;
function loop() {
  const dt = Math.min(clock.getDelta(), 0.1), t = clock.elapsedTime;
  drawScreens(t);
  for (const tick of roomTicks) { try { tick(dt, t); } catch (e) { /* una sala rota no para la oficina */ } }
  for (const [id, s] of stations) if (!s.tick(dt, t)) { s.dispose(); stations.delete(id); }
  if (selectedId && stations.has(selectedId)) {
    stations.get(selectedId).worldPos(tmpV); tmpV.y = 1;
    const delta = tmpV.sub(controls.target).multiplyScalar(Math.min(1, dt * 3));
    controls.target.add(delta); camera.position.add(delta);
  }
  if ((panelT += dt) > 1) { panelT = 0; renderPanel(); }
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(loop);
}

// ---------- ajustes y primer uso ----------
// Oculta en el Vestuario los motores que el jefe desactivó en Ajustes (los miembros que ya los usan siguen igual)
function applyMotores() {
  const on = modelsCache?.motores || { claude: true, opencode: true, kimi: true };
  document.querySelectorAll('input[name=fEngine]').forEach(r => {
    const lab = r.closest('label');
    if (lab) lab.hidden = !on[r.value] && !r.checked;
  });
}
const MOTOR_NOMBRE = { claude: 'Claude Code', opencode: 'OpenCode', kimi: 'Kimi Code' };
const MOTOR_AYUDA = {
  claude: 'Instálalo y entra con tu cuenta (comando claude).',
  opencode: 'Instálalo y añade proveedores con «opencode auth» (comando opencode).',
  kimi: 'Instálalo y entra con tu cuenta (comando kimi).',
};
async function abrirAjustes(primera = false) {
  let d;
  try { d = await api('/api/ajustes'); } catch (e) { return toast(e.message); }
  const a = d.ajustes;
  $('setupTitle').textContent = primera ? 'Configurar la oficina' : 'Ajustes de la oficina';
  $('sJefe').value = a.jefe;
  $('sMotores').innerHTML = ['claude', 'opencode', 'kimi'].map(m => {
    const ok = d.detectados[m];
    return `<label><input type="checkbox" name="sMotor" value="${m}"${a.motores[m] ? ' checked' : ''}> ${MOTOR_NOMBRE[m]} ${ok ? '<span class="mut">(instalado)</span>' : '<span class="warn">(no encontrado)</span>'}</label>`;
  }).join('');
  $('sMotoresHint').innerHTML = ['claude', 'opencode', 'kimi'].filter(m => !d.detectados[m])
    .map(m => `${MOTOR_NOMBRE[m]}: ${MOTOR_AYUDA[m]}`).join('<br>');
  document.querySelectorAll('input[name=sAhorro]').forEach(r => { r.checked = r.value === a.ahorro; });
  $('sGratis').textContent = d.gratisOpenCode.length
    ? `Modelos gratuitos de OpenCode disponibles ahora: ${d.gratisOpenCode.length}.`
    : 'No veo modelos gratuitos de OpenCode. Revisa los proveedores con «opencode auth».';
  $('sProv').textContent = d.proveedores.length
    ? `Proveedores de OpenCode con clave: ${d.proveedores.join(', ')}. Para añadir otro, usa «opencode auth».`
    : 'No hay ningún proveedor de OpenCode con clave. Añádelo con «opencode auth» en una terminal.';
  $('sError').hidden = true;
  pintarVoz(d.voz);
  $('setup').dataset.primera = primera ? '1' : '';
  $('setup').showModal();
}
$('btnAjustes').onclick = () => abrirAjustes(false);

// Descarga de la voz de Liberty, con progreso mientras dura
let vozTimer = null;
function pintarVoz(v) {
  const txt = v.instalada ? 'Instalada. Liberty puede hablar y escuchar.'
    : v.fase === 'error' ? `No se pudo instalar: ${v.error}`
    : v.fase === 'no instalada' ? `No instalada (${v.tamano}).`
    : `${v.fase}: ${v.detalle}`;
  $('vozEstado').textContent = txt;
  $('vozEstado').classList.toggle('warn', v.fase === 'error');
  $('vozBtn').hidden = !!v.instalada || ['creando entorno', 'instalando paquetes', 'descargando modelos', 'copiando servidores'].includes(v.fase);
  if (!v.instalada && ['creando entorno', 'instalando paquetes', 'descargando modelos', 'copiando servidores'].includes(v.fase)) {
    if (!vozTimer) vozTimer = setInterval(async () => {
      try {
        const e = await api('/api/voz/estado');
        pintarVoz(e);
        if (e.instalada || e.fase === 'error') { clearInterval(vozTimer); vozTimer = null; }
      } catch (_) { /* reintenta en el siguiente tic */ }
    }, 2000);
  }
}
$('vozBtn').onclick = async () => {
  try {
    const e = await api('/api/voz/descargar', {});
    pintarVoz(e);
  } catch (err) { toast(err.message); }
};
$('setupSave').onclick = async e => {
  e.preventDefault();
  const motores = Object.fromEntries([...document.querySelectorAll('input[name=sMotor]')].map(c => [c.value, c.checked]));
  const body = {
    jefe: $('sJefe').value, motores, configurado: true,
    ahorro: document.querySelector('input[name=sAhorro]:checked')?.value || 'normal',
  };
  try {
    await api('/api/ajustes', body);
    $('setup').close();
    toast('Ajustes guardados');
    await poll();
  } catch (err) {
    $('sError').textContent = err.message; $('sError').hidden = false;
  }
};
// primer uso: si nunca se han guardado ajustes, se abre el asistente al cargar
api('/api/ajustes').then(d => { if (!d.ajustes.configurado) abrirAjustes(true); }).catch(() => {});

// ---------- arranque ----------
try { await Promise.race([document.fonts.load('40px VT323'), new Promise(r => setTimeout(r, 1500))]); } catch (e) { /* monospace */ }
await Promise.all([...new Set(ROOMS.map(r => r.file))].map(async f => {
  try { roomsLoaded.set(f, await import(`../rooms/${f}.js?v=${Date.now()}`)); }
  catch (e) { console.warn('sala no disponible:', f, e.message); roomsLoaded.set(f, null); }
}));
window.__office = { stations, get plan() { return plan; }, occupied, camera, controls };
poll(); setInterval(poll, POLL_MS); loop();
