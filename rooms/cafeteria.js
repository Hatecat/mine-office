// Cafetería: barra con dos máquinas de espresso, mesas, taburetes y vapor animado.
export const meta = { id: 'cafeteria', title: 'Cafetería', size: [10, 8], floor: 'tiles' };

export default function build(V, opts = {}) {
  const { THREE, box, col, glow, sign } = V;
  const g = new THREE.Group();
  const vapores = []; // cubitos de vapor animados en tick

  const wood = V.MAT.darkwood, planks = V.MAT.planks, metal = V.MAT.metal;
  const ceramica = col(0xf4efe4), cafe = col(0x3a2012);

  // --- Taza: cuerpo + asa + café ---
  function taza(x, y, z, color = 0xf4efe4, lleno = true) {
    const t = new THREE.Group();
    t.add(box(0.16, 0.13, 0.16, col(color), 0, 0.065, 0));
    t.add(box(0.05, 0.08, 0.03, col(color), 0.105, 0.07, 0));
    if (lleno) t.add(box(0.12, 0.01, 0.12, cafe, 0, 0.13, 0));
    t.position.set(x, y, z);
    return t;
  }

  // --- Vapor: cubitos blancos que suben y se desvanecen ---
  function vapor(x, y, z, n = 4) {
    for (let i = 0; i < n; i++) {
      const m = new THREE.Mesh(V.UNIT, new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0, depthWrite: false }));
      m.position.set(x, y, z);
      g.add(m);
      vapores.push({ m, x, y, z, fase: i / n, vel: 0.35 + (i % 2) * 0.1, ox: (i % 3 - 1) * 0.04 });
    }
  }

  // --- Máquina de espresso grande (mira hacia +z; origen en la base) ---
  function maquina(x, y, z, color, luz) {
    const m = new THREE.Group();
    const cuerpo = col(color), oscuro = col(0x2a2d34);
    m.add(box(1.0, 0.7, 0.62, cuerpo, 0, 0.35, 0));                // cuerpo
    m.add(box(1.04, 0.08, 0.66, col(0xd8dde4), 0, 0.74, 0));       // tapa cromada
    m.add(box(0.5, 0.3, 0.3, V.MAT.glass, -0.22, 0.93, -0.08));    // depósito
    m.add(box(0.44, 0.18, 0.24, col(0x5a3a22), -0.22, 0.85, -0.08)); // granos / agua oscura
    m.add(box(0.16, 0.08, 0.16, oscuro, 0.3, 0.82, -0.05));         // tolva pequeña
    // panel frontal con botones con luz
    m.add(box(0.9, 0.22, 0.04, oscuro, 0, 0.55, 0.32));
    const lc = [luz, 0x66ff88, 0xffd04a, 0xff5a5a];
    for (let i = 0; i < 4; i++) m.add(box(0.1, 0.1, 0.03, glow(lc[i]), -0.3 + i * 0.2, 0.55, 0.35));
    // grupo: boquillas y portafiltro
    m.add(box(0.7, 0.1, 0.12, col(0xd8dde4), 0, 0.37, 0.37));
    for (const dx of [-0.2, 0.2]) {
      m.add(box(0.14, 0.1, 0.14, oscuro, dx, 0.3, 0.4));            // portafiltro
      m.add(box(0.05, 0.05, 0.2, wood, dx, 0.3, 0.55));              // mango
      m.add(box(0.03, 0.09, 0.03, col(0xb8bec8), dx, 0.2, 0.4));    // chorro/boquilla
    }
    // bandeja de goteo y tazas debajo
    m.add(box(0.8, 0.04, 0.3, oscuro, 0, 0.02, 0.4));
    m.add(taza(-0.2, 0.04, 0.4, 0xf4efe4));
    m.add(taza(0.2, 0.04, 0.4, color === 0xb33a3a ? 0xffd04a : 0xf4efe4));
    // varita de vapor
    m.add(box(0.04, 0.34, 0.04, col(0xb8bec8), 0.55, 0.45, 0.22));
    m.position.set(x, y, z);
    g.add(m);
    vapor(x - 0.2, y + 0.28, z + 0.4, 3);   // sobre la taza izquierda
    vapor(x + 0.2, y + 0.28, z + 0.4, 3);
    vapor(x + 0.55, y + 0.65, z + 0.22, 2); // de la varita
  }

  // --- Barra / mostrador contra el fondo ---
  const cx = 6.1, cw = 6.6;
  g.add(box(cw, 1.0, 1.0, wood, cx, 0.5, 0.65));
  g.add(box(cw + 0.1, 0.1, 1.1, planks, cx, 1.05, 0.65)); // encimera, y superior 1.1
  g.add(box(cw, 0.14, 0.06, col(0xc7a24a), cx, 0.55, 1.18)); // franja decorativa

  maquina(4.6, 1.1, 0.55, 0xb33a3a, 0x66ff88);
  maquina(7.6, 1.1, 0.55, 0x2f7f86, 0xff5a5a);

  // molinillo entre las dos máquinas
  const mol = new THREE.Group();
  mol.add(box(0.34, 0.5, 0.34, col(0x3b3f4a), 0, 0.25, 0));
  mol.add(box(0.3, 0.3, 0.3, V.MAT.glass, 0, 0.65, 0));
  mol.add(box(0.24, 0.22, 0.24, col(0x5a3a22), 0, 0.6, 0));
  mol.add(box(0.1, 0.06, 0.04, glow(0x66ff88), 0, 0.3, 0.19));
  mol.position.set(6.1, 1.1, 0.6);
  g.add(mol);

  // jarra de café con base y vapor
  const jarra = new THREE.Group();
  jarra.add(box(0.28, 0.04, 0.28, col(0x2a2d34), 0, 0.02, 0));
  jarra.add(box(0.22, 0.26, 0.22, V.MAT.glass, 0, 0.17, 0));
  jarra.add(box(0.18, 0.15, 0.18, cafe, 0, 0.13, 0));
  jarra.add(box(0.04, 0.2, 0.04, col(0x2a2d34), 0.15, 0.17, 0));
  jarra.add(box(0.24, 0.04, 0.24, col(0x2a2d34), 0, 0.32, 0));
  jarra.position.set(8.9, 1.1, 0.7);
  g.add(jarra);
  vapor(8.9, 1.45, 0.7, 2);

  // tazas apiladas y platitos en la encimera
  for (let i = 0; i < 3; i++) g.add(taza(3.15, 1.1 + i * 0.12, 0.6, 0xf4efe4, false));
  g.add(taza(3.55, 1.1, 0.8, 0xe85a4f, false));
  g.add(box(0.22, 0.14, 0.18, col(0xd9a53a), 3.3, 1.17, 0.35)); // bote de azúcar/galletas
  g.add(taza(9.15, 1.1, 1.0, 0xf4efe4));

  // --- Pizarra del menú en la pared del fondo ---
  g.add(box(2.1, 1.0, 0.06, wood, 1.9, 1.2, -0.43));
  g.add(box(1.94, 0.84, 0.04, col(0x20302a), 1.9, 1.2, -0.4));
  const lineas = [['CAFE', 0xffe9a8, 1.45], ['ESPRESSO', 0xffffff, 1.28], ['LATTE', 0xffffff, 1.11], ['CORTADO', 0xffffff, 0.94]];
  lineas.forEach(([txt, c, y], i) => {
    const s = sign(txt, i === 0 ? 0.26 : 0.17, { color: '#' + c.toString(16).padStart(6, '0') });
    s.position.set(1.9, y + 0.1, -0.37);
    g.add(s);
  });

  // --- Sacos de granos y barrica junto a la barra ---
  const saco = col(0xc9a16a);
  g.add(box(0.5, 0.45, 0.4, saco, 1.4, 0.225, 0.3));
  g.add(box(0.5, 0.4, 0.4, col(0xb98f58), 1.95, 0.2, 0.3));
  g.add(box(0.46, 0.4, 0.36, saco, 1.65, 0.65, 0.3));
  g.add(box(0.2, 0.08, 0.02, col(0x5a3a22), 1.4, 0.3, 0.51));
  g.add(box(0.2, 0.08, 0.02, col(0x5a3a22), 1.95, 0.25, 0.51));

  // --- Taburetes de barra (asiento 0.8) ---
  function taburete(x, z) {
    g.add(box(0.4, 0.1, 0.4, col(0xb33a3a), x, 0.75, z));
    g.add(box(0.08, 0.7, 0.08, col(0x2a2d34), x, 0.35, z));
    g.add(box(0.36, 0.05, 0.36, col(0x2a2d34), x, 0.025, z));
  }
  for (const x of [4.6, 6.1, 7.6]) taburete(x, 2.0);

  // --- Mesas con sillas (asiento 0.5, mesa 0.88) ---
  function mesa(x, z) {
    g.add(box(1.2, 0.08, 1.2, planks, x, 0.84, z));
    g.add(box(0.14, 0.8, 0.14, wood, x, 0.4, z));
    g.add(box(0.7, 0.05, 0.7, wood, x, 0.025, z));
    g.add(taza(x - 0.25, 0.88, z - 0.2, 0xf4efe4));
    g.add(taza(x + 0.2, 0.88, z + 0.25, 0xe85a4f));
  }
  // silla mirando hacia dir (rotación Y): respaldo en el lado opuesto
  function silla(x, z, rotY) {
    const s = new THREE.Group();
    s.add(box(0.5, 0.08, 0.5, col(0x2f3b55), 0, 0.46, 0));
    s.add(box(0.5, 0.5, 0.07, col(0x2f3b55), 0, 0.75, -0.22));
    s.add(box(0.1, 0.42, 0.1, col(0x2a2d34), 0, 0.21, 0));
    s.position.set(x, 0, z); s.rotation.y = rotY;
    g.add(s);
  }
  mesa(3.8, 5.8);
  silla(2.85, 5.8, Math.PI / 2);
  silla(3.8, 4.85, 0);
  mesa(7.5, 4.8);
  silla(7.5, 3.85, 0);
  silla(6.55, 4.8, Math.PI / 2);

  // mesita redonda de esquina con una taza
  g.add(box(0.7, 0.07, 0.7, planks, 8.7, 0.84, 6.6));
  g.add(box(0.12, 0.8, 0.12, wood, 8.7, 0.4, 6.6));
  g.add(box(0.5, 0.05, 0.5, wood, 8.7, 0.025, 6.6));
  g.add(taza(8.7, 0.88, 6.6));

  // --- Plantas ---
  function planta(x, z, alto = 0.9) {
    g.add(box(0.5, 0.4, 0.5, V.MAT.pot, x, 0.2, z));
    g.add(box(0.6, alto * 0.5, 0.6, V.MAT.leaves, x, 0.4 + alto * 0.25, z));
    g.add(box(0.4, alto * 0.4, 0.4, V.MAT.leaves, x, 0.4 + alto * 0.7, z));
  }
  planta(0.1, 0.1);
  planta(0.1, 7.0, 0.7);
  planta(9.1, 7.0, 1.0);

  // --- Lámparas colgantes sobre las mesas ---
  function lampara(x, z) {
    g.add(box(0.03, 0.5, 0.03, col(0x2a2d34), x, 2.45, z));
    g.add(box(0.4, 0.14, 0.4, col(0xd96a3a), x, 2.13, z));
    g.add(box(0.24, 0.05, 0.24, glow(0xffe9a8), x, 2.04, z));
  }
  lampara(3.8, 5.8);
  lampara(7.5, 4.8);

  // --- Sitios ---
  g.userData.spots = [
    { x: 2.85, z: 5.8, y: 0.5, rotY: Math.PI / 2, pose: 'sit', activity: 'coffee' },
    { x: 3.8, z: 4.85, y: 0.5, rotY: 0, pose: 'sit', activity: 'coffee' },
    { x: 7.5, z: 3.85, y: 0.5, rotY: 0, pose: 'sit', activity: 'coffee' },
    { x: 6.55, z: 4.8, y: 0.5, rotY: Math.PI / 2, pose: 'sit', activity: 'eat' },
    { x: 4.6, z: 2.0, y: 0.8, rotY: Math.PI, pose: 'sit', activity: 'coffee' },
    { x: 6.1, z: 2.0, y: 0.8, rotY: Math.PI, pose: 'sit', activity: 'coffee' },
    { x: 7.6, z: 2.0, y: 0.8, rotY: Math.PI, pose: 'sit', activity: 'chat' },
    { x: 9.0, z: 2.0, y: 0, rotY: Math.PI, pose: 'stand', activity: 'coffee' },
  ];

  // --- Animación del vapor ---
  g.userData.tick = (dt, t) => {
    for (const v of vapores) {
      const p = (t * v.vel + v.fase) % 1;
      v.m.position.set(v.x + v.ox + Math.sin(t * 2 + v.fase * 6) * 0.03, v.y + p * 0.7, v.z);
      const s = 0.11 + p * 0.12;
      v.m.scale.set(s, s, s);
      v.m.material.opacity = 0.6 * Math.sin(Math.PI * p);
      v.m.rotation.y = t + v.fase * 5;
    }
  };

  return g;
}
