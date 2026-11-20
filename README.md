# mine-office

Una oficina 3D de voxels donde ves trabajar a tus agentes de IA. Cada sesión de **Claude Code** y de **OpenCode** que tienes abierta aparece como un personaje sentado en su mesa; los agentes fijos de tu plantilla viven en equipos y reciben órdenes desde un chat dentro de la propia oficina.

Todo corre en tu máquina, sin servicios externos propios: un servidor de Python sin dependencias (`server.py`) y una página con three.js.

> Proyecto personal, en español y a medio hacer. Funciona en Linux; está pensado para un solo usuario en su propio PC.

## Qué hace

- **Plano de oficina** con salas (cafetería, reuniones, juegos, descanso, vestuario…) y un personaje por agente que trabaja, descansa o pasea según lo que esté haciendo.
- **Plantilla persistente**: equipos y miembros con nombre, cargo, personalidad, aspecto (Vestuario), motor (Claude u OpenCode), modelo y permisos. Se editan desde la interfaz.
- **Chat con cada agente**: les mandas órdenes y ves lo que hacen. Pueden pedirte permiso, y un globo sobre su cabeza avisa cuando terminan o necesitan algo.
- **Gastos**: estimación a precio de API de lo que gasta cada agente, por día y por orden.
- **Jefe y buzón**: un jefe (tu sesión principal de Claude Code) al que los agentes le piden cosas con `tools/jefe.py`; puede contestarles.
- **PM automático**: un miembro con rol de PM cambia a un modelo gratuito al agente que se queda sin cuota, y rescata a los que se cuelgan.
- **Secretaria con voz** (`secretaria.py`): lee en voz alta los avisos y, opcionalmente, escucha por el micrófono («Liberty, …»). Usa un servidor de voz local que **no va en este repositorio** (ver más abajo).
- **Estudio de arte** (`tools/arte/`): imágenes y modelos 3D con un ComfyUI local (Animagine, Flux y Hunyuan3D).

## Requisitos

- Python 3.11 o superior y un navegador moderno.
- [Claude Code](https://claude.com/claude-code) (`claude`) para los agentes de Claude; [OpenCode](https://opencode.ai) para los de OpenCode. Con uno basta.
- Opcional: Node.js (capturas con `tools/shot.js`), ComfyUI y Blender (arte), un servidor de voz local (secretaria).

## Cómo arrancarla

```bash
git clone https://github.com/Hatecat/mine-office.git
cd mine-office
python3 server.py            # http://127.0.0.1:8765  (--port para cambiarlo)
# o: ./oficina               # lo arranca y abre el navegador
```

La primera vez crea `data/` (ignorada por Git) con una plantilla de ejemplo: Rocío, Bruno y Nube.

### Avisos de «terminé» y «necesito permiso»

Los globos usan los hooks de Claude Code. Añade esto a `~/.claude/settings.json` (cambiando la ruta):

```json
"hooks": {
  "Notification":     [{"hooks": [{"type": "command", "command": "python3 /RUTA/mine-office/hook.py", "timeout": 5}]}],
  "Stop":             [{"hooks": [{"type": "command", "command": "python3 /RUTA/mine-office/hook.py", "timeout": 5}]}],
  "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "python3 /RUTA/mine-office/hook.py", "timeout": 5}]}]
}
```

## Seguridad

- El servidor solo escucha en `127.0.0.1`. **No lo expongas a la red**: puede lanzar agentes que ejecutan comandos.
- Las acciones de escritura exigen un token que se guarda en `data/token` y va dentro de la página.
- Los agentes se lanzan con los permisos que les des en el Vestuario. «Sin preguntar nada» es peligroso.
- `data/` contiene tus conversaciones, gastos y token: no la subas a ningún sitio.

## Voz de la secretaria

`secretaria.py` espera encontrar un proyecto de voz local en `~/liberty` (con `tts_server.py` y, para escuchar, `stt_server.py`, y un entorno `tts-venv`). Ese proyecto no forma parte de este repositorio. Sin él, todo lo demás funciona y la voz queda desactivada.

## Estructura

```
server.py        servidor HTTP y estado en vivo
roster.py        plantilla, órdenes, PM y habilidades
usage.py         historial de gastos
secretaria.py    voz y escucha
hook.py          hooks de Claude Code
lib/             interfaz (three.js)
rooms/           una sala por archivo (ver rooms/README.md)
tools/           jefe.py, arte/, shot.js
vendor/          three.js y OrbitControls (MIT)
```

## Licencia

[Beerware (revisión 42)](LICENSE): haz lo que quieras con esto, conserva el aviso y, si algún día nos vemos y te ha servido, me debes una cerveza. 🍺
`vendor/` conserva las licencias de sus autores (three.js, MIT).
