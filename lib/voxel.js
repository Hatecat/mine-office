// Utilidades compartidas de la oficina de bloques: texturas pixel-art, materiales y ayudas de geometría.
// Las salas (rooms/*.js) reciben este módulo entero como `V`.
import * as THREE from 'three';
export { THREE };

export function rng(seed) { let s = (seed >>> 0) || 1; return () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; }; }
export function hash(str) { let h = 2166136261; for (const c of str) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
export function shade(hex, f) {
  const n = parseInt(hex.slice(1), 16);
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(v => Math.max(0, Math.min(255, Math.round(v * f))));
  return '#' + c.map(v => v.toString(16).padStart(2, '0')).join('');
}
export const pick = (arr, r) => arr[Math.floor(r() * arr.length) % arr.length];
export function px(g, x, y, col) { g.fillStyle = col; g.fillRect(x, y, 1, 1); }
export function noiseFill(g, r, w, h, base, amt) { for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) px(g, x, y, shade(base, 1 + (r() - 0.5) * amt)); }

/** Textura pixel-art: paint(ctx2d, rand, w, h). Filtro nearest, sRGB, repetible. */
export function pixelTex(w, h, paint, seed = 1) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  paint(c.getContext('2d'), rng(seed), w, h);
  const t = new THREE.CanvasTexture(c);
  t.magFilter = t.minFilter = THREE.NearestFilter; t.generateMipmaps = false;
  t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}
/** Material Lambert con textura (o null) y opciones extra. */
export const lam = (map, extra = {}) => new THREE.MeshLambertMaterial({ map, ...extra });
/** Material Lambert de color liso. */
export const col = (color, extra = {}) => new THREE.MeshLambertMaterial({ color, ...extra });
/** Material que brilla (pantallas, luces): no le afecta la iluminación. */
export const glow = (color, extra = {}) => new THREE.MeshBasicMaterial({ color, ...extra });

/** Texto pixel-art sobre transparente, para carteles. Devuelve una CanvasTexture. */
export function textTex(text, { color = '#ffffff', bg = null, font = 'VT323, monospace', px: size = 48, pad = 8 } = {}) {
  const c = document.createElement('canvas'); const g = c.getContext('2d');
  g.font = `${size}px ${font}`;
  c.width = Math.ceil(g.measureText(text).width + pad * 2); c.height = size + pad * 2;
  if (bg) { g.fillStyle = bg; g.fillRect(0, 0, c.width, c.height); }
  g.font = `${size}px ${font}`; g.fillStyle = color; g.textBaseline = 'middle'; g.fillText(text, pad, c.height / 2 + 2);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  t.userData = { aspect: c.width / c.height };
  return t;
}
/** Cartel plano con texto. height en bloques; mira hacia +z. */
export function sign(text, height = 0.4, opts = {}) {
  const t = textTex(text, opts);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(height * t.userData.aspect, height), new THREE.MeshBasicMaterial({ map: t, transparent: !opts.bg }));
  return m;
}

