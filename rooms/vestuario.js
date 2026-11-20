// Vestuario: los agentes se cambian aquí.
// Fondo: fila de cinco taquillas (dos abiertas, con una camiseta colgada dentro) y, a la derecha,
// un espejo de cuerpo entero con su alfombrilla delante. Centro: banco de madera largo.
// Pared +x (baja): perchero con camisetas, que una de ellas se balancea de vez en cuando.
// Esquina del fondo derecha: estantería baja con gorras. La puerta queda en -x (z = 2 y 3).
export const meta = {
  id: 'vestuario',
  title: 'Vestuario',
  size: [8, 6],
  floor: 'checker',
};

// Medidas de las taquillas. Cada una ocupa de z = -0.5 (pared del fondo) a z = 0.1 (cara frontal).
const TQ_W = 0.76, TQ_H = 1.9, TQ_D = 0.6;
const TQ_Z = -0.2;   // centro en z del cuerpo
const TQ_FRONT = 0.1; // cara frontal del cuerpo

// Taquilla metálica. Si `abierta`, la puerta es un pivote que gira sobre la bisagra de la izquierda
// y se deja abierta hacia la sala, con una camiseta colgada en el hueco.
// Las rejillas no van a `g` sino a la lista compartida `rejillas`, que se convierte en un único InstancedMesh.
function taquilla(V, g, rejillas, x, color, abierta, camisa) {
  const { THREE } = V;
  g.add(V.box(TQ_W, TQ_H, TQ_D, V.col(color), x, TQ_H / 2, TQ_Z));
  const puertaMat = V.col(V.shade(color, 1.12));

  // Tres franjas oscuras arriba. Cerrada, van sobre la puerta; abierta, sobre el cuerpo.
  const zRej = abierta ? TQ_FRONT + 0.005 : TQ_FRONT + 0.035;
  for (const y of [1.62, 1.68, 1.74]) rejillas.push([x, y, zRej, TQ_W - 0.3, 0.025, 0.01]);

  if (!abierta) {
    // Puerta cerrada y tirador pegado al borde derecho.
    g.add(V.box(TQ_W - 0.08, TQ_H - 0.2, 0.03, puertaMat, x, TQ_H / 2, TQ_FRONT + 0.015));
    g.add(V.box(0.05, 0.2, 0.04, V.col(0xd0d4da), x + TQ_W / 2 - 0.12, TQ_H / 2, TQ_FRONT + 0.05));
    return null;
  }

  // Hueco oscuro de la taquilla abierta, algo por delante del cuerpo.
  g.add(V.box(TQ_W - 0.16, 1.5, 0.02, V.MAT.dark, x, 0.8, TQ_FRONT + 0.01));

  // Camiseta colgada dentro: torso y mangas, un poco por delante del hueco.
  const cam = V.col(camisa);
  g.add(V.box(0.3, 0.4, 0.03, cam, x + 0.04, 1.42, 0.14));
  g.add(V.box(0.5, 0.12, 0.03, cam, x + 0.04, 1.6, 0.14));

  // Puerta abierta: el pivote está en la bisagra (borde izquierdo) y la hoja va hacia +x.
  // La rotación de -1.2 rad (sobre Y) hace que la puerta se abra hacia la sala, hacia +z.
  const pivote = new THREE.Group();
  pivote.position.set(x - TQ_W / 2 + 0.04, TQ_H / 2, TQ_FRONT);
  const hoja = TQ_W - 0.08;
  const panel = V.box(hoja, TQ_H - 0.2, 0.03, puertaMat, hoja / 2, 0, 0.015);
  const tirador = V.box(0.05, 0.2, 0.04, V.col(0xd0d4da), hoja - 0.1, 0, 0.05);
  pivote.add(panel, tirador);
  pivote.rotation.y = -1.2;
  g.add(pivote);
  return pivote;
}

// Espejo de cuerpo entero contra el fondo: marco de madera y cristal azul muy claro con dos reflejos diagonales.
// Va en z ≈ 0 y su parte más alta queda por debajo de y = 2 (la pared del fondo).
function espejo(V, g, cx) {
  const { THREE } = V;
  // Marco: z de -0.48 a -0.40.
  g.add(V.box(1.3, 1.9, 0.08, V.MAT.darkwood, cx, 1.0, -0.44));
  // Cristal: un plano azul muy claro que mira hacia +z.
  const cristal = new THREE.Mesh(new THREE.PlaneGeometry(1.1, 1.7), V.glow('#cfe6ff'));
  cristal.position.set(cx, 1.0, -0.39);
  g.add(cristal);
  // Dos reflejos diagonales, algo más claros que el cristal y delante de él.
  const raya = (x, y) => { const m = V.box(0.07, 0.9, 0.01, V.glow('#ffffff'), x, y, -0.375); m.rotation.z = 0.8; g.add(m); };
  raya(cx - 0.22, 1.1);
  raya(cx + 0.18, 0.55);
}

// Alfombrilla delante del espejo, muy fina para que los pies no la atraviesen.
function alfombrilla(V, g, cx, cz) {
  g.add(V.box(2.0, 0.02, 1.1, V.col('#a33b5e'), cx, 0.01, cz));
}

// Banco largo de madera: asiento con la superficie a y = 0.45 y cuatro patas en las esquinas.
// Centrado en x = 3.5, z = 2.95 y con 0.7 de fondo, para que la cadera de los sentados quede en el asiento.
function banco(V, g) {
  const cx = 3.5, cz = 2.95;
  g.add(V.box(3.0, 0.08, 0.7, V.MAT.planks, cx, 0.41, cz));       // asiento (0.37 a 0.45)
  g.add(V.box(2.8, 0.05, 0.5, V.MAT.darkwood, cx, 0.15, cz));     // travesaño bajo el asiento
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
    g.add(V.box(0.1, 0.37, 0.1, V.MAT.darkwood, cx + sx * 1.35, 0.185, cz + sz * 0.3));
  }
}

