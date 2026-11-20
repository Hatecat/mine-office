// Sala de reuniones: el mismo módulo con dos variantes.
// A: mesa larga de madera oscura con 6 sillas, pizarra blanca con un diagrama y una planta.
// B: mesa pequeña con 4 sillas y una pantalla grande con gráfica de barras que se mueve en `tick`.
export const meta = {
  id: 'reuniones',
  title: 'Reuniones',
  size: [8, 5],
  floor: 'carpet',
  floorColor: '#4a5a78',
};

// Mesa: tablero con la superficie a y = 0.9 y cuatro patas en las esquinas.
// Las patas están en las esquinas, así que las piernas de las sillas pasan por debajo del tablero sin chocar.
function mesa(V, g, cx, cz, len, dep) {
  g.add(V.box(len, 0.1, dep, V.MAT.darkwood, cx, 0.85, cz));
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
    g.add(V.box(0.1, 0.8, 0.1, V.MAT.darkwood, cx + sx * (len / 2 - 0.15), 0.4, cz + sz * (dep / 2 - 0.15)));
  }
}

// Silla: asiento con la superficie a y = 0.5 (la altura que usa el spot).
// `mira` es +1 si la silla mira a +z y -1 si mira a -z. El respaldo va detrás de la cadera,
// es decir, en sentido contrario a la mirada.
function silla(V, g, x, z, mira) {
  g.add(V.box(0.6, 0.1, 0.55, V.MAT.chair, x, 0.45, z));
  g.add(V.box(0.6, 0.75, 0.08, V.MAT.chair, x, 0.875, z - mira * 0.32));
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
    g.add(V.box(0.06, 0.45, 0.06, V.MAT.dark, x + sx * 0.25, 0.225, z + sz * 0.2));
  }
}

// Pizarra blanca en la pared del fondo (z ≈ -0.4), con un diagrama de cajas y flechas en colores.
function pizarra(V, g) {
  const T = V.THREE;
  // Marco metálico detrás de la tabla, que queda entre y = 0.9 y y = 1.9.
  g.add(V.box(4.1, 1.0, 0.08, V.MAT.metal, 3.5, 1.4, -0.42));

  // Dibujo en un canvas 416×96 (la misma proporción que la tabla, 3.9 × 0.9).
  const c = document.createElement('canvas');
  c.width = 416; c.height = 96;
  const x = c.getContext('2d');
  x.fillStyle = '#f5f7fa';
  x.fillRect(0, 0, c.width, c.height);
  // Caja con contorno de color y dos líneas de "texto" dentro.
  const caja = (px, py, w, h, color) => {
    x.strokeStyle = color; x.lineWidth = 5;
    x.strokeRect(px + 2.5, py + 2.5, w - 5, h - 5);
    x.fillStyle = color;
    x.fillRect(px + 12, py + 12, w - 24, 6);
    x.fillRect(px + 12, py + h - 18, (w - 24) * 0.6, 6);
  };
  const linea = (x1, y1, x2, y2) => {
    x.strokeStyle = '#2c2f38'; x.lineWidth = 4;
    x.beginPath(); x.moveTo(x1, y1); x.lineTo(x2, y2); x.stroke();
  };
  x.fillStyle = '#2c2f38';
  x.fillRect(30, 8, 120, 8);            // título
  caja(30, 28, 90, 40, '#3a6bb2');      // entrada
  caja(160, 8, 100, 34, '#3aa25a');     // proceso A
  caja(160, 54, 100, 34, '#d9a53a');    // proceso B
  caja(300, 28, 90, 40, '#b23a3a');     // salida
  linea(120, 48, 160, 25);
  linea(120, 48, 160, 71);
  linea(260, 25, 300, 48);
  linea(260, 71, 300, 48);

  const tex = new T.CanvasTexture(c);
  tex.magFilter = tex.minFilter = T.NearestFilter;
  tex.generateMipmaps = false;
  tex.colorSpace = T.SRGBColorSpace;
  const tabla = new T.Mesh(new T.PlaneGeometry(3.9, 0.9), V.lam(tex));
  tabla.position.set(3.5, 1.4, -0.37);
  g.add(tabla);
}

// Pantalla en el fondo con una gráfica de barras brillantes. Devuelve la función que cambia la altura de una barra.
function pantalla(V, g) {
  const base = 0.65;                                                    // línea de base de las barras
  g.add(V.box(4.8, 1.5, 0.1, V.MAT.dark, 3.5, 1.2, -0.4));              // marco negro
  g.add(V.box(4.4, 1.3, 0.04, V.glow('#16233b'), 3.5, 1.2, -0.34));    // fondo azul oscuro
  g.add(V.box(4.0, 0.03, 0.03, V.glow('#8fa6c8'), 3.5, base, -0.31));  // eje horizontal

  const colores = ['#3aa25a', '#3a6bb2', '#d9a53a', '#b23a3a', '#7a3ab2'];
  const alturas = [0.45, 0.7, 0.55, 0.85, 0.6];
  // Cada barra es un cubo de alto 1 escalado en y, así que su altura real es scale.y.
  const barras = colores.map((color, i) => {
    const b = V.box(0.42, 1, 0.04, V.glow(color), 3.5 + (i - 2) * 0.7, base + alturas[i] / 2, -0.31);
    b.scale.y = alturas[i];
    g.add(b);
    return b;
  });
  // Cambia la altura de una barra manteniendo su base sobre la línea de base.
  return (i, h) => {
    barras[i].scale.y = h;
    barras[i].position.y = base + h / 2;
  };
}

// Planta en la esquina del fondo derecha (+x, -z).
function planta(V, g, x, z) {
  g.add(V.box(0.6, 0.5, 0.6, V.MAT.pot, x, 0.25, z));
  g.add(V.box(0.9, 0.8, 0.9, V.MAT.leaves, x, 0.9, z));
  g.add(V.box(0.6, 0.5, 0.6, V.MAT.leaves, x, 1.45, z));
}

export default function build(V, opts = {}) {
  const { THREE } = V;
  const g = new THREE.Group();
  const esB = opts.variant === 'B';

  // Mesa centrada en x = 3.5, z = 2.0. La variante B es más pequeña.
  const tx = 3.5, tz = 2.0;
  const len = esB ? 2.2 : 3.0;
  const dep = esB ? 0.9 : 1.0;
  const xs = esB ? [3.0, 4.0] : [2.5, 3.5, 4.5];   // columnas de sillas (de a dos o de a tres por lado)
  mesa(V, g, tx, tz, len, dep);

  // Una fila de sillas a cada lado de la mesa (lados -z y +z). La cadera queda 0.3 fuera del borde.
  const zNear = tz - dep / 2 - 0.3;   // lado -z: mira a +z (rotY = 0)
  const zFar = tz + dep / 2 + 0.3;    // lado +z: mira a -z (rotY = PI)
  const spots = [];
  for (const x of xs) {
    silla(V, g, x, zNear, +1);
    spots.push({ x, z: zNear, y: 0.5, rotY: 0, pose: 'sit', activity: 'meeting' });
    silla(V, g, x, zFar, -1);
    spots.push({ x, z: zFar, y: 0.5, rotY: Math.PI, pose: 'sit', activity: 'meeting' });
  }

  if (esB) {
    const setAltura = pantalla(V, g);
    // Barra 2 oscila suavemente entre 0.15 y 0.85 de alto.
    g.userData.tick = (dt, t) => setAltura(2, 0.5 + 0.35 * Math.sin(t * 0.8));
  } else {
    pizarra(V, g);
  }

  planta(V, g, 6.5, 0.5);

  g.userData.spots = spots;
  return g;
}
