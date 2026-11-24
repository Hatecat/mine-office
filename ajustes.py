"""Ajustes de la oficina: nombre del jefe, motores instalados y modo de ahorro. Se guardan en data/ajustes.json."""
import json
import os
import re
import subprocess
import threading

import plataforma

from plataforma import DATA_DIR, which

FILE = os.path.join(DATA_DIR, "ajustes.json")
KIMI_BIN_FALLBACK = os.path.join(os.path.expanduser("~"), ".kimi-code", "bin", "kimi")
MOTORES = ("claude", "opencode", "kimi")
AHORROS = ("normal", "gratis")
DEFECTO = {
    "configurado": False,                      # False hasta que pasas el asistente de primer uso
    "jefe": "Claude",
    "motores": {"claude": True, "opencode": True, "kimi": False},
    "ahorro": "normal",                        # gratis: en OpenCode, cambia a modelos gratuitos si el elegido es de pago
    "modeloLiberty": "claude-sonnet-5-5",      # modelo de Claude con el que responde la secretaria
    "presupuestoDia": 5.0,                     # USD estimados al día en modelos de pago; 0 = sin límite
}
# Modelos de OpenCode gratuitos que no llevan «free» en el nombre (según models.dev)
GRATIS_EXTRA = {"big-pickle"}
_lock = threading.Lock()


def cargar():
    with _lock:
        try:
            with open(FILE, encoding="utf-8") as f:
                datos = json.load(f)
        except (OSError, ValueError):
            datos = {}
    out = json.loads(json.dumps(DEFECTO))
    for k, v in datos.items():
        if k == "motores" and isinstance(v, dict):
            out["motores"].update({m: bool(v[m]) for m in MOTORES if m in v})
        elif k in DEFECTO:
            out[k] = v
    return out


def guardar(datos):
    with _lock:
        os.makedirs(os.path.dirname(FILE), exist_ok=True)
        tmp = FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        os.replace(tmp, FILE)


def validar(entrada):
    """Devuelve los ajustes limpios o lanza ValueError con un mensaje para el usuario."""
    actual = cargar()
    jefe = str(entrada.get("jefe", actual["jefe"])).strip()[:40]
    if not jefe:
        raise ValueError("El jefe necesita un nombre")
    motores = {m: bool(entrada.get("motores", {}).get(m, actual["motores"][m])) for m in MOTORES}
    if not any(motores.values()):
        raise ValueError("Activa al menos un motor")
    ahorro = entrada.get("ahorro", actual["ahorro"])
    if ahorro not in AHORROS:
        raise ValueError("Modo de ahorro no válido")
    modelo = str(entrada.get("modeloLiberty", actual["modeloLiberty"])).strip()
    if not re.fullmatch(r"claude-[a-z0-9.\-]{3,60}", modelo):
        raise ValueError("Modelo de Liberty no válido")
    try:
        presupuesto = float(entrada.get("presupuestoDia", actual["presupuestoDia"]))
    except (TypeError, ValueError):
        raise ValueError("Presupuesto no válido") from None
    if not 0 <= presupuesto <= 10000:
        raise ValueError("Presupuesto no válido")
    return {"configurado": bool(entrada.get("configurado", actual["configurado"])),
            "jefe": jefe, "motores": motores, "ahorro": ahorro, "modeloLiberty": modelo,
            "presupuestoDia": round(presupuesto, 2)}


def detectar():
    """Qué motores están instalados en este equipo."""
    kimi = which("kimi") or (KIMI_BIN_FALLBACK if os.path.exists(KIMI_BIN_FALLBACK) else None)
    return {"claude": bool(which("claude")), "opencode": bool(which("opencode")), "kimi": bool(kimi)}


def proveedores_opencode():
    """Proveedores de OpenCode con clave guardada (opencode auth list)."""
    exe = which("opencode")
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "auth", "list"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    nombres = []
    for linea in out.splitlines():
        if "stored" in linea.lower():
            col = re.split(r"\s{2,}", linea.strip())[0]
            if col and col not in nombres:
                nombres.append(col)
    return nombres


def es_gratis(model_id):
    """Heurística: ids con «free» (OpenCode, OpenRouter «:free») y los de GRATIS_EXTRA."""
    if not model_id:
        return False
    corto = model_id.split("/")[-1]
    return "free" in model_id.lower() or model_id.endswith(":free") or corto in GRATIS_EXTRA
