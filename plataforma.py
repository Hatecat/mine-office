"""Diferencias entre Linux y Windows en un solo sitio: procesos, binarios y carpeta de datos."""
import os
import shutil
import subprocess
import sys

WIN = os.name == "nt"
FROZEN = bool(getattr(sys, "frozen", False))   # empaquetado con PyInstaller

# Código (HTML, JS, tools/) y datos (data/) viven en sitios distintos cuando está empaquetado.
HERE = getattr(sys, "_MEIPASS", None) if FROZEN else None
HERE = HERE or os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("OFICINA_DATOS") or (
    os.path.join(os.path.dirname(sys.executable), "data") if FROZEN else os.path.join(HERE, "data"))


def which(name):
    """Ruta del binario (en Windows resuelve .cmd y .exe; subprocess no lo hace solo)."""
    return shutil.which(name)


def new_group_kwargs():
    """Argumentos de Popen para lanzar un proceso en su propio grupo (para poder pararlo entero)."""
    if WIN:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def kill_tree(pid):
    """Para un proceso y sus hijos. Lanza OSError si no se puede."""
    if WIN:
        r = subprocess.run(["taskkill", "/F", "/T", "/PID", str(int(pid))], capture_output=True)
        if r.returncode != 0:
            raise OSError(f"taskkill falló con código {r.returncode}")
    else:
        os.killpg(int(pid), 15)


def pid_alive(pid):
    try:
        pid = int(pid)
    except (ValueError, TypeError):
        return False
    if WIN:
        # os.kill(pid, 0) en Windows manda Ctrl+C a la consola: no se usa.
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return f" {pid} " in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
