"""Liberty, la secretaria de la oficina: cuando un agente necesita algo de ti, ella lo dice en voz alta.

Usa el servidor de voz de ~/liberty (tts_server.py, Piper o Kokoro, en CPU) con la voz configurada en
~/liberty/settings.json, y reproduce el audio con pw-play. Si Liberty está abierta, comparte su servidor de voz;
si no, arranca solo ese servidor (sin el avatar ni la transcripción, que usan la GPU).
"""
import json
import os
import queue
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import plataforma
import voz

HOME = os.path.expanduser("~")
LIBERTY_PROPIA = os.path.join(HOME, "liberty")     # proyecto de voz de Liberty, si lo tienes instalado a mano
DATA = plataforma.DATA_DIR


def _liberty():
    """Carpeta de la voz: la que descargaste desde Ajustes o, si no, tu proyecto ~/liberty."""
    return voz.DIR if voz.instalada() or not os.path.isdir(LIBERTY_PROPIA) else LIBERTY_PROPIA


def _py(d):
    return voz._py_venv(os.path.join(d, "tts-venv"))
CONF = os.path.join(DATA, "office.json")
EVENTS = os.path.join(DATA, "events.jsonl")
TTS_PORT = 5002
STT_PORT = 5013                         # transcriptor propio de la oficina (en CPU; la app de Liberty usa el 5003)
STT_MODEL = "small"
SID = "liberty"                         # su «sesión» para los globos

_q = queue.Queue(maxsize=20)
_last_said = {}                         # (sid, tipo) -> momento (para no repetir)
speaking_until = 0.0


# ---------------------------------------------------------------- ajustes
def conf():
    try:
        with open(CONF) as f:
            return {"voz": True, **json.load(f)}
    except (OSError, ValueError):
        return {"voz": True}


def set_voice(on):
    c = conf(); c["voz"] = bool(on)
    os.makedirs(DATA, exist_ok=True)
    with open(CONF, "w") as f:
        json.dump(c, f)
    return c


def liberty_tts_settings():
    tts, models = {"engine": "piper", "voice": "es_MX-claude-high", "speed": 1}, "models"
    try:
        with open(os.path.join(_liberty(), "settings.json")) as f:
            s = json.load(f)
        tts.update(s.get("tts") or {})
        models = s.get("modelsDir") or models
    except (OSError, ValueError):
        pass
    return tts, os.path.normpath(os.path.join(_liberty(), models))


# ---------------------------------------------------------------- voz
def _port_open():
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", TTS_PORT)) == 0


def ensure_tts():
    if _port_open():
        return True
    py = _py(_liberty())
    script = os.path.join(_liberty(), "tts_server.py")
    if not (os.path.exists(py) and os.path.exists(script)):
        return False
    log = open(os.path.join(DATA, "tts.log"), "ab")
    subprocess.Popen([py, script], cwd=_liberty(), env=dict(os.environ, TTS_PORT=str(TTS_PORT)),
                     stdin=subprocess.DEVNULL, stdout=log, stderr=log, **plataforma.new_group_kwargs())
    for _ in range(40):
        if _port_open():
            return True
        time.sleep(0.5)
    return False


def _stt_open():
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", STT_PORT)) == 0


