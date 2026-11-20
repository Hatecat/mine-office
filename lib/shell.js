// Suelo, paredes, puerta y cartel de una sala. Lo usan la oficina y room-test.html.
import * as V from './voxel.js';
const { THREE } = V;

export function floorMaterial(meta) {
  if (meta.floor === 'tiles') return V.MAT.tiles;
  if (meta.floor === 'checker') return V.MAT.checker;
  if (meta.floor === 'carpet') return V.lam(V.carpetTex(meta.floorColor || '#7a6a9a', V.hash(meta.id || 'x')));
  return V.MAT.planks;
}
export function doorCells(meta) { const D = meta.size[1]; return [Math.floor(D / 2) - 1, Math.floor(D / 2)]; }

/** Grupo con suelo de la sala (interior) y paredes de 2 de alto con puerta en -x. Coordenadas locales de sala. */
export function roomShell(meta, { wallH = 2, lowH = 1, wH = wallH, eH = lowH, walls = ['n', 's', 'e', 'w'] } = {}) {
  const [W, D] = meta.size;
  const g = new THREE.Group();
  const floor = [];
  for (let x = 0; x < W; x++) for (let z = 0; z < D; z++) floor.push([x, -0.5, z]);
  g.add(V.instCubes(floor, floorMaterial(meta)));
  const door = new Set(doorCells(meta));
  const trim = [], plaster = [];
  // paredes del fondo (n) y de la puerta (w) altas; las del frente (s) y la derecha (e) bajas para ver dentro
  const put = (x, z, h = wallH) => { for (let y = 0; y < h; y++) (y === h - 1 ? trim : plaster).push([x, y + 0.5, z]); };
  if (walls.includes('n')) for (let x = -1; x < W; x++) put(x, -1);
  if (walls.includes('s')) for (let x = -1; x <= W; x++) put(x, D, x === -1 ? wallH : lowH);
  if (walls.includes('w')) for (let z = 0; z < D; z++) if (!door.has(z)) put(-1, z, wH);
  if (walls.includes('e')) { for (let z = 0; z < D; z++) put(W, z, eH); if (walls.includes('n')) put(W, -1); }
  // suelo bajo las paredes y en el hueco de la puerta
  const under = [];
  for (let x = -1; x <= W; x++) { under.push([x, -0.5, -1], [x, -0.5, D]); }
  for (let z = 0; z < D; z++) { under.push([-1, -0.5, z], [W, -0.5, z]); }
  g.add(V.instCubes(under, V.MAT.planks));
  if (plaster.length) g.add(V.instCubes(plaster, V.MAT.plaster));
  if (trim.length) g.add(V.instCubes(trim, V.MAT.darkwood));
  // cartel sobre la puerta, mirando hacia -x (al pasillo)
  if (meta.title) {
    const s = V.sign(meta.title, 0.42, { color: '#fff', bg: '#2a2f3a', px: 40 });
    const [z0, z1] = doorCells(meta);
    s.position.set(-1.52, wH + 0.3, (z0 + z1) / 2); s.rotation.y = -Math.PI / 2;
    g.add(s);
    const back = s.clone(); back.position.x = -0.48; back.rotation.y = Math.PI / 2; g.add(back);
  }
  return g;
}
