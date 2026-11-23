"""Voz de la secretaria (Liberty): descarga opcional de su entorno de Python y de sus modelos.

No viene en el paquete. Desde Ajustes se instala en DATA_DIR/voz: un entorno virtual con los paquetes
de voz, los modelos de Piper (hablar) y Whisper pequeño (escuchar), y los servidores de voz.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.request

import plataforma

DIR = os.path.join(plataforma.DATA_DIR, "voz")
FUENTE = os.path.join(plataforma.HERE, "voz")          # servidores de voz que viene con la oficina
VENV = os.path.join(DIR, "tts-venv")
PAQUETES = ["piper-tts==1.8.0", "faster-whisper==1.2.1", "numpy"]
VOZ_PIPER = "es_AR-daniela-high"
PIPER = "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_AR/daniela/high/"
WHISPER = "https://huggingface.co/Systran/faster-whisper-small/resolve/main/"
ARCHIVOS = [
    (PIPER + VOZ_PIPER + ".onnx", "models/piper/" + VOZ_PIPER + ".onnx"),
    (PIPER + VOZ_PIPER + ".onnx.json", "models/piper/" + VOZ_PIPER + ".onnx.json"),
    (WHISPER + "model.bin", "models/whisper/small/model.bin"),
    (WHISPER + "config.json", "models/whisper/small/config.json"),
    (WHISPER + "tokenizer.json", "models/whisper/small/tokenizer.json"),
    (WHISPER + "vocabulary.txt", "models/whisper/small/vocabulary.txt"),
]
TAMANO = "unos 1 GB"

_estado = {"fase": "no instalada", "detalle": "", "error": None, "progreso": None}
_lock = threading.Lock()


def _py_venv(d):
    return os.path.join(d, "Scripts", "python.exe") if plataforma.WIN else os.path.join(d, "bin", "python")


def instalada():
    """Está todo lo necesario para hablar y escuchar."""
    rutas = [_py_venv(VENV), os.path.join(DIR, "tts_server.py"), os.path.join(DIR, "stt_server.py"),
             os.path.join(DIR, "settings.json")] + [os.path.join(DIR, rel) for _, rel in ARCHIVOS]
    return all(os.path.exists(r) for r in rutas)


def estado():
    with _lock:
        e = dict(_estado)
    e["instalada"] = instalada()
    e["tamano"] = TAMANO
    if e["instalada"] and e["fase"] in ("no instalada", "error"):
        e["fase"] = "instalada"
    return e


def _set(fase, detalle="", error=None, progreso=None):
    with _lock:
        _estado.update(fase=fase, detalle=detalle, error=error, progreso=progreso)


def _python_base():
    """Un Python del sistema para crear el entorno (el ejecutable empaquetado no sirve para eso)."""
    if not plataforma.FROZEN:
        return [sys.executable]
    candidatos = [["py", "-3"], ["python3"], ["python"]] if plataforma.WIN else [["python3"], ["python"]]
    for c in candidatos:
        if shutil.which(c[0]):
            return c
    raise RuntimeError("Hace falta Python 3 instalado para crear el entorno de voz")


def _run(cmd, paso):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{paso}: {(r.stderr or r.stdout).strip()[-400:]}")


def _bajar(url, destino, paso):
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    tmp = destino + ".part"
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        leido = 0
        while True:
            bloque = r.read(1 << 20)
            if not bloque:
                break
            f.write(bloque); leido += len(bloque)
            pct = f"{leido * 100 // total} %" if total else f"{leido // 1_000_000} MB"
            _set("descargando modelos", f"{paso} ({pct})")
    os.replace(tmp, destino)


def _instalar():
    try:
        os.makedirs(DIR, exist_ok=True)
        if not os.path.exists(_py_venv(VENV)):
            _set("creando entorno", "Creando el entorno de Python de la voz")
            _run(_python_base() + ["-m", "venv", VENV], "crear entorno")
        _set("instalando paquetes", "Instalando piper-tts, faster-whisper y numpy (puede tardar varios minutos)")
        _run([_py_venv(VENV), "-m", "pip", "install", "--quiet", *PAQUETES], "instalar paquetes")
        for url, rel in ARCHIVOS:
            destino = os.path.join(DIR, rel)
            if not os.path.exists(destino):
                _bajar(url, destino, os.path.basename(rel))
        _set("copiando servidores", "Copiando los servidores de voz")
        for nombre in ("tts_server.py", "stt_server.py"):
            shutil.copy(os.path.join(FUENTE, nombre), os.path.join(DIR, nombre))
        with open(os.path.join(DIR, "settings.json"), "w", encoding="utf-8") as f:
            json.dump({"tts": {"engine": "piper", "voice": VOZ_PIPER, "speed": 1.2}, "modelsDir": "models"}, f)
        _set("instalada", "Voz lista", None, None)
    except Exception as e:  # noqa: BLE001 - se muestra en Ajustes, no tumba la oficina
        _set("error", "", str(e), None)


def iniciar():
    """Arranca la descarga en segundo plano. Devuelve False si ya hay una en marcha o ya está instalada."""
    global _hilo
    if instalada() or (_hilo and _hilo.is_alive()):
        return False
    _hilo = threading.Thread(target=_instalar, daemon=True)
    _hilo.start()
    return True


_hilo = None