def _stt_get(path, data=None, timeout=10):
    _, models_dir = liberty_tts_settings()
    q = urllib.parse.urlencode({"model": STT_MODEL, "dir": models_dir, "hot": "Liberty"})
    req = urllib.request.Request(f"http://127.0.0.1:{STT_PORT}{path}?{q}", data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def stt_status():
    """Arranca (si hace falta) el transcriptor Whisper de Liberty en CPU y dice si ya está listo."""
    if not _stt_open():
        py = _py(_liberty())
        script = os.path.join(_liberty(), "stt_server.py")
        if not (os.path.exists(py) and os.path.exists(script)):
            return {"state": "error", "error": "La voz no está instalada: descárgala desde Ajustes"}
        log = open(os.path.join(DATA, "stt.log"), "ab")
        env = dict(os.environ, STT_PORT=str(STT_PORT), CUDA_VISIBLE_DEVICES="")    # CPU: la GPU es para el arte
        subprocess.Popen([py, script], cwd=_liberty(), env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         **plataforma.new_group_kwargs())
        for _ in range(60):
            if _stt_open():
                break
            time.sleep(0.5)
        else:
            return {"state": "error", "error": "El transcriptor no arrancó (mira data/stt.log)"}
    return _stt_get("/health")


def transcribe(raw):
    return _stt_get("/stt", raw, timeout=60)


def synth(text):
    tts, models_dir = liberty_tts_settings()
    body = json.dumps({"text": text, **tts, "dir": models_dir}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{TTS_PORT}/tts", data=body)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _player():
    if plataforma.WIN:
        return "winsound"
    for p in ("pw-play", "paplay", "aplay"):
        if shutil.which(p):
            return p
    return None


def _reproducir(player, path):
    if player == "winsound":        # Windows: sin procesos externos
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME)
    else:
        subprocess.run([player, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)


def _worker():
    global speaking_until
    while True:
        text = _q.get()
        try:
            if not conf()["voz"] or not ensure_tts():
                continue
            wav = synth(text)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav); path = f.name
            speaking_until = time.time() + 30
            player = _player()
            if player:
                _reproducir(player, path)
            os.remove(path)
        except Exception as e:  # noqa: BLE001 - la voz nunca debe tumbar la oficina
            print("Liberty: no pude hablar:", e)
        finally:
            speaking_until = time.time() + 1.5


def say(text, show=True):
    """Pone una frase en la cola de Liberty (y la muestra en su globo)."""
    text = " ".join(str(text).split())[:300]
    if not text:
        return
    if show:
        import server
        server.add_event(SID, "Say", text)
    if conf()["voz"]:
        try:
            _q.put_nowait(text)
        except queue.Full:
            pass


# ---------------------------------------------------------------- qué decir
_names, _names_t = {}, 0


def _name_map():
    global _names, _names_t
    if time.time() - _names_t < 10:
        return _names
    import roster
    import server
    names = {}
    try:
        for a in server.snapshot()["agents"]:
            if a.get("kind") == "member":
                m = roster.get_member(a["memberId"])
                if m and m.get("sessionId"):
                    names[m["sessionId"]] = a["name"]
            elif not a.get("secretary"):
                names[a["id"]] = a["name"]
        for m in roster.load()["members"]:
            if m.get("sessionId"):
                names.setdefault(m["sessionId"], m["name"])
    except Exception:  # noqa: BLE001
        pass
    _names, _names_t = names, time.time()
    return names


def phrase(e):
    ev, typ, msg = e.get("ev"), e.get("type") or "", e.get("msg") or ""
    if ev == "BossAsk":
        import roster
        if e.get("sid") in roster.virtual_sids():
            return None, None                       # Liberty ya sabe lo que ella misma le pide al jefe
        return "jefe", msg.replace(" le pide al jefe: ", " le pide a Claude: ", 1)[:220] + ". Cuando puedas, díselo en su ventana."
    who = _name_map().get(e.get("sid"))
    if not who:
        return None, None
    if ev == "Notification":
        if typ == "idle_prompt" or "waiting for your input" in msg.lower():
            return None, None
        if typ == "permission_prompt" or "permission" in msg.lower():
            tool = msg.split(" use ")[-1].strip(". ") if " use " in msg else ""
            return "permiso", f"{who} necesita tu permiso" + (f" para usar {tool}." if tool else ".")
        return "pregunta", f"{who} tiene una pregunta para ti."
    if ev == "Resumen":
        return "listo", f"{who} dice: {msg}"
    if ev in ("Stop", "RunDone"):
        return "listo", f"{who} ha terminado y te espera."
    if ev == "Denied":
        return "permiso", f"{who} no pudo terminar: necesita permiso."
    if ev in ("PM", "PMHang"):
        return "pm", f"Aviso de {who}: {msg}."
    return None, None


def _follow():
    """Lee los avisos nuevos de events.jsonl y los anuncia."""
    pos = os.path.getsize(EVENTS) if os.path.exists(EVENTS) else 0
    while True:
        time.sleep(1)
        try:
            size = os.path.getsize(EVENTS)
        except OSError:
            continue
        if size < pos:
            pos = 0
        if size == pos:
            continue
        with open(EVENTS, "rb") as f:
            f.seek(pos)
            chunk = f.read()
        end = chunk.rfind(b"\n") + 1
        pos += end
        for line in chunk[:end].decode(errors="replace").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("sid") == SID:
                continue
            kind, text = phrase(e)
            if not text:
                continue
            key = (e.get("sid"), kind)
            if time.time() - _last_said.get(key, 0) < 45:      # Stop + RunDone de la misma orden: una sola vez
                continue
            _last_said[key] = time.time()
            say(text)


def start():
    threading.Thread(target=_worker, daemon=True).start()
    threading.Thread(target=_follow, daemon=True).start()


def agent():
    """Liberty como personaje de la oficina (va en Dirección, junto al jefe)."""
    busy = time.time() < speaking_until
    return {"id": SID, "kind": "session", "secretary": True, "parent": None, "name": "Liberty", "job": "Secretaria",
            "title": "anuncia en voz alta lo que te necesitan los agentes", "model": "piper (voz)",
            "status": "busy" if busy else "idle", "tool": "Hablando" if busy else None, "detail": "",
            "tokens": 0, "cwd": "~", "voice": conf()["voz"],
            "look": {"skin": "#f1c27d", "hair": "#6a3fb5", "shirt": "#f4f1fb", "pants": "#2d2f3a", "accessory": "auriculares"}}
