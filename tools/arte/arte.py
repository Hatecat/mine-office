#!/usr/bin/env python3
"""Herramienta de la artista de la oficina: imágenes con ComfyUI (Animagine XL) y modelos 3D (Hunyuan3D 2.1).

Uso:
  arte.py imagen "descripción" [--modelo animagine|flux] [--negativo ...] [--ancho 1024] [--alto 1024] [--pasos N] [--semilla N]
      animagine (por defecto): anime, tags de Danbooru, 28 pasos, ~40 s.
      flux: Flux.1-schnell, entiende frases en inglés (composiciones raras, realismo, objetos), 4 pasos, ~40 s;
            no usa el negativo (workflow en flux_schnell_api.json).
  arte.py modelo3d RUTA_IMAGEN [--resolucion 256] [--pasos 30] [--semilla N]
  arte.py vista MODELO.glb   (render en arcilla desde 3 ángulos, para revisar el resultado)
  arte.py estado
  arte.py parar          (apaga ComfyUI solo si lo arrancó esta herramienta; libera la GPU)

Si ComfyUI no está abierto, lo arranca en segundo plano (sin abrir el navegador). Al terminar cada trabajo
descarga los modelos de la GPU, y si lo arrancó esta herramienta, lo apaga tras 10 minutos sin uso.
Los resultados se copian a ~/Imágenes/oficina/ y se imprime la ruta final en la última línea.
"""
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

HOST = "http://127.0.0.1:8188"
COMFY = os.path.expanduser("~/ComfyUI")
OUT = os.path.expanduser("~/Imágenes/oficina")
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "..", "..", "data")
PIDFILE = os.path.join(STATE, "comfyui.pid")
LOG = os.path.join(STATE, "comfyui.log")
LASTUSE = os.path.join(STATE, "comfyui.lastuse")
IDLE_OFF = int(os.environ.get("ARTE_IDLE_OFF", "600"))         # s sin uso antes de apagar el ComfyUI que arrancamos nosotros

IMG_CKPT = "animagine-xl-4.0-opt.safetensors"
MESH_CKPT = "hunyuan_3d_v2.1.safetensors"
QUALITY = "masterpiece, high score, great score, absurdres"
NEGATIVE = ("lowres, bad anatomy, bad hands, text, error, missing finger, extra digits, fewer digits, cropped, worst quality, "
            "low quality, low score, bad score, average score, signature, watermark, username, blurry")


def say(msg):
    print(msg, flush=True)


def http(path, data=None, headers=None, timeout=30):
    req = urllib.request.Request(HOST + path, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def alive():
    try:
        http("/system_stats", timeout=3)
        return True
    except (urllib.error.URLError, OSError):
        return False


def checkpoints():
    info = json.loads(http("/object_info/CheckpointLoaderSimple"))
    return info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]


def ensure_server():
    if not alive():
        say("ComfyUI no está abierto: lo arranco en segundo plano…")
        os.makedirs(STATE, exist_ok=True)
        env = dict(os.environ, ARGOS_COMPUTE_TYPE="float32")
        with open(LOG, "ab") as log:
            p = subprocess.Popen([os.path.join(COMFY, ".venv/bin/python"), "main.py", "--listen", "127.0.0.1"],
                                 cwd=COMFY, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 start_new_session=True)
        with open(PIDFILE, "w") as f:
            f.write(str(p.pid))
        touch()
        # vigilante aparte: apaga este ComfyUI cuando lleve un rato sin trabajo
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "_vigilar", str(p.pid)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(180):
            if alive():
                break
            if p.poll() is not None:
                sys.exit(f"ComfyUI no arrancó (código {p.returncode}). Mira {LOG}")
            time.sleep(1)
        else:
            sys.exit(f"ComfyUI tarda demasiado en arrancar. Mira {LOG}")
        say("ComfyUI listo.")
    ck = checkpoints()
    if IMG_CKPT not in ck:
        sys.exit("En el puerto 8188 hay un ComfyUI que no es el de ~/ComfyUI (¿el de Krita?): no tiene Animagine. "
                 "Cierra Krita o su servidor y vuelve a intentarlo.")
    return ck


def touch():
    os.makedirs(STATE, exist_ok=True)
    with open(LASTUSE, "w") as f:
        f.write(str(time.time()))


def free_gpu():
    """Descarga los modelos de la VRAM (ComfyUI sigue abierto y los vuelve a cargar si hacen falta)."""
    try:
        http("/free", json.dumps({"unload_models": True, "free_memory": True}).encode(), {"Content-Type": "application/json"})
    except (urllib.error.URLError, OSError):
        pass


def run(prompt, timeout=900):
    touch()
    try:
        return _run(prompt, timeout)
    finally:
        touch()
        free_gpu()


