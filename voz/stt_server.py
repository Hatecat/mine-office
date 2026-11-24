# Servidor de transcripción local (solo 127.0.0.1) con faster-whisper. Usa la GPU NVIDIA (CUDA, float16)
# y, si no está disponible, la CPU (int8). Los modelos se guardan en <carpeta de modelos>/whisper.
#   GET  /health?model=..&dir=..  -> estado de carga {state, model, device}; inicia la carga si hace falta
#   POST /stt?model=..&dir=..&hot=..   cuerpo: audio float32 mono 16 kHz  -> {"text": ".."}
import ctypes, glob, json, os, re, site, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("STT_PORT", "5003"))

TOKEN = os.environ.get("VOZ_TOKEN", "")      # secreto que pone la oficina: sin él no atiende a nadie
MODELOS = os.environ.get("VOZ_DIR", "")      # carpeta de modelos fijada al arrancar (no la elige quien llama)
PERMITIDOS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}


def autorizada(h):
    """Solo peticiones de este equipo, con el Host esperado y el secreto de la oficina (contra DNS rebinding y CSRF)."""
    import hmac
    return (bool(TOKEN) and h.headers.get("Host", "") in PERMITIDOS
            and hmac.compare_digest(h.headers.get("X-Voz-Token", ""), TOKEN))
ALLOWED = {"tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"}


def preload_cuda_libs():
    """Carga cuBLAS y cuDNN de los paquetes pip `nvidia-*` para que CTranslate2 los encuentre."""
    for sp in site.getsitepackages():
        for pattern in ("nvidia/cublas/lib/libcublas.so.12*", "nvidia/cublas/lib/libcublasLt.so.12*",
                        "nvidia/cudnn/lib/libcudnn*.so.9*"):
            for so in sorted(glob.glob(os.path.join(sp, pattern))):
                try:
                    ctypes.CDLL(so, mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    pass


preload_cuda_libs()
import numpy as np                      # noqa: E402
import ctranslate2                      # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402

state = {"state": "idle", "model": None, "device": None, "error": None, "wanted": None}
model = None
lock = threading.Lock()                 # una carga o transcripción a la vez


def load(name, root):
    global model
    state.update(state="loading", error=None, wanted=name)
    try:
        cuda = ctranslate2.get_cuda_device_count() > 0
        attempts = [("cuda", "float16"), ("cpu", "int8")] if cuda else [("cpu", "int8")]
        last = None
        for device, ctype in attempts:
            try:
                # modelo ya descargado en una carpeta propia (la oficina lo instala así): se usa tal cual
                local = os.path.join(root, name)
                m = WhisperModel(local if os.path.isdir(local) else name, device=device, compute_type=ctype, download_root=root)
                # calentamiento: detecta aquí fallos de CUDA/cuDNN, no en la primera frase del usuario
                list(m.transcribe(np.zeros(16000, np.float32), language="es", beam_size=1)[0])
                with lock:
                    model = m
                state.update(state="ready", model=name, device=f"{device}/{ctype}")
                return
            except Exception as e:      # noqa: BLE001
                last = e
        raise last
    except Exception as e:              # noqa: BLE001
        state.update(state="error", error=str(e)[:300])


def ensure(name, root):
    if name not in ALLOWED:
        raise ValueError("Modelo no permitido")
    if state["state"] == "loading" and state["wanted"] == name:
        return
    if state["state"] == "ready" and state["model"] == name:
        return
    if state["state"] == "error" and state["wanted"] == name:
        return
    threading.Thread(target=load, args=(name, root), daemon=True).start()
    time.sleep(0.05)


def transcribe(raw, hot):
    audio = np.frombuffer(raw, dtype=np.float32)
    prompt = f"Conversación en español con {hot}, una asistente virtual." if hot else None
    with lock:
        segments, _ = model.transcribe(
            audio, language="es", beam_size=5, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
            condition_on_previous_text=False, initial_prompt=prompt, hotwords=hot or None,
            no_speech_threshold=0.6, temperature=0.0,
        )
        return " ".join(s.text.strip() for s in segments).strip()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def params(self):
        q = parse_qs(urlparse(self.path).query)
        root = os.path.join(MODELOS, "whisper")
        return q.get("model", ["small"])[0], root, q.get("hot", [""])[0][:40]

    def do_GET(self):
        if not autorizada(self):
            return self.reply(403, {"error": "prohibido"})
        try:
            name, root, _ = self.params()
            ensure(name, root)
            self.reply(200, {k: state[k] for k in ("state", "model", "device", "error")})
        except Exception as e:          # noqa: BLE001
            self.reply(400, {"error": str(e)})

    def do_POST(self):
        if not autorizada(self):
            return self.reply(403, {"error": "prohibido"})
        try:
            name, root, hot = self.params()
            raw = self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 4_000_000))
            ensure(name, root)
            if state["state"] != "ready" or state["model"] != name:
                return self.reply(503, {"error": "El modelo de transcripción aún se está cargando", **state})
            t0 = time.time()
            text = transcribe(raw, hot)
            self.reply(200, {"text": text, "seconds": round(time.time() - t0, 2), "device": state["device"]})
        except Exception as e:          # noqa: BLE001
            self.reply(500, {"error": str(e)})


if not TOKEN or not MODELOS:
    raise SystemExit("Falta VOZ_TOKEN o VOZ_DIR: el servidor lo arranca la oficina")
print(f"STT listo en :{PORT}", flush=True)
ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
