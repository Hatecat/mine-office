#!/usr/bin/env python3
"""Servidor MCP (stdio) con el estudio de imágenes para agentes de OpenCode.

Expone dos herramientas con argumentos tipados: generar_imagen y estado. No hay shell: cada generación
es un proceso de arte.py lanzado con una lista de argumentos. Solo habla con arte.py de esta carpeta.
Sin dependencias: JSON-RPC por líneas, como pide el transporte stdio de MCP.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARTE = os.path.join(HERE, "arte.py")
PROTOCOLO = "2024-11-05"
TAM_PERMITIDOS = (512, 768, 1024)
MODELOS = ("animagine", "flux")

HERRAMIENTAS = [
    {"name": "generar_imagen",
     "description": "Genera una imagen con el estudio local (ComfyUI, GPU de este PC). Devuelve la ruta del archivo.",
     "inputSchema": {"type": "object", "required": ["prompt"], "additionalProperties": False, "properties": {
         "prompt": {"type": "string", "maxLength": 500, "description": "Tags en inglés, estilo Danbooru para Animagine"},
         "ancho": {"type": "integer", "enum": list(TAM_PERMITIDOS)},
         "alto": {"type": "integer", "enum": list(TAM_PERMITIDOS)},
         "pasos": {"type": "integer", "minimum": 1, "maximum": 50},
         "semilla": {"type": "integer", "minimum": 0, "maximum": 2**31 - 1},
         "modelo": {"type": "string", "enum": list(MODELOS)},
     }}},
    {"name": "estado", "description": "Estado del estudio local: si ComfyUI está en marcha y qué hace.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}}},
]


def _argv_imagen(a):
    prompt = str(a.get("prompt") or "")
    if not prompt.strip() or len(prompt) > 500 or "\n" in prompt or prompt.lstrip().startswith("-"):
        raise ValueError("El prompt debe ser una línea de 1 a 500 caracteres y no puede empezar por «-»")
    ancho = int(a.get("ancho", 1024)); alto = int(a.get("alto", 1024))
    if ancho not in TAM_PERMITIDOS or alto not in TAM_PERMITIDOS:
        raise ValueError("Tamaño no permitido")
    modelo = a.get("modelo", "animagine")
    if modelo not in MODELOS:
        raise ValueError("Modelo no permitido")
    argv = [sys.executable, ARTE, "imagen", prompt, "--ancho", str(ancho), "--alto", str(alto), "--modelo", modelo]
    if "pasos" in a:
        p = int(a["pasos"])
        if not 1 <= p <= 50:
            raise ValueError("Pasos fuera de rango")
        argv += ["--pasos", str(p)]
    if "semilla" in a:
        s = int(a["semilla"])
        if not 0 <= s <= 2**31 - 1:
            raise ValueError("Semilla fuera de rango")
        argv += ["--semilla", str(s)]
    return argv


def _llamar(nombre, args):
    if nombre == "generar_imagen":
        argv = _argv_imagen(args or {})
        timeout = 900
    elif nombre == "estado":
        argv, timeout = [sys.executable, ARTE, "estado"], 60
    else:
        raise ValueError(f"Herramienta desconocida: {nombre}")
    r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, shell=False)
    salida = (r.stdout or "") + (r.stderr or "")
    texto = salida.strip()[-3000:] or "(sin salida)"
    return {"content": [{"type": "text", "text": texto}], "isError": r.returncode != 0}


def _responder(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        try:
            msg = json.loads(linea)
        except ValueError:
            continue
        metodo, mid = msg.get("method"), msg.get("id")
        if mid is None:              # notificaciones (p. ej. initialized): no se contestan
            continue
        try:
            if metodo == "initialize":
                res = {"protocolVersion": PROTOCOLO, "capabilities": {"tools": {}},
                       "serverInfo": {"name": "arte", "version": "1"}}
            elif metodo == "tools/list":
                res = {"tools": HERRAMIENTAS}
            elif metodo == "tools/call":
                p = msg.get("params") or {}
                res = _llamar(str(p.get("name", "")), p.get("arguments") or {})
            else:
                _responder({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "método no soportado"}})
                continue
            _responder({"jsonrpc": "2.0", "id": mid, "result": res})
        except Exception as e:  # noqa: BLE001 - se devuelve como error de la herramienta, no tumba el servidor
            _responder({"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}})


if __name__ == "__main__":
    main()
