"""Modelos locales de chat: un servidor que corre en este equipo (Ollama, LM Studio, llama.cpp...).

Se registra como proveedor en la configuración global de OpenCode (~/.config/opencode/opencode.json),
con la API compatible con OpenAI. Así aparece en el Vestuario igual que cualquier otro modelo.
Lo que añade la oficina se apunta en data/modelos-locales.json, para poder quitarlo después sin tocar
lo que hayas configurado a mano.
"""
import json
import os
import re
import shutil
import threading
from urllib.parse import urlparse

import plataforma

CONFIG = os.path.join(os.path.expanduser("~"), ".config", "opencode", "opencode.json")
REGISTRO = os.path.join(plataforma.DATA_DIR, "modelos-locales.json")
HOSTS_LOCALES = {"127.0.0.1", "localhost"}
NOMBRE_RE = re.compile(r"[a-z][a-z0-9-]{1,29}")
MODELO_RE = re.compile(r"[A-Za-z0-9._:/-]{1,100}")
_lock = threading.Lock()


def _leer(ruta, por_defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return por_defecto


def _escribir(ruta, datos):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ruta)


def listar():
    with _lock:
        return _leer(REGISTRO, [])


def _url_base(url):
    """Solo servidores de este equipo. Devuelve la base compatible con OpenAI (…/v1)."""
    p = urlparse(str(url or "").strip())
    if p.scheme != "http" or p.hostname not in HOSTS_LOCALES:
        raise ValueError("La dirección tiene que ser http://127.0.0.1:puerto o http://localhost:puerto")
    try:
        puerto = p.port
    except ValueError:
        raise ValueError("Puerto no válido") from None
    if not puerto:
        raise ValueError("Falta el puerto, por ejemplo http://127.0.0.1:11434")
    return f"http://{p.hostname}:{puerto}/v1"


def validar(entrada):
    nombre = str(entrada.get("nombre", "")).strip().lower()
    if not NOMBRE_RE.fullmatch(nombre):
        raise ValueError("El nombre usa minúsculas, números y guiones (2 a 30 caracteres)")
    base = _url_base(entrada.get("url"))
    crudos = entrada.get("modelos") or []
    if isinstance(crudos, str):
        crudos = re.split(r"[,\n]", crudos)
    modelos = []
    for m in crudos:
        m = str(m).strip()
        if not m:
            continue
        if not MODELO_RE.fullmatch(m):
            raise ValueError(f"Nombre de modelo no válido: {m}")
        if m not in modelos:
            modelos.append(m)
    if not modelos:
        raise ValueError("Indica al menos un modelo (el mismo nombre que usa Ollama, por ejemplo llama3.2)")
    if len(modelos) > 20:
        raise ValueError("Como mucho 20 modelos por servidor")
    return nombre, base, modelos


def _config_con_respaldo():
    if os.path.exists(CONFIG) and not os.path.exists(CONFIG + ".bak"):
        shutil.copy(CONFIG, CONFIG + ".bak")          # copia de seguridad la primera vez
    if not os.path.exists(CONFIG):
        return {"$schema": "https://opencode.ai/config.json"}
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except ValueError:
        # no la reescribimos: podría tener comentarios o un formato que no entendemos
        raise ValueError("Tu opencode.json no es JSON válido; corrígelo a mano y vuelve a intentarlo") from None


def agregar(entrada):
    nombre, base, modelos = validar(entrada)
    with _lock:
        registro = _leer(REGISTRO, [])
        if nombre in _proveedores_a_mano():
            raise ValueError(f"Ya tienes un proveedor «{nombre}» configurado a mano; elige otro nombre")
        cfg = _config_con_respaldo()
        cfg.setdefault("provider", {})[nombre] = {
            "npm": "@ai-sdk/openai-compatible", "name": f"{nombre} (local)",
            "options": {"baseURL": base},
            "models": {m: {"name": f"{m} (local)"} for m in modelos},
        }
        _escribir(CONFIG, cfg)
        registro = [r for r in registro if r["nombre"] != nombre] + [{"nombre": nombre, "url": base, "modelos": modelos}]
        _escribir(REGISTRO, registro)
    return registro


def quitar(nombre):
    nombre = str(nombre or "")
    with _lock:
        registro = _leer(REGISTRO, [])
        if not any(r["nombre"] == nombre for r in registro):
            raise ValueError("Ese modelo local no lo añadió la oficina")
        cfg = _config_con_respaldo()
        cfg.get("provider", {}).pop(nombre, None)
        _escribir(CONFIG, cfg)
        registro = [r for r in registro if r["nombre"] != nombre]
        _escribir(REGISTRO, registro)
    return registro


def _proveedores_a_mano():
    """Proveedores que ya estaban en la configuración y no los añadió la oficina."""
    reg = {r["nombre"] for r in _leer(REGISTRO, [])}
    return {k for k in _leer(CONFIG, {}).get("provider", {}) if k not in reg}