export const TEX = {
  planks: pixelTex(16, 16, (g, r) => {
    noiseFill(g, r, 16, 16, '#a8773f', 0.16);
    for (let row = 0; row < 4; row++) {
      for (let x = 0; x < 16; x++) px(g, x, row * 4 + 3, shade('#a8773f', 0.68));
      const seam = (row * 7 + 3) % 16;
      for (let y = 0; y < 3; y++) px(g, seam, row * 4 + y, shade('#a8773f', 0.72));
    }
  }, 11),
  darkwood: pixelTex(16, 16, (g, r) => {
    noiseFill(g, r, 16, 16, '#6b4a2b', 0.18);
    for (let x = 0; x < 16; x++) { px(g, x, 7, '#4b331d'); px(g, x, 15, '#4b331d'); }
  }, 12),
  plaster: pixelTex(16, 16, (g, r) => noiseFill(g, r, 16, 16, '#e4dccb', 0.07), 13),
  grassTop: pixelTex(16, 16, (g, r) => noiseFill(g, r, 16, 16, '#69a94c', 0.28), 14),
  dirt: pixelTex(16, 16, (g, r) => noiseFill(g, r, 16, 16, '#7a5534', 0.26), 15),
  grassSide: pixelTex(16, 16, (g, r) => {
    noiseFill(g, r, 16, 16, '#7a5534', 0.26);
    for (let x = 0; x < 16; x++) { const d = 2 + Math.floor(r() * 3); for (let y = 0; y < d; y++) px(g, x, y, shade('#69a94c', 1 + (r() - 0.5) * 0.25)); }
  }, 16),
  glass: pixelTex(16, 16, (g) => {
    g.fillStyle = 'rgba(170,215,255,0.28)'; g.fillRect(0, 0, 16, 16);
    g.fillStyle = 'rgba(235,245,255,0.85)'; g.fillRect(0, 0, 16, 1); g.fillRect(0, 15, 16, 1); g.fillRect(0, 0, 1, 16); g.fillRect(15, 0, 1, 16);
    for (let i = 0; i < 4; i++) { px(g, 4 + i, 7 - i, 'rgba(255,255,255,0.7)'); px(g, 8 + i, 11 - i, 'rgba(255,255,255,0.5)'); }
  }, 17),
  books: pixelTex(16, 16, (g, r) => {
    noiseFill(g, r, 16, 16, '#6b4a2b', 0.15);
    const cols = ['#b23a3a', '#3a6bb2', '#3aa25a', '#d9a53a', '#7a3ab2', '#e0e0e0'];
    for (const y0 of [1, 9]) { for (let x = 1; x < 15; x++) { const c = pick(cols, r); const top = y0 + Math.floor(r() * 2); for (let y = top; y < y0 + 6; y++) px(g, x, y, shade(c, 0.85 + r() * 0.3)); } }
  }, 18),
  leaves: pixelTex(16, 16, (g, r) => { noiseFill(g, r, 16, 16, '#3f8f3a', 0.45); for (let i = 0; i < 18; i++) px(g, Math.floor(r() * 16), Math.floor(r() * 16), '#2a5e27'); }, 19),
  pot: pixelTex(16, 16, (g, r) => { noiseFill(g, r, 16, 16, '#a5553a', 0.16); for (let x = 0; x < 16; x++) { px(g, x, 0, '#7d3d28'); px(g, x, 1, '#c26b4d'); } }, 20),
  tiles: pixelTex(16, 16, (g, r) => {
    for (let y = 0; y < 16; y++) for (let x = 0; x < 16; x++) {
      const light = ((x >> 3) + (y >> 3)) % 2 === 0;
      px(g, x, y, shade(light ? '#e9e4d8' : '#cfc7b6', 1 + (r() - 0.5) * 0.06));
    }
    for (let i = 0; i < 16; i++) { px(g, i, 0, '#b3ab9a'); px(g, 0, i, '#b3ab9a'); px(g, i, 8, '#b3ab9a'); px(g, 8, i, '#b3ab9a'); }
  }, 21),
  checker: pixelTex(16, 16, (g, r) => {
    for (let y = 0; y < 16; y++) for (let x = 0; x < 16; x++) {
      const dark = ((x >> 3) + (y >> 3)) % 2 === 0;
      px(g, x, y, shade(dark ? '#2c2f38' : '#e8e8ec', 1 + (r() - 0.5) * 0.08));
    }
  }, 22),
  metal: pixelTex(16, 16, (g, r) => noiseFill(g, r, 16, 16, '#9aa1ab', 0.1), 23),
};
export function carpetTex(color, seed = 5) { return pixelTex(16, 16, (g, r) => noiseFill(g, r, 16, 16, color, 0.14), seed); }

export const MAT = {
  planks: lam(TEX.planks), darkwood: lam(TEX.darkwood), plaster: lam(TEX.plaster),
  glass: new THREE.MeshLambertMaterial({ map: TEX.glass, transparent: true, depthWrite: false }),
  leaves: lam(TEX.leaves), pot: lam(TEX.pot), tiles: lam(TEX.tiles), checker: lam(TEX.checker),
  metal: lam(TEX.metal), dark: col(0x23262e), white: col(0xe9edf2), chair: col(0x2f3b55),
  lamp: glow(0xffe9a8), water: col(0x7fc4ff, { transparent: true, opacity: 0.7 }),
};
MAT.grass = [lam(TEX.grassSide), lam(TEX.grassSide), lam(TEX.grassTop), lam(TEX.dirt), lam(TEX.grassSide), lam(TEX.grassSide)];
MAT.dirt = lam(TEX.dirt);
MAT.shelf = [MAT.darkwood, MAT.darkwood, MAT.darkwood, MAT.darkwood, lam(TEX.books), MAT.darkwood];

export const UNIT = new THREE.BoxGeometry(1, 1, 1);

/** Muchos cubos con el mismo material. cells: [x, y, z, sx?, sy?, sz?] (centro y escala). */
export function instCubes(cells, mat, shadow = true) {
  const m = new THREE.InstancedMesh(UNIT, mat, cells.length);
  const o = new THREE.Object3D();
  cells.forEach((c, i) => { o.position.set(c[0], c[1], c[2]); o.scale.set(c[3] || 1, c[4] || 1, c[5] || 1); o.updateMatrix(); m.setMatrixAt(i, o.matrix); });
  m.castShadow = shadow; m.receiveShadow = true;
  return m;
}
/** Caja de tamaño w×h×d con centro en (x, y, z). mat puede ser un array de 6 (px, nx, py, ny, pz, nz). */
export function box(w, h, d, mat, x = 0, y = 0, z = 0) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  m.position.set(x, y, z); m.castShadow = m.receiveShadow = true; return m;
}
/** Libera geometrías propias (no la UNIT compartida) de un árbol de objetos. */
export function disposeTree(obj) {
  obj.traverse(o => {
    if (o.isInstancedMesh) o.dispose();
    else if (o.isMesh && o.geometry !== UNIT) o.geometry.dispose();
  });
}