def _run(prompt, timeout):
    pid = json.loads(http("/prompt", json.dumps({"prompt": prompt, "client_id": "oficina"}).encode(),
                          {"Content-Type": "application/json"}))["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = json.loads(http(f"/history/{pid}"))
        if pid in h:
            st = h[pid].get("status") or {}
            if st.get("status_str") == "error":
                msgs = [m[1].get("exception_message", "") for m in st.get("messages", []) if m[0] == "execution_error"]
                sys.exit("ComfyUI dio un error: " + (" ".join(msgs) or "desconocido"))
            return h[pid].get("outputs") or {}
        time.sleep(2)
    sys.exit(f"Se agotó el tiempo ({timeout} s) esperando a ComfyUI")


def files_in(outputs, ext):
    found = []
    def walk(o):
        if isinstance(o, dict):
            if str(o.get("filename", "")).endswith(ext):
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(outputs)
    return found


def fetch(item, name):
    os.makedirs(OUT, exist_ok=True)
    src = os.path.join(COMFY, item.get("type", "output"), item.get("subfolder", ""), item["filename"])
    dst = os.path.join(OUT, name)
    if os.path.exists(src):
        shutil.copy2(src, dst)
    else:
        q = urllib.parse.urlencode({k: item.get(k, "") for k in ("filename", "subfolder", "type")})
        with open(dst, "wb") as f:
            f.write(http(f"/view?{q}", timeout=120))
    return dst


def slug(text, n=40):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:n] or "obra"


FLUX_WF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flux_schnell_api.json")


def flux_graph(a, seed):
    with open(FLUX_WF) as f:
        g = json.load(f)
    unet = os.path.join(COMFY, "models", "unet", g["1"]["inputs"]["unet_name"])
    if not os.path.exists(unet):
        sys.exit(f"Falta el modelo de Flux: {unet}")
    g["3"]["inputs"]["text"] = a.prompt.strip()
    g["5"]["inputs"].update(width=a.ancho, height=a.alto)
    g["6"]["inputs"].update(seed=seed, steps=a.pasos or 4)
    return g


def cmd_imagen(a):
    ensure_server()
    seed = a.semilla if a.semilla is not None else random.randint(1, 2**31)
    if a.modelo == "flux":
        g = flux_graph(a, seed)
        say(f"Generando imagen con Flux {a.ancho}x{a.alto}, {a.pasos or 4} pasos, semilla {seed}…")
        imgs = files_in(run(g, timeout=1200), ".png")
        if not imgs:
            sys.exit("ComfyUI terminó pero no devolvió ninguna imagen")
        dst = fetch(imgs[0], f"{time.strftime('%Y%m%d-%H%M%S')}_flux_{slug(a.prompt)}.png")
        say(f"Semilla: {seed}")
        say(dst)
        return
    a.pasos = a.pasos or 28
    pos = a.prompt.strip().rstrip(",")
    if "masterpiece" not in pos:
        pos += ", " + QUALITY
    g = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": IMG_CKPT}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": pos}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": a.negativo}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": a.ancho, "height": a.alto, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
              "latent_image": ["4", 0], "seed": seed, "steps": a.pasos, "cfg": 5.0, "sampler_name": "euler_ancestral",
              "scheduler": "normal", "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "oficina/img"}},
    }
    say(f"Generando imagen {a.ancho}x{a.alto}, {a.pasos} pasos, semilla {seed}…")
    imgs = files_in(run(g), ".png")
    if not imgs:
        sys.exit("ComfyUI terminó pero no devolvió ninguna imagen")
    dst = fetch(imgs[0], f"{time.strftime('%Y%m%d-%H%M%S')}_{slug(a.prompt)}.png")
    say(f"Semilla: {seed}")
    say(dst)


def upload(path):
    boundary = uuid.uuid4().hex
    name = os.path.basename(path)
    with open(path, "rb") as f:
        data = f.read()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + \
           f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n".encode()
    r = json.loads(http("/upload/image", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=60))
    return (r.get("subfolder") + "/" if r.get("subfolder") else "") + r["name"]


