#!/usr/bin/env python3
"""Lanzador multiplataforma: arranca la oficina y la abre en el navegador (Linux, Windows o empaquetada)."""
import os
import sys
import threading
import time
import traceback
import webbrowser

import plataforma


def _registro():
    """Sin consola (MineOffice.exe) no hay dónde ver los mensajes: se escriben en data/oficina.log."""
    if not plataforma.FROZEN:
        return
    os.makedirs(plataforma.DATA_DIR, exist_ok=True)
    f = open(os.path.join(plataforma.DATA_DIR, "oficina.log"), "a", encoding="utf-8", buffering=1)
    f.write(f"\n--- arranque {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    sys.stdout = sys.stderr = f


PORT = plataforma.PUERTO


def abrir():
    webbrowser.open(f"http://127.0.0.1:{PORT}/")


if __name__ == "__main__":
    _registro()
    try:
        import server
        threading.Timer(1.5, abrir).start()
        server.main(["--port", str(PORT)])
    except BaseException:
        traceback.print_exc()
        raise
