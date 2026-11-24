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

## Primer uso

Al abrir la oficina por primera vez aparece el asistente de configuración:

- **Nombre del jefe.** Por defecto «Claude». Es quien recibe las peticiones de tus agentes. Puedes cambiarlo luego con **⚙ Ajustes**.
- **Motores.** Se detectan los instalados (Claude Code, OpenCode y Kimi Code). Los desactivados no aparecen al contratar.
- **Ahorro.** «Normal», o «Preferir gratis»: los agentes de OpenCode usan un modelo gratuito cuando el suyo es de pago. Los de Claude no cambian, van con tu suscripción.

Los proveedores de modelos (OpenAI, Mistral, NVIDIA…) se añaden en cada motor, no en la oficina: en OpenCode con `opencode auth`, en Kimi con su propio comando.

Los ajustes se guardan en `data/ajustes.json`.

## Windows

Hay un workflow (`.github/workflows/windows.yml`) que genera `MineOffice-windows.zip` con PyInstaller. Para probarlo en tu PC:

1. Descomprime el zip y ejecuta `MineOffice.exe`. Se abre la oficina en el navegador.
2. Los datos (`data/`) quedan junto al ejecutable.
3. Los agentes necesitan Python 3 para `tools/jefe.py` y los hooks. Instálalo desde python.org y comprueba que `python` o `py` responden en la terminal.
4. Claude Code y OpenCode deben estar instalados y en el `PATH`.

Aún no se ha probado en Windows: el empaquetado está verificado en Linux. La ventana de cada agente usa la consola de Windows, y las ventanas de kitty y konsole son solo de Linux.

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

Liberty habla y escucha, pero la voz no viene en el paquete. Se descarga desde **⚙ Ajustes → Voz de la secretaria** (unos 1 GB, con Python 3 instalado en el equipo). Crea un entorno en `data/voz/tts-venv`, instala `piper-tts` y `faster-whisper` en CPU, y baja el modelo de voz Piper `es_AR-daniela-high` y Whisper `small`.

Si ya tienes el proyecto de voz de Liberty en `~/liberty`, la oficina lo usa a falta de la descarga. Sin voz, todo lo demás funciona; Liberty sigue en el chat.

Los servidores de voz están en `voz/` (`tts_server.py` y `stt_server.py`). El código de la descarga está en `voz.py`.

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

[Beerware (revisión 42)](LICENSE): haz lo que quieras con esto, conserva el aviso y, si algún día nos vemos y te ha servido, me debes una cerveza 🍺 (o que compartas el contacto de tu hermana 😏).
`vendor/` conserva las licencias de sus autores (three.js, MIT).