// Perchero junto a la pared +x (x = 7). Pie de cruz, columna, barra a y = 1.7 y 5 camisetas planas que cuelgan de ella.
// Devuelve la camiseta del medio, que es la que se balancea.
function perchero(V, g) {
  const { THREE } = V;
  const x = 7.0, z = 4.0;
  g.add(V.box(0.9, 0.04, 0.08, V.MAT.metal, x, 0.02, z));
  g.add(V.box(0.08, 0.04, 0.9, V.MAT.metal, x, 0.02, z));
  g.add(V.box(0.05, 1.72, 0.05, V.MAT.metal, x, 0.86, z));
  g.add(V.box(0.06, 0.06, 1.6, V.MAT.metal, x, 1.72, z));

  const colores = ['#e05d5d', '#5dade0', '#f2c94c', '#6fcf97', '#bb6bd9'];
  let balanceada = null;
  colores.forEach((c, i) => {
    const pivote = new THREE.Group();
    pivote.position.set(x, 1.66, 3.4 + i * 0.3);       // punto de colgado, justo bajo la barra
    const camiseta = V.box(0.06, 0.55, 0.22, V.col(c), 0, -0.275, 0);
    pivote.add(camiseta);
    g.add(pivote);
    if (i === 2) balanceada = pivote;
  });
  return balanceada;
}

// Estantería baja de madera oscura con gorras y sombreros de colores en tres baldas.
// Va en la esquina del fondo derecha, junto al espejo, y mide 1 de alto.
function estanteria(V, g) {
  const cx = 7.0, cz = -0.2;
  g.add(V.box(0.04, 1.0, 0.5, V.MAT.darkwood, cx - 0.45, 0.5, cz));
  g.add(V.box(0.04, 1.0, 0.5, V.MAT.darkwood, cx + 0.45, 0.5, cz));
  g.add(V.box(0.9, 1.0, 0.04, V.MAT.darkwood, cx, 0.5, -0.47));
  // Baldas: centro en y, con la superficie 0.04 por encima.
  for (const y of [0.02, 0.34, 0.66, 0.98]) g.add(V.box(0.9, 0.04, 0.5, V.MAT.darkwood, cx, y, cz));

  // Sombreros: en cada balda, dos gorras (corona y ala) de colores distintos.
  const gorras = [
    ['#c44b4b', '#f2c94c'], ['#3aa25a', '#2f80ed'], ['#9b51e0', '#f2994a'],
  ];
  gorras.forEach(([a, b], nivel) => {
    const top = [0.04, 0.36, 0.68][nivel];
    [[cx - 0.14, a], [cx + 0.14, b]].forEach(([hx, c]) => {
      g.add(V.box(0.28, 0.03, 0.28, V.col(c), hx, top + 0.015, cz));      // ala
      g.add(V.box(0.18, 0.12, 0.18, V.col(c), hx, top + 0.075, cz));      // corona
    });
  });
}

export default function build(V) {
  const { THREE } = V;
  const g = new THREE.Group();

  // Taquillas: cinco en la pared del fondo, a partir de x = 0. Las de x = 0.8 y 2.4 están abiertas.
  const rejillas = [];
  const taquillas = [
    { x: 0.0, color: '#c44b4b' },
    { x: 0.8, color: '#4b7bc4', abierta: true, camisa: '#f2c94c' },
    { x: 1.6, color: '#4bb07a' },
    { x: 2.4, color: '#d9a53a', abierta: true, camisa: '#6fcf97' },
    { x: 3.2, color: '#8a5bc4' },
  ];
  for (const t of taquillas) taquilla(V, g, rejillas, t.x, t.color, !!t.abierta, t.camisa);
  g.add(V.instCubes(rejillas, V.MAT.dark));

  banco(V, g);
  espejo(V, g, 5.8);
  alfombrilla(V, g, 5.8, 1.4);
  const camisetaBalanceada = perchero(V, g);
  estanteria(V, g);

  // Sitios: dos de pie frente al espejo (miran a -z), uno de pie frente al perchero (mira a +x) y tres sentados en el banco (miran a +z).
  // La cadera de los sentados queda en z = 3.09 para que las espinillas no entren en el frente del asiento.
  g.userData.spots = [
    { x: 5.2, z: 1.4, y: 0, rotY: Math.PI, pose: 'stand', activity: 'dress' },
    { x: 6.4, z: 1.4, y: 0, rotY: Math.PI, pose: 'stand', activity: 'dress' },
    { x: 5.9, z: 4.0, y: 0, rotY: Math.PI / 2, pose: 'stand', activity: 'dress' },
    { x: 2.6, z: 3.09, y: 0.45, rotY: 0, pose: 'sit', activity: 'chat' },
    { x: 3.5, z: 3.09, y: 0.45, rotY: 0, pose: 'sit', activity: 'chat' },
    { x: 4.4, z: 3.09, y: 0.45, rotY: 0, pose: 'sit', activity: 'chat' },
  ];

  // Cada cierto tiempo, la camiseta del perchero se balancea y se para poco a poco, como si alguien la acabara de tocar.
  // Es barato: solo cambia la rotación de un pivote.
  g.userData.tick = (dt, t) => {
    const k = t % 6;                                  // un toque cada 6 segundos
    const a = 0.2 * Math.exp(-1.4 * k) * Math.sin(9 * k);
    camisetaBalanceada.rotation.z = a;
  };
  return g;
}
