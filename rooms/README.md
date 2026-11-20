# Salas de la oficina: cómo hacer una

Cada sala es un módulo ES en `rooms/<id>.js`. Solo pones los **muebles y la decoración**. El suelo, las paredes, la puerta y la colocación en el plano los hace la oficina.

```js
export const meta = {
  id: 'cafeteria',            // igual que el nombre del archivo
  title: 'Cafetería',         // cartel encima de la puerta
  size: [10, 8],              // [W, D] en bloques: NO lo cambies, viene asignado
  floor: 'tiles',             // 'planks' | 'tiles' | 'checker' | 'carpet'
  floorColor: '#8a3b3b',      // solo si floor === 'carpet'
};

export default function build(V, opts = {}) {
  const { THREE } = V;
  const g = new THREE.Group();
  // ... muebles ...
  g.userData.spots = [ /* sitios donde se ponen los agentes */ ];
  g.userData.tick = (dt, t) => { /* animaciones opcionales */ };
  return g;
}
```

`V` es todo lo que exporta `lib/voxel.js`: `THREE`, `box`, `instCubes`, `lam`, `col`, `glow`, `pixelTex`, `noiseFill`, `px`, `shade`, `rng`, `pick`, `textTex`, `sign`, `TEX`, `MAT`, `carpetTex` y `UNIT`. Lee ese archivo para ver las firmas exactas.

`opts.variant` solo lo usan las salas que se instancian más de una vez (por ejemplo, las de reuniones: `'A'` / `'B'`).

## Coordenadas

- Unidades en bloques (1 = un cubo).
- El interior útil ocupa **x ∈ [-0.5, W-0.5]** y **z ∈ [-0.5, D-0.5]**. Las celdas del suelo están centradas en enteros (0…W-1, 0…D-1). El suelo está en **y = 0**.
- No construyas paredes, suelo ni techo. Las paredes quedan fuera de ese rectángulo.
- **La puerta está en la pared -x** (el lado x = -0.5), en las celdas z = `floor(D/2)-1` y `floor(D/2)`. Deja libres las celdas x = 0 y x = 1 a esa altura, y deja un camino razonable desde la puerta hasta cada sitio: los agentes andan en línea recta desde la puerta.
- La cámara suele mirar desde **+x, +z y desde arriba** (ángulo de unos 40°). Pon lo alto (estanterías, máquinas grandes) contra el fondo (z ≈ 0) o contra la pared +x, y lo bajo hacia el frente (+z), para que no tape.
- Las paredes del fondo (-z) y de la puerta (-x) miden 2 bloques de alto. Las del frente (+z) y de la derecha (+x) miden 1 bloque, para poder ver dentro. Lo que cuelgues en las paredes altas tiene que quedar por debajo de y = 2, y en las bajas solo caben cosas a ras de suelo.

## Escala de referencia

- Un personaje mide unos 0.55 de ancho y unos 2.0 de alto de pie. Sentado, la cadera queda 0.11 por encima del asiento.
- Silla: asiento a y = 0.5. Sofá: asiento a 0.4. Mesa: 0.85–0.9. Taburete de barra: 0.8 con barra a 1.1.
- Un personaje con `rotY = 0` mira hacia **+z**. `rotY = Math.PI/2` mira hacia +x.

## Sitios (`userData.spots`)

```js
{ x, z, y, rotY, pose: 'sit' | 'stand', activity: 'coffee' | 'eat' | 'play' | 'pool' | 'meeting' | 'rest' | 'chat' | 'read' }
```

- `x, z`: dónde queda la cadera del personaje. Sentado, las piernas salen unos 0.5 hacia donde mira. De pie, son los pies.
- `y`: altura del asiento si está sentado, o 0 si está de pie (o la altura de una tarima).
- `activity` decide la animación: `coffee` hace que beba de una taza que le aparece en la mano, `play` mueve los brazos como con mandos, `pool` sujeta el taco, `rest` lo pone a dormir con "z", `meeting` y `chat` mueven la cabeza como si hablara, `read` lo deja quieto mirando abajo, y `eat` es como `coffee` pero con un plato.
- Pon entre 4 y 10 sitios por sala, sin que se solapen.

## Estilo

- Vóxel/pixel-art: cajas, texturas de 16×16 hechas con `V.pixelTex` (filtro nearest) y materiales Lambert. Para pantallas y luces, `V.glow`.
- Diseños originales: sin marcas, logos ni personajes de juegos reales. Un arcade genérico con una pantalla de colores inventada vale.
- Usa `V.instCubes` cuando haya muchos cubos repetidos. Mantente por debajo de unos 250 meshes por sala.
- Las animaciones de `tick` deben ser baratas: mover, rotar o cambiar el color de unos pocos objetos, y como mucho actualizar una textura de canvas varias veces por segundo.
- Las sombras ya están activadas en `V.box`.

## Probar la sala

Con el servidor en marcha (`python3 server.py`):

```
node tools/shot.js "http://127.0.0.1:8765/room-test.html?room=<id>" /ruta/salida.png
node tools/shot.js "http://127.0.0.1:8765/room-test.html?room=<id>&view=top" /ruta/top.png
```

Después abre el PNG para mirarlo. La página de prueba dibuja suelo, paredes y puerta, y pone **maniquíes en cada sitio** para que compruebes la escala y la orientación. Los errores de JavaScript salen en la terminal (`pageerror:`) y en rojo en la propia página.
