// Sala de juegos: arcades inventados, mesa de billar, pufs, neón y máquina de bebidas.
export const meta = { id: 'juegos', title: 'Sala de juegos', size: [10, 8], floor: 'carpet', floorColor: '#3b2f5c' };

export default function build(V) {
  const { THREE, box, col, glow, lam, pixelTex, noiseFill, px, shade } = V;
  const g = new THREE.Group();
  const tri = (u) => 1 - Math.abs((((u % 2) + 2) % 2) - 1); // onda triangular 0..1

  // ---------- Minijuegos (canvas 32x24, todo inventado) ----------
  const W = 32, H = 24;
  const mkScreen = () => {
    const c = document.createElement('canvas'); c.width = W; c.height = H;
    const t = new THREE.CanvasTexture(c);
    t.magFilter = t.minFilter = THREE.NearestFilter; t.generateMipmaps = false; t.colorSpace = THREE.SRGBColorSpace;
    return { c, ctx: c.getContext('2d'), t };
  };
  const rect = (s, x, y, w, h, color) => { s.ctx.fillStyle = color; s.ctx.fillRect(Math.round(x), Math.round(y), w, h); };
  const BR = ['#e05050', '#e0a030', '#e0e050', '#50c060', '#4090e0'];
  const games = [
    // 0: bloques y pelota
    (s, t) => {
      rect(s, 0, 0, W, H, '#10102a');
      for (let r = 0; r < 5; r++) for (let i = 0; i < 8; i++) {
        if ((i * 7 + r * 3 + Math.floor(t / 6)) % 11 === 0) continue; // algún hueco que cambia
        rect(s, 1 + i * 4, 2 + r * 2, 3, 1, BR[r]);
      }
      const bx = 1 + tri(t * 0.9) * 29, by = 13 + tri(t * 1.3) * 7;
      rect(s, bx, by, 2, 2, '#ffffff');
      rect(s, 2 + tri(t * 0.9 + 0.1) * 22, 22, 7, 1, '#60e0ff');
    },
    // 1: naves y estrellas
    (s, t) => {
      rect(s, 0, 0, W, H, '#05051a');
      for (let i = 0; i < 14; i++) rect(s, (i * 11 + 5) % W, ((i * 7 + t * (6 + (i % 3) * 4)) % H), 1, 1, i % 3 ? '#8888cc' : '#ffffff');
      const off = Math.sin(t * 1.5) * 4;
      for (let r = 0; r < 3; r++) for (let i = 0; i < 6; i++) {
        const ex = 4 + i * 4 + off, ey = 2 + r * 3;
        rect(s, ex, ey, 3, 2, r === 1 ? '#ff6090' : '#80ff80'); rect(s, ex, ey + 2, 1, 1, '#ffffff');
      }
      const sx = 14 + Math.sin(t * 0.8) * 11;
      rect(s, sx, 20, 3, 2, '#ffd040'); rect(s, sx + 1, 19, 1, 1, '#ffd040');
      rect(s, sx + 1, 20 - ((t * 24) % 18), 1, 2, '#ff4040');
    },
    // 2: pelota y palas
    (s, t) => {
      rect(s, 0, 0, W, H, '#0a2a1a');
      for (let y = 0; y < H; y += 3) rect(s, 15, y, 2, 2, '#2a6a4a');
      const bx = 3 + tri(t * 0.8) * 25, by = 1 + tri(t * 1.1) * 21;
      rect(s, 2, by - 3 + Math.sin(t) * 1.5, 1, 6, '#ff9050');
      rect(s, 29, 21 - by + 1 - 3 + Math.cos(t) * 1.5, 1, 6, '#50a0ff');
      rect(s, bx, by, 2, 2, '#ffffff');
      rect(s, 8, 1, 3, 1, '#ff9050'); rect(s, 21, 1, 3, 1, '#50a0ff');
    },
  ];

  // ---------- Arcades ----------
  const screens = [];
  const arcades = [
    { x: 2.2, body: '#c0392b', trim: '#ffcf4a', name: 'BLOQUES', mq: '#ff4fa0' },
    { x: 3.6, body: '#2f6fd0', trim: '#7ff0ff', name: 'NAVES', mq: '#40e0ff' },
    { x: 5.0, body: '#2e9e5b', trim: '#ffd84a', name: 'PELOTA', mq: '#ffe040' },
  ];
  arcades.forEach((a, i) => {
    const m = new THREE.Group();
    const body = col(a.body), dark = col(shade(a.body, 0.55)), trim = col(a.trim);
    m.add(box(0.9, 0.95, 0.9, body, 0, 0.475, 0));                  // cuerpo inferior
    m.add(box(0.9, 0.65, 0.6, body, 0, 1.275, -0.15));              // cuerpo superior
    m.add(box(0.94, 0.1, 0.46, dark, 0, 1.0, 0.34));                // panel de mandos
    m.add(box(0.06, 0.95, 0.9, trim, -0.46, 0.475, 0));             // franjas laterales
    m.add(box(0.06, 0.95, 0.9, trim, 0.46, 0.475, 0));
    m.add(box(0.8, 0.5, 0.04, col(0x101018), 0, 1.3, 0.16));        // bisel de pantalla
    // pantalla animada
    const s = mkScreen(); screens.push(s);
    const scr = new THREE.Mesh(new THREE.PlaneGeometry(0.7, 0.52), glow(0xffffff, { map: s.t }));
    scr.position.set(0, 1.3, 0.185); m.add(scr);
    // marquesina iluminada
    m.add(box(0.94, 0.3, 0.7, dark, 0, 1.75, -0.1));
    const mq = new THREE.Mesh(new THREE.PlaneGeometry(0.84, 0.22), glow(a.mq)); mq.position.set(0, 1.75, 0.255); m.add(mq);
    const nm = V.sign(a.name, 0.15, { color: '#1a1030', px: 36 }); nm.position.set(0, 1.75, 0.26); m.add(nm);
    // joystick y botones
    m.add(box(0.05, 0.14, 0.05, col(0x15151c), -0.22, 1.12, 0.38));
    const ball = new THREE.Mesh(new THREE.SphereGeometry(0.07, 6, 4), col(0xd02030)); ball.position.set(-0.22, 1.21, 0.38); ball.castShadow = true; m.add(ball);
    [['#ff4040', 0.05], ['#40d0ff', 0.2], ['#ffe040', 0.35]].forEach(([c, dx]) => {
      m.add(box(0.1, 0.05, 0.1, glow(c), dx - 0.02, 1.07, 0.42 - (dx > 0.3 ? 0.07 : 0)));
    });
    m.add(box(0.7, 0.08, 0.04, dark, 0, 0.1, 0.46));                // zócalo
    m.position.set(a.x, 0, 0.5);
    g.add(m);
  });

  // ---------- Mesa de billar (centro-derecha) ----------
  const px0 = 7.0, pz0 = 4.5;
  const felt = lam(pixelTex(16, 16, (c, r) => { noiseFill(c, r, 16, 16, '#2c8a4a', 0.14); }, 31));
  const wood = V.MAT.darkwood;
  const pool = new THREE.Group();
  [[-1.25, -0.65], [1.25, -0.65], [-1.25, 0.65], [1.25, 0.65]].forEach(([lx, lz]) => pool.add(box(0.22, 0.55, 0.22, wood, lx, 0.275, lz)));
  pool.add(box(2.8, 0.3, 1.6, wood, 0, 0.7, 0));                   // cuerpo bajo el tapete
  pool.add(box(2.4, 0.06, 1.2, felt, 0, 0.85, 0));                 // tapete
  pool.add(box(2.8, 0.12, 0.2, V.MAT.planks, 0, 0.91, -0.7));      // bandas
  pool.add(box(2.8, 0.12, 0.2, V.MAT.planks, 0, 0.91, 0.7));
  pool.add(box(0.2, 0.12, 1.2, V.MAT.planks, -1.3, 0.91, 0));
  pool.add(box(0.2, 0.12, 1.2, V.MAT.planks, 1.3, 0.91, 0));
  const hole = col(0x08080c);
  [[-1.15, -0.55], [1.15, -0.55], [-1.15, 0.55], [1.15, 0.55], [0, -0.57], [0, 0.57]].forEach(([hx, hz]) => pool.add(box(0.2, 0.02, 0.2, hole, hx, 0.885, hz)));
  // bolas: triángulo de 10 + blanca
  const bc = ['#e03030', '#2060d0', '#f0c020', '#8030b0', '#f07020', '#20a050', '#a02020', '#202020', '#e0e040', '#40c0d0'];
  const bgeo = new THREE.SphereGeometry(0.075, 6, 5);
  let bi = 0;
  for (let row = 0; row < 4; row++) for (let k = 0; k <= row; k++) {
    const b = new THREE.Mesh(bgeo, col(bc[bi++])); b.castShadow = true;
    b.position.set(0.55 + row * 0.14, 0.955, (k - row / 2) * 0.16); pool.add(b);
  }
  const cue = new THREE.Mesh(bgeo, col(0xf4f4f4)); cue.castShadow = true; cue.position.set(-0.7, 0.955, 0.05); pool.add(cue);
  pool.position.set(px0, 0, pz0);
  g.add(pool);

  // lámpara colgante sobre el billar
  g.add(box(0.04, 1.2, 0.04, col(0x222228), px0, 3.0, pz0));
  g.add(box(1.4, 0.14, 0.3, col(0x2a8a50), px0, 2.4, pz0));
  const lampG = new THREE.Mesh(new THREE.PlaneGeometry(1.3, 0.22), glow(0xfff0b0));
  lampG.rotation.x = Math.PI / 2; lampG.position.set(px0, 2.32, pz0); g.add(lampG);

  // soporte con dos tacos apoyados (derecha, junto a la pared)
  const cx = 9.15, cz = 2.2;
  g.add(box(0.5, 0.08, 0.3, wood, cx, 0.04, cz));
  g.add(box(0.5, 0.5, 0.05, wood, cx, 0.3, cz - 0.15));
  [-0.12, 0.12].forEach((dx, i) => {
    const t = box(0.05, 1.5, 0.05, i ? V.MAT.planks : col(0xc9a35c), cx + dx, 0.78, cz - 0.08);
    t.rotation.x = -0.1; g.add(t);
    g.add(box(0.06, 0.12, 0.06, col(0x2060c0), cx + dx, 1.5, cz - 0.17));
  });

  // ---------- Extras ----------
  // pufs y mesita
  const pufs = [[0.9, 6.4, '#e0527a'], [3.0, 6.4, '#f0a030']];
  pufs.forEach(([x, z, c]) => {
    g.add(box(0.72, 0.34, 0.72, col(c), x, 0.17, z));
    g.add(box(0.6, 0.08, 0.6, col(shade(c, 1.15)), x, 0.38, z));
  });
  g.add(box(0.5, 0.05, 0.5, V.MAT.planks, 1.95, 0.4, 6.4));
  g.add(box(0.1, 0.38, 0.1, V.MAT.darkwood, 1.95, 0.19, 6.4));

  // neón en la pared del fondo (entre los arcades y la máquina de bebidas)
  const neon = V.sign('GAME ON', 0.45, { color: '#ff5ad0', px: 56 });
  neon.position.set(7.2, 1.35, -0.46); g.add(neon);
  const neon2 = new THREE.Mesh(new THREE.PlaneGeometry(1.5, 0.05), glow(0x5affff)); neon2.position.set(7.2, 1.05, -0.46); g.add(neon2);

  // máquina de bebidas
  const dm = new THREE.Group();
  dm.add(box(0.9, 1.7, 0.8, col(0x2d62c4), 0, 0.85, 0));
  dm.add(box(0.7, 1.0, 0.04, glow(0x9fe8ff), -0.05, 1.05, 0.41));
  ['#ff5050', '#ffd040', '#60e060', '#ff8030'].forEach((c, i) => {
    dm.add(box(0.12, 0.2, 0.03, glow(c), -0.27 + (i % 2) * 0.3, 1.3 - Math.floor(i / 2) * 0.4, 0.44));
    dm.add(box(0.12, 0.2, 0.03, glow(shade(c, 0.8)), -0.12 + (i % 2) * 0.3 + 0.15, 1.3 - Math.floor(i / 2) * 0.4, 0.44));
  });
  dm.add(box(0.6, 0.18, 0.04, col(0x10141c), 0, 0.3, 0.41));
  dm.position.set(8.8, 0, 0.5); g.add(dm);

  // ---------- Sitios ----------
  g.userData.spots = [
    ...arcades.map(a => ({ x: a.x, z: 1.5, y: 0, rotY: Math.PI, pose: 'stand', activity: 'play' })),
    { x: px0, z: 3.25, y: 0, rotY: 0, pose: 'stand', activity: 'pool' },
    { x: px0 + 0.4, z: 5.75, y: 0, rotY: Math.PI, pose: 'stand', activity: 'pool' },
    { x: 9.0, z: pz0, y: 0, rotY: -Math.PI / 2, pose: 'stand', activity: 'pool' },
    { x: 0.9, z: 6.4, y: 0.4, rotY: Math.PI / 2, pose: 'sit', activity: 'chat' },
    { x: 3.0, z: 6.4, y: 0.4, rotY: -Math.PI / 2, pose: 'sit', activity: 'chat' },
  ];

  // ---------- Animación: pantallas a ~8 fps ----------
  let acc = 0;
  g.userData.tick = (dt, t) => {
    acc += dt;
    if (acc < 0.125) return;
    acc = 0;
    screens.forEach((s, i) => { games[i](s, t); s.t.needsUpdate = true; });
  };
  games.forEach((f, i) => { f(screens[i], 0); screens[i].t.needsUpdate = true; });
  return g;
}