def cmd_modelo3d(a):
    path = os.path.abspath(os.path.expanduser(a.imagen))
    if not os.path.isfile(path):
        sys.exit(f"No existe la imagen: {path}")
    ck = ensure_server()
    if MESH_CKPT not in ck:
        sys.exit(f"Falta el modelo {MESH_CKPT} en ~/ComfyUI/models/checkpoints")
    seed = a.semilla if a.semilla is not None else random.randint(1, 2**31)
    img = upload(path)
    g = {
        "1": {"class_type": "ImageOnlyCheckpointLoader", "inputs": {"ckpt_name": MESH_CKPT}},
        "2": {"class_type": "LoadImage", "inputs": {"image": img}},
        "3": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 1.0}},
        "4": {"class_type": "CLIPVisionEncode", "inputs": {"clip_vision": ["1", 1], "image": ["2", 0], "crop": "center"}},
        "5": {"class_type": "Hunyuan3Dv2Conditioning", "inputs": {"clip_vision_output": ["4", 0]}},
        "6": {"class_type": "EmptyLatentHunyuan3Dv2", "inputs": {"resolution": 4096, "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": {"model": ["3", 0], "positive": ["5", 0], "negative": ["5", 1],
              "latent_image": ["6", 0], "seed": seed, "steps": a.pasos, "cfg": 5.0, "sampler_name": "euler",
              "scheduler": "normal", "denoise": 1.0}},
        "8": {"class_type": "VAEDecodeHunyuan3D", "inputs": {"samples": ["7", 0], "vae": ["1", 2], "num_chunks": 8000,
              "octree_resolution": a.resolucion}},
        "9": {"class_type": "VoxelToMesh", "inputs": {"voxel": ["8", 0], "algorithm": "surface net", "threshold": 0.6}},
        "10": {"class_type": "SaveGLB", "inputs": {"mesh": ["9", 0], "filename_prefix": "3d/oficina"}},
    }
    say(f"Generando modelo 3D (sin textura) desde {os.path.basename(path)}, semilla {seed}. Puede tardar unos minutos…")
    glbs = files_in(run(g, timeout=1500), ".glb")
    if not glbs:
        sys.exit("ComfyUI terminó pero no devolvió ningún .glb")
    dst = fetch(glbs[0], f"{time.strftime('%Y%m%d-%H%M%S')}_{slug(os.path.splitext(os.path.basename(path))[0])}.glb")
    say(f"Semilla: {seed}")
    say(dst)


def cmd_vista(a):
    glb = os.path.abspath(os.path.expanduser(a.modelo))
    if not os.path.isfile(glb):
        sys.exit(f"No existe el modelo: {glb}")
    out = os.path.splitext(glb)[0] + "_vista.png"
    r = subprocess.run(["blender", "-b", "--factory-startup", "--python", os.path.join(HERE, "vista_blender.py"), "--", glb, out],
                       capture_output=True, text=True, timeout=300)
    if not os.path.exists(out):
        sys.exit("Blender no pudo renderizar la vista:\n" + (r.stderr or r.stdout)[-800:])
    say(out)


def cmd_vigilar(a):
    pid = int(a.pid)
    while True:
        time.sleep(30)
        try:
            os.kill(pid, 0)
        except OSError:
            return                                      # ya se cerró
        busy = False
        try:
            q = json.loads(http("/queue", timeout=5))
            busy = bool(q.get("queue_running") or q.get("queue_pending"))
        except (urllib.error.URLError, OSError, ValueError):
            pass
        if busy:
            touch()
            continue
        try:
            last = float(open(LASTUSE).read())
        except (OSError, ValueError):
            last = time.time()
        if time.time() - last > IDLE_OFF:
            try:
                os.killpg(pid, 15)
            except OSError:
                pass
            try:
                if int(open(PIDFILE).read()) == pid:
                    os.remove(PIDFILE)
            except (OSError, ValueError):
                pass
            return


def cmd_estado(_a):
    if not alive():
        say("ComfyUI está cerrado (se abrirá solo al generar algo).")
        return
    ck = checkpoints()
    say("ComfyUI abierto. Modelos: " + ", ".join(c for c in ck if c in (IMG_CKPT, MESH_CKPT)))
    say(f"Resultados en {OUT}")


def cmd_parar(_a):
    try:
        pid = int(open(PIDFILE).read())
    except (OSError, ValueError):
        say("No lo arranqué yo (o ya está parado): no lo toco.")
        return
    try:
        os.killpg(pid, 15)
        say("ComfyUI parado; la GPU queda libre.")
    except OSError:
        say("Ya estaba parado.")
    os.remove(PIDFILE)


def main():
    import urllib.parse  # noqa: F401  (para /view)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("imagen")
    p.add_argument("prompt")
    p.add_argument("--negativo", default=NEGATIVE)
    p.add_argument("--ancho", type=int, default=1024)
    p.add_argument("--alto", type=int, default=1024)
    p.add_argument("--pasos", type=int, help="por defecto 28 con animagine y 4 con flux")
    p.add_argument("--semilla", type=int)
    p.add_argument("--modelo", choices=["animagine", "flux"], default="animagine")
    p = sub.add_parser("modelo3d")
    p.add_argument("imagen")
    p.add_argument("--resolucion", type=int, default=256, help="resolución del octree (más = más detalle y más lento)")
    p.add_argument("--pasos", type=int, default=30)
    p.add_argument("--semilla", type=int)
    p = sub.add_parser("vista")
    p.add_argument("modelo")
    sub.add_parser("estado")
    p = sub.add_parser("_vigilar")
    p.add_argument("pid")
    sub.add_parser("parar")
    a = ap.parse_args()
    {"imagen": cmd_imagen, "modelo3d": cmd_modelo3d, "vista": cmd_vista, "_vigilar": cmd_vigilar, "estado": cmd_estado, "parar": cmd_parar}[a.cmd](a)


if __name__ == "__main__":
    import urllib.parse
    main()
