# Servidor de voz local (solo 127.0.0.1). Motores: Piper y Kokoro. Los modelos se leen de
#   <dir>/piper/*.onnx            (voces Piper, con su .onnx.json)
#   <dir>/kokoro/kokoro-v1.0.onnx + voices-v1.0.bin
# donde <dir> es la carpeta de modelos que Node envía en cada petición.
import io, json, os, re, threading, wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import numpy as np

PORT = int(os.environ.get("TTS_PORT", "5002"))
KOKORO_ES = ["ef_dora", "em_alex", "em_santa"]       # voces en español de Kokoro v1.0
SAFE = re.compile(r"^[\w.-]+$")
_cache, _lock = {}, threading.Lock()                  # modelos cargados / un solo sintetizador a la vez


def piper_voice(d, name):
    from piper import PiperVoice
    path = os.path.join(d, "piper", name + ".onnx")
    if not SAFE.match(name) or not os.path.exists(path):
        raise ValueError(f"Voz Piper no encontrada: {name}")
    if path not in _cache:
        _cache[path] = PiperVoice.load(path)
    return _cache[path]


def kokoro_files(d):
    base = os.path.join(d, "kokoro")
    for model in ("kokoro-v1.0.onnx", "kokoro-v1.0.int8.onnx"):
        m, v = os.path.join(base, model), os.path.join(base, "voices-v1.0.bin")
        if os.path.exists(m) and os.path.exists(v):
            return m, v
    return None


def kokoro_engine(d):
    files = kokoro_files(d)
    if not files:
        raise ValueError("Faltan los archivos de Kokoro en <modelos>/kokoro")
    if files not in _cache:
        from kokoro_onnx import Kokoro
        _cache[files] = Kokoro(*files)
    return _cache[files]


def to_wav(samples, rate):
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm.tobytes())
    return buf.getvalue()


def synth(req):
    text = str(req["text"]).strip()
    if not text:
        raise ValueError("Texto vacío")
    d, engine, voice = req["dir"], req.get("engine", "piper"), req.get("voice", "")
    speed = float(req.get("speed", 1))
    with _lock:
        if engine == "kokoro":
            k = kokoro_engine(d)
            if voice not in KOKORO_ES:
                voice = KOKORO_ES[0]
            samples, rate = k.create(text, voice=voice, speed=speed, lang="es")
            return to_wav(samples, rate)
        from piper import SynthesisConfig
        v = piper_voice(d, voice)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            v.synthesize_wav(text, w, syn_config=SynthesisConfig(length_scale=1 / speed))
        return buf.getvalue()


def list_voices(d):
    piper_dir = os.path.join(d, "piper")
    piper = sorted(f[:-5] for f in os.listdir(piper_dir) if f.endswith(".onnx")) if os.path.isdir(piper_dir) else []
    has_kokoro = kokoro_files(d) is not None
    return {"piper": {"available": bool(piper), "voices": piper},
            "kokoro": {"available": has_kokoro, "voices": KOKORO_ES if has_kokoro else []}}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, ctype, data):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        try:
            if u.path == "/voices":
                d = parse_qs(u.query)["dir"][0]
                return self.reply(200, "application/json", json.dumps(list_voices(d)).encode())
            self.reply(404, "text/plain", b"no")
        except Exception as e:
            self.reply(500, "text/plain", str(e).encode())

    def do_POST(self):
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self.reply(200, "audio/wav", synth(req))
        except Exception as e:
            self.reply(500, "text/plain", str(e).encode())


print(f"TTS listo en :{PORT}", flush=True)
ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
