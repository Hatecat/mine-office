#!/usr/bin/env python3
"""Lanzador multiplataforma: arranca la oficina y la abre en el navegador (Linux, Windows o empaquetada)."""
import threading
import webbrowser

import plataforma
import server

PORT = plataforma.PUERTO


def abrir():
    webbrowser.open(f"http://127.0.0.1:{PORT}/")


if __name__ == "__main__":
    threading.Timer(1.5, abrir).start()
    server.main(["--port", str(PORT)])
