// Sala de descanso de la oficina.
// Un sofá grande contra la pared del fondo, dos pufs alrededor de una alfombra
// redonda con mesita baja, un sillón de lectura junto a la estantería, lámpara
// de pie y varias plantas. La puerta queda en la pared -x (celdas z=2 y z=3).
export const meta = {
  id: 'descanso',
  title: 'Descanso',
  size: [8, 6],
  floor: 'carpet',
  floorColor: '#6b8f5a',
};

export default function build(V, opts = {}) {
  const { THREE } = V;
  const g = new THREE.Group();
  const rand = V.rng(0x0d35c0); // pequeñas variaciones deterministas

  // ---------------------------------------------------------------------------
  // Paleta de la sala (tonos cálidos sobre la moqueta verde)
  // ---------------------------------------------------------------------------
  const C = {
    sofa: '#4c6e7b',
    sofaDark: '#3b5663',
    coral: '#c96b58',
    mustard: '#d6a544',
    cream: '#e8dfc8',
    rust: '#b26a4a',
    rug: '#d9c092',
    rugEdge: '#b27351',
    wood: '#3b2c20',
    chair: '#8a5a44',
  };
  const mSofa = V.col(C.sofa);
  const mSofaDark = V.col(C.sofaDark);
  const mCoral = V.col(C.coral);
  const mMustard = V.col(C.mustard);
  const mCream = V.col(C.cream);

  // ---------------------------------------------------------------------------
  // Sofá grande contra la pared del fondo (z ≈ 0)
  // Ocupa x 2.1..6.7; el asiento queda a y = 0.40, como piden los sitios.
  // ---------------------------------------------------------------------------
  const sofaX = 4.4;
  g.add(V.box(4.3, 0.28, 0.86, mSofa, sofaX, 0.14, 0.68)); // base
  g.add(V.box(4.7, 0.8, 0.22, mSofaDark, sofaX, 0.68, 0.12)); // respaldo
  g.add(V.box(4.7, 0.1, 0.26, mSofa, sofaX, 1.12, 0.12)); // remate del respaldo
  for (const x of [2.2, 6.6]) {
    g.add(V.box(0.22, 0.55, 1.0, mSofaDark, x, 0.29, 0.62)); // reposabrazos
    g.add(V.box(0.26, 0.08, 1.04, mSofa, x, 0.59, 0.62)); // remate del brazo
  }
  // Tres cojines de asiento, uno por sitio.
  const seatCols = [V.col('#628a98'), V.col('#5d8493'), V.col('#6b93a0')];
  for (let i = 0; i < 3; i++) {
    g.add(V.box(1.34, 0.12, 0.8, seatCols[i], 3.0 + i * 1.4, 0.34, 0.7));
  }
  // Cojines decorativos apoyados en el respaldo.
  const pillows = [
    [3.3, C.coral], [4.4, C.mustard], [5.5, C.cream],
  ];
  for (const [x, color] of pillows) {
    g.add(V.box(0.62, 0.46, 0.17, V.col(color), x, 0.65, 0.31));
  }
  // Manta doblada sobre el brazo derecho.
  g.add(V.box(0.3, 0.07, 0.72, V.col(C.rust), 6.6, 0.66, 0.58));
  g.add(V.box(0.07, 0.36, 0.7, V.col(C.rust), 6.74, 0.46, 0.58));

  // Dos cuadros pixel-art sobre el sofá (la pared del fondo mide 2 de alto).
  const arteAtardecer = (ctx, r) => {
    for (let y = 0; y < 16; y++) {
      const base = y < 6 ? '#7d9fb4' : y < 10 ? '#d9a07a' : '#e8c88a';
      for (let x = 0; x < 16; x++) V.px(ctx, x, y, V.shade(base, 1 + (r() - 0.5) * 0.09));
    }
    ctx.fillStyle = '#ffe08a'; ctx.fillRect(9, 6, 4, 4); // sol
    for (let x = 0; x < 16; x++) { // montañas
      const h = 3 + Math.floor(r() * 4);
      ctx.fillStyle = x % 5 === 0 ? '#4b5d6d' : '#556a78';
      ctx.fillRect(x, 16 - h, 1, h);
    }
    ctx.fillStyle = '#6f7f5c'; ctx.fillRect(0, 14, 16, 2);
  };
  const arteAbstracto = (ctx, r) => {
    V.noiseFill(ctx, r, 16, 16, '#324a52', 0.06);
    const cols = ['#c96b58', '#d6a544', '#e8dfc8', '#7fa3a8'];
    for (let i = 0; i < 8; i++) {
      ctx.fillStyle = cols[i % cols.length];
      ctx.fillRect(Math.floor(r() * 11), Math.floor(r() * 11), 2 + Math.floor(r() * 5), 2 + Math.floor(r() * 5));
    }
    ctx.fillStyle = '#e8dfc8'; ctx.fillRect(2, 2, 3, 12);
  };
  const cuadro = (x, paint, seed) => {
    const c = new THREE.Group();
    c.position.set(x, 1.55, -0.46);
    c.add(V.box(0.92, 0.72, 0.05, V.MAT.darkwood, 0, 0, 0));
    c.add(V.box(0.78, 0.58, 0.04, V.lam(V.pixelTex(16, 16, paint, seed)), 0, 0, 0.03));
    for (const [w, h, ox, oy] of [[0.92, 0.08, 0, 0.32], [0.92, 0.08, 0, -0.32], [0.08, 0.72, -0.42, 0], [0.08, 0.72, 0.42, 0]]) {
      c.add(V.box(w, h, 0.06, V.MAT.darkwood, ox, oy, 0.045));
    }
    return c;
  };
  g.add(cuadro(3.2, arteAtardecer, 41));
  g.add(cuadro(5.4, arteAbstracto, 42));

  // ---------------------------------------------------------------------------
  // Alfombra redonda hecha de bloques, con mesita baja en el centro.
  // ---------------------------------------------------------------------------
  const RUG = { x: 3.7, z: 2.9, r: 1.6 };
  const rugCentro = [], rugBorde = [];
  for (let dz = -1.5; dz <= 1.5; dz += 0.5) {
    for (let dx = -1.5; dx <= 1.5; dx += 0.5) {
      const d = Math.hypot(dx, dz);
      if (d > RUG.r) continue;
      (d > 1.12 ? rugBorde : rugCentro).push([RUG.x + dx, 0.035, RUG.z + dz, 0.5, 0.07, 0.5]);
    }
  }
  g.add(V.instCubes(rugBorde, V.col(C.rugEdge)));
  g.add(V.instCubes(rugCentro, V.col(C.rug)));

  // Mesita baja de madera oscura.
  const TX = RUG.x, TZ = RUG.z;
  g.add(V.box(1.1, 0.12, 1.1, V.MAT.darkwood, TX, 0.5, TZ));
  for (const sx of [-0.42, 0.42]) for (const sz of [-0.42, 0.42]) {
    g.add(V.box(0.1, 0.44, 0.1, V.MAT.darkwood, TX + sx, 0.22, TZ + sz));
  }
  // Bandeja y taza.
  g.add(V.box(0.56, 0.03, 0.36, V.col('#c9b184'), TX - 0.18, 0.575, TZ - 0.2));
  g.add(V.box(0.13, 0.15, 0.13, mCream, TX - 0.18, 0.665, TZ - 0.2));
  g.add(V.box(0.05, 0.06, 0.03, mCream, TX - 0.09, 0.66, TZ - 0.2));
  // Un par de libros (la textura de V.MAT.shelf se ve desde +z).
  g.add(V.box(0.36, 0.08, 0.27, V.MAT.shelf, TX + 0.25, 0.6, TZ + 0.2));
  // Plantita sobre la mesa.
  const plantaMesa = (() => {
    const p = new THREE.Group();
    p.position.set(TX + 0.26, 0.56, TZ + 0.18);
    p.scale.setScalar(0.55);
    p.add(V.box(0.42, 0.36, 0.42, V.MAT.pot, 0, 0.18, 0));
    p.add(V.box(0.48, 0.07, 0.48, V.MAT.pot, 0, 0.38, 0));
    p.add(V.box(0.48, 0.4, 0.48, V.MAT.leaves, 0, 0.62, 0));
    p.add(V.box(0.28, 0.3, 0.28, V.MAT.leaves, 0.08, 0.9, 0.04));
    return p;
  })();

  // ---------------------------------------------------------------------------
  // Dos pufs, uno a cada lado de la alfombra, mirando hacia la mesita.
  // ---------------------------------------------------------------------------
  const puf = (x, z, color) => {
    const p = new THREE.Group();
    p.add(V.box(0.72, 0.28, 0.72, V.col(V.shade(color, 0.8)), x, 0.14, z));
    p.add(V.box(0.84, 0.2, 0.84, V.col(color), x, 0.38, z));
    p.add(V.box(0.86, 0.05, 0.86, V.col(V.shade(color, 0.72)), x, 0.295, z));
    p.add(V.box(0.12, 0.04, 0.12, V.col(V.shade(color, 0.68)), x, 0.5, z));
    return p;
  };
  g.add(puf(2.0, 3.35, '#c9a24a'));
  g.add(puf(5.3, 4.5, '#b26a4a'));

  // ---------------------------------------------------------------------------
  // Sillón de lectura junto a la estantería de la pared +x.
  // Mira hacia -x (rotY = -PI/2 en su sitio).
  // ---------------------------------------------------------------------------
  const chairX = 6.4, chairZ = 1.7;
  g.add(V.box(0.9, 0.3, 1.0, V.col(C.chair), chairX, 0.15, chairZ)); // base
  g.add(V.box(0.72, 0.15, 0.8, mCream, chairX - 0.02, 0.375, chairZ)); // asiento
  g.add(V.box(0.22, 0.75, 1.0, V.col(C.chair), chairX + 0.39, 0.68, chairZ)); // respaldo
  for (const z of [chairZ - 0.45, chairZ + 0.45]) {
    g.add(V.box(0.9, 0.2, 0.18, V.col(V.shade(C.chair, 0.85)), chairX, 0.55, z)); // brazos
  }
  g.add(V.box(0.13, 0.4, 0.52, mCoral, chairX + 0.35, 0.78, chairZ)); // cojín
  g.add(V.box(0.12, 0.12, 0.12, V.col('#2e3b3f'), chairX - 0.42, 0.05, chairZ)); // pata visible

  // ---------------------------------------------------------------------------
  // Estantería baja contra la pared +x, con libros.
  // ---------------------------------------------------------------------------
  const SHX = 7.2, SHZ = 1.45; // centro de la estantería
  g.add(V.box(0.1, 1.12, 2.2, V.col(C.wood), 7.4, 0.56, SHZ)); // trasera
  g.add(V.box(0.56, 1.14, 0.09, V.MAT.darkwood, SHX, 0.57, 0.36)); // lateral
  // El lateral que mira a cámara (+z) lleva la textura de libros de V.MAT.shelf.
  g.add(V.box(0.56, 1.14, 0.09, V.MAT.shelf, SHX, 0.57, 2.54));
  for (const y of [0.08, 0.6, 1.2]) {
    g.add(V.box(0.58, 0.07, 2.24, V.MAT.darkwood, SHX, y, SHZ)); // baldas
  }
  // Libros de colores en las dos baldas (varían de ancho y alto con `rand`).
  const lomos = ['#b23a3a', '#3a6bb2', '#3aa25a', '#d9a53a', '#7a3ab2', '#e0e0e0', '#c96b58', '#4c6e7b'];
  for (const baseY of [0.115, 0.635]) {
    let z = 0.47;
    while (z < 2.4) {
      if (rand() < 0.12) { z += 0.12 + rand() * 0.1; continue; } // hueco
      const w = 0.07 + rand() * 0.08;
      const h = 0.24 + rand() * 0.11;
      g.add(V.box(0.24, h, w, V.col(V.pick(lomos, rand)), 7.13, baseY + h / 2, z + w / 2));
      z += w + 0.018;
    }
  }
  // Pilas de libros tumbadas dentro de la balda central.
  for (let i = 0; i < 3; i++) {
    g.add(V.box(0.24, 0.05, 0.32, V.col(V.pick(lomos, rand)), 7.13, 0.65 + i * 0.055, 1.05));
    g.add(V.box(0.24, 0.05, 0.3, V.col(V.pick(lomos, rand)), 7.13, 0.65 + i * 0.055, 1.95));
  }
  // Libros y detalles encima de la estantería (visibles desde la cámara).
  for (let i = 0; i < 3; i++) {
    g.add(V.box(0.34, 0.06, 0.42, V.col(V.pick(lomos, rand)), 7.14, 1.27 + i * 0.065, 0.8));
  }
  g.add(V.box(0.3, 0.07, 0.36, V.MAT.shelf, 7.14, 1.28, 1.5));
  g.add(V.box(0.3, 0.07, 0.36, V.col(C.mustard), 7.14, 1.35, 1.52));
  g.add(V.box(0.28, 0.26, 0.28, V.col(C.cream), 7.14, 1.38, 2.2)); // caja decorativa

  // ---------------------------------------------------------------------------
  // Lámpara de pie (su luz parpadea muy suavemente en el tick).
  // ---------------------------------------------------------------------------
  const lampX = 1.6, lampZ = 0.8;
  g.add(V.box(0.36, 0.08, 0.36, V.MAT.metal, lampX, 0.04, lampZ));
  g.add(V.box(0.07, 1.44, 0.07, V.MAT.metal, lampX, 0.78, lampZ));
  g.add(V.box(0.2, 0.06, 0.2, V.MAT.metal, lampX, 1.5, lampZ));
  const lampMat = V.glow(0xffe9a8);
  g.add(V.box(0.46, 0.34, 0.46, lampMat, lampX, 1.68, lampZ));
  g.add(V.box(0.52, 0.05, 0.52, V.col('#d8b46a'), lampX, 1.86, lampZ));
  // Disco cálido en el suelo, como un charco de luz.
  const halo = V.box(0.9, 0.012, 0.9, new THREE.MeshBasicMaterial({
    color: 0xffd98a, transparent: true, opacity: 0.13, depthWrite: false,
  }), lampX, 0.045, lampZ + 0.15);
  halo.castShadow = false; halo.receiveShadow = false;
  g.add(halo);

  // ---------------------------------------------------------------------------
  // Plantas: una en la esquina del fondo, otra en la esquina delantera y la
  // pequeña de la mesa. La de delante se balancea en el tick.
  // ---------------------------------------------------------------------------
  const planta = (x, z, s, conBalanceo = false) => {
    const p = new THREE.Group();
    p.position.set(x, 0, z);
    p.scale.setScalar(s);
    p.add(V.box(0.42, 0.36, 0.42, V.MAT.pot, 0, 0.18, 0));
    p.add(V.box(0.48, 0.07, 0.48, V.MAT.pot, 0, 0.38, 0));
    const hojas = new THREE.Group();
    hojas.position.y = 0.4;
    hojas.add(V.box(0.54, 0.42, 0.54, V.MAT.leaves, 0, 0.28, 0));
    hojas.add(V.box(0.34, 0.34, 0.34, V.MAT.leaves, 0.18, 0.58, 0.04));
    hojas.add(V.box(0.3, 0.3, 0.3, V.MAT.leaves, -0.16, 0.55, -0.08));
    hojas.add(V.box(0.22, 0.26, 0.22, V.MAT.leaves, 0.02, 0.78, 0.12));
    p.add(hojas);
    if (conBalanceo) p.userData.hojas = hojas;
    return p;
  };
  g.add(planta(0.75, 0.55, 1.25));
  const plantaDelantera = planta(7.0, 4.9, 1.35, true);
  g.add(plantaDelantera);
  g.add(plantaMesa);

  // ---------------------------------------------------------------------------
  // Sitios (6): 3 en el sofá, 2 en los pufs y 1 de lectura en el sillón.
  // ---------------------------------------------------------------------------
  g.userData.spots = [
    { x: 3.05, z: 0.72, y: 0.4, rotY: 0, pose: 'sit', activity: 'chat' },
    { x: 4.4, z: 0.72, y: 0.4, rotY: 0, pose: 'sit', activity: 'rest' },
    { x: 5.75, z: 0.72, y: 0.4, rotY: 0, pose: 'sit', activity: 'chat' },
    { x: 2.0, z: 3.35, y: 0.45, rotY: 1.83, pose: 'sit', activity: 'chat' },
    { x: 5.3, z: 4.5, y: 0.45, rotY: -2.36, pose: 'sit', activity: 'chat' },
    { x: 6.35, z: 1.7, y: 0.45, rotY: -Math.PI / 2, pose: 'sit', activity: 'read' },
  ];

  // ---------------------------------------------------------------------------
  // Animación barata: parpadeo cálido de la lámpara y balanceo de una planta.
  // ---------------------------------------------------------------------------
  const lampA = new THREE.Color(0xffe9a8);
  const lampB = new THREE.Color(0xffcf7a);
  const hojas = plantaDelantera.userData.hojas;
  g.userData.tick = (dt, t) => {
    const k = 0.5 + 0.5 * Math.sin(t * 3.1 + 0.7) * Math.sin(t * 7.7);
    lampMat.color.copy(lampA).lerp(lampB, 0.12 + 0.3 * k);
    hojas.rotation.z = Math.sin(t * 1.15) * 0.035;
    hojas.rotation.x = Math.cos(t * 0.8) * 0.02;
  };

  return g;
}
