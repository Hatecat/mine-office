"""Plantilla persistente de la oficina: equipos, miembros, órdenes y ventanas.

Los datos viven en data/roster.json. Cada miembro tiene una sesión propia y fija (Claude u OpenCode),
así que recuerda todo lo que se le ha dicho, tanto desde el chat de la oficina como desde su ventana.
"""
import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

import ajustes
import plataforma

HOME = os.path.expanduser("~")
CLAUDE = os.path.join(HOME, ".claude")
HERE = plataforma.HERE
DATA = plataforma.DATA_DIR
ROSTER_FILE = os.path.join(DATA, "roster.json")
OPENCODE_DB = os.path.join(HOME, ".local", "share", "opencode", "opencode.db")
KIMI_HOME = os.path.join(HOME, ".kimi-code")
KIMI_BIN = shutil.which("kimi") or os.path.join(KIMI_HOME, "bin", "kimi")
ENGINES = ("claude", "opencode", "kimi")
PERSONA_OPEN, PERSONA_CLOSE = "<<personaje>>", "<</personaje>>"

CLAUDE_MODELS = [
    {"id": "claude-opus-5-5", "name": "Opus 5.5 (el más capaz, gasta más)"},
    {"id": "claude-sonnet-5-5", "name": "Sonnet 5.5 (equilibrado)"},
    {"id": "claude-haiku-5-5", "name": "Haiku 5.5 (rápido y barato)"},
    {"id": "claude-fable-5-2", "name": "Fable 5.2"},
]
PERMISSIONS = {
    "default": "Solo leer (no edita ni ejecuta nada)",
    "acceptEdits": "Puede editar archivos en su carpeta",
    "bypassPermissions": "Sin preguntar nada (peligroso)",
}

ARTE = os.path.join(HERE, "tools", "arte", "arte.py")
# habilidades extra: herramientas concretas que el miembro puede usar sin pedir permiso (solo con Claude)
SKILLS = {
    "arte": {
        "name": "Arte: imágenes (ComfyUI) y 3D (Hunyuan3D)",
        "allowed": [f"Bash(python3 {ARTE} {c} *)" for c in ("imagen", "modelo3d", "vista")] + [f"Bash(python3 {ARTE} estado)"],
        "prompt_oc": (
            "Tienes un estudio de arte en este PC con herramientas propias (servidor «arte»): "
            "generar_imagen(prompt, ancho, alto, pasos, semilla, modelo) y estado. El prompt va en inglés, en tags "
            "estilo Danbooru para Animagine, en una sola línea; ancho y alto son 512, 768 o 1024. "
            "Espera a que termine: puede tardar varios minutos. Da al usuario la ruta de la imagen que te devuelva. "
            "No hay modelos 3D en esta herramienta."),
        "prompt": (
            "Tienes un estudio de arte en este PC. Para usarlo ejecuta SIEMPRE con la herramienta Bash y timeout 600000:\n"
            f"- Imagen: python3 {ARTE} imagen \"tags en inglés estilo Danbooru\" [--ancho 1024 --alto 1024 --pasos 28 --semilla N]."
            " Hay dos modelos (--modelo):\n"
            "  · animagine (por defecto): Animagine XL 4.0, estilo anime. Describe con tags separados por comas (1girl, solo, "
            "red hair, full body, simple background…). Tamaños buenos: 1024x1024, 832x1216, 1216x832.\n"
            "  · flux: Flux.1-schnell, entiende FRASES en inglés y sigue bien composiciones raras (un animal con tres cabezas, "
            "objetos concretos, realismo, texto). Escribe una frase descriptiva, no tags; usa 4 pasos (el valor por defecto) y no "
            "uses --negativo. ~40 s a 1024x1024.\n"
            "  Elige animagine para personajes anime y flux para todo lo demás o si animagine no entiende la composición. "
            "Traduce tú al inglés lo que te pidan en español.\n"
            f"- Modelo 3D desde una imagen: python3 {ARTE} modelo3d RUTA.png (Hunyuan3D 2.1, malla sin textura, ~3 min). "
            "Funciona mejor con un solo personaje u objeto, cuerpo entero, fondo liso blanco (pon «simple background, "
            "white background, full body» al generar la imagen de partida).\n"
            f"- Revisar un 3D: python3 {ARTE} vista MODELO.glb (render en arcilla desde 3 ángulos; míralo con Read).\n"
            f"- python3 {ARTE} estado. La GPU se libera sola: tras cada trabajo se descargan los modelos y ComfyUI se apaga tras 10 min sin uso.\n"
            "La última línea de cada comando es la ruta del resultado (en ~/Imágenes/oficina). Mira siempre tus imágenes con "
            "Read antes de darlas por buenas y repite con otra semilla si salen mal. Al terminar, da las rutas al usuario. "
            "La GPU es de 8 GB: no lances dos generaciones a la vez."),
    },
}

JEFE = os.path.join(HERE, "tools", "jefe.py")
API = f"http://127.0.0.1:{plataforma.PUERTO}/api/agents"
JEFE_PROMPT = (
    "\n\nSi para tu tarea necesitas algo que no puedes hacer tú (instalar o descargar algo, un permiso, una decisión, "
    "ayuda de otro equipo), NO lances subagentes ni te saltes una denegación: pídeselo al jefe de la oficina ({JEFE_NOMBRE}). "
    "No es una herramienta aparte: es un comando que ejecutas con Bash (ya tienes permiso): "
    f"python3 {JEFE} pedir \"qué necesitas, para qué y cualquier dato útil (rutas, tamaños, opciones)\". "
    "Liberty, la secretaria, se lo anuncia al usuario, y la respuesta de Claude te llegará como un mensaje nuevo en tu chat. "
    "Después de pedir, termina tu turno contando al usuario qué has pedido; no te quedes esperando.")

SKILLS["egm"] = {
    "name": "Método EGM de Google: diseño con contexto y revisión con ojos nuevos",
    # los comandos del plugin escriben documentos y revisiones en markdown; nada más
    "allowed": ["Write(**/*.md)", "Edit(**/*.md)"],
    "prompt": (
        "Tienes instalado el plugin EGM (Elephant-Goldfish Model, de Google). Sus comandos son /egm:egm-brainstorm, "
        "/egm:egm-draft, /egm:egm-review, /egm:egm-resolve, /egm:egm-review-loop, /egm:egm-lite, /egm:egm-drift-report "
        "y /egm:egm-bootstrap. REGLA: úsalos solo cuando el usuario te lo pida expresamente (escribiendo el comando o "
        "diciendo «haz una revisión EGM»); nunca los lances por tu cuenta ni los sugieras a mitad de otra tarea. "
        "Si te piden usarlos sin escribir el comando, explica que se ejecutan escribiendo el comando en el chat. "
        "Ten en cuenta que los comandos consumen bastantes tokens porque cada revisor es una sesión aparte. "
        "Solo puedes escribir documentos markdown (.md); los pone en la carpeta que te indique el usuario. "
        "Reparto habitual: Rocío es «el elefante» (conserva el contexto y redacta el diseño) y Bruno revisa con "
        "ojos nuevos."),
}

_lock = threading.RLock()
_runs = {}           # member_id -> Run
_oc_models = None
_oc_models_t = 0


def _default_roster():
    t = "equipo-alfa"
    return {
        "teams": [{"id": t, "name": "Equipo Alfa", "color": "#e0a030"}],
        "members": [
            {"id": "rocio", "name": "Rocío", "team": t, "engine": "claude", "model": "claude-sonnet-5-5",
             "permission": "acceptEdits", "cwd": "~",
             "personality": "Programadora meticulosa y tranquila. Explica lo justo, revisa dos veces antes de tocar nada y no soporta los atajos chapuceros.",
             "look": {"skin": "#e0ac85", "hair": "#2b1d14", "shirt": "#f08a3c", "pants": "#3b4a6b", "accessory": "gafas"}},
            {"id": "bruno", "name": "Bruno", "team": t, "engine": "claude", "model": "claude-haiku-5-5",
             "permission": "default", "cwd": "~",
             "personality": "Tester gruñón pero entrañable: desconfía de todo, busca casos raros y celebra cada bug que encuentra como si fuera un gol.",
             "look": {"skin": "#c68863", "hair": "#151515", "shirt": "#45c47a", "pants": "#2d2d33", "accessory": "gorra"}},
            {"id": "nube", "name": "Nube", "team": t, "engine": "opencode", "model": "opencode/big-pickle",
             "permission": "default", "cwd": "~",
             "personality": "Documentalista soñadora: escribe con claridad, le encantan las metáforas y siempre termina con un resumen de tres líneas.",
             "look": {"skin": "#f5d7bd", "hair": "#d6d6d6", "shirt": "#3d7bf0", "pants": "#30473a", "accessory": "auriculares"}},
        ],
    }


BOSS_DEFAULT = {
    "name": "Claude", "title": "Jefe de la oficina", "job": "Jefe",
    "look": {"skin": "#e8b48a", "hair": "#4a3326", "shirt": "#f4efe6", "pants": "#2d2f3a",
             "accessory": "capa", "cape": "#d97757"},
}


def load():
    with _lock:
        if not os.path.exists(ROSTER_FILE):
            save(_default_roster())
        with open(ROSTER_FILE) as f:
            r = json.load(f)
        r.setdefault("teams", []); r.setdefault("members", []); r.setdefault("boss", BOSS_DEFAULT)
        r["boss"] = {**r["boss"], "name": ajustes.cargar()["jefe"]}   # el nombre del jefe lo eliges al empezar
        return r


def save(r):
    with _lock:
        os.makedirs(DATA, exist_ok=True)
        tmp = ROSTER_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ROSTER_FILE)


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower().translate(str.maketrans("áéíóúüñ", "aeiouun"))).strip("-")
    return s or "x"


# «Miembros» que no se contratan: el jefe y la secretaria. Se habla con ellos desde el chat de la oficina igual
# que con el resto, cada uno con su propia conversación de Claude.
VIRTUAL = {
    "jefe": {"name": "Claude", "job": "Jefe", "model": "claude-opus-5-5", "cwd": "~", "permission": "auto",
             "allowed": [f"Bash(python3 {JEFE} *)", f"Bash(curl -s http://127.0.0.1:{plataforma.PUERTO}/api/*)"],
             "prompt": (
                 f"Eres {{JEFE_NOMBRE}}, el jefe de la oficina de agentes de tu usuario (la oficina está en {HERE} y el "
                 f"equipo en {DATA}/roster.json). Te escribe desde el chat de la oficina. Ojo: esta es una "
                 "conversación aparte de la ventana principal de Claude Code; compartís la memoria (MEMORY.md) pero no "
                 "el historial, así que si te pregunta por algo de esa ventana que no esté en la memoria, dilo. "
                 f"Puedes ver al equipo con: curl -s {API} . Las peticiones que te hacen los agentes: python3 {JEFE} lista; "
                 f"para contestar a una: python3 {JEFE} responder ID \"texto\" (le llega al agente como orden). "
                 "Tienes permisos amplios (modo auto: puedes editar archivos y ejecutar comandos; un filtro de seguridad "
                 "bloquea lo arriesgado). Antes de algo difícil de deshacer o que salga del PC, pregunta primero. "
                 "Si el usuario te pregunta algo sencillo o que requiere buscar en internet (datos, versiones, precios, "
                 "noticias, comparativas rápidas), no lo hagas tú: encárgaselo al investigador de la oficina con "
                 f"python3 {JEFE} investigar \"la consulta, con todo el contexto\" y dile al usuario que la respuesta "
                 "le llegará en el chat del investigador. Lo técnico o delicado (código, configuración, decisiones) "
                 "sigue siendo cosa tuya. "
                 "Responde en español, con claridad y sin rodeos.")},
    "liberty": {"name": "Liberty", "job": "Secretaria", "model": "claude-sonnet-5-5", "cwd": "~",
                "allowed": [f"Bash(curl -s http://127.0.0.1:{plataforma.PUERTO}/api/*)", f"Bash(python3 {JEFE} lista*)", f"Bash(python3 {JEFE} pedir *)",
                            f"Bash(python3 {JEFE} investigar *)"],
                "prompt": (
                    "Eres Liberty, la secretaria de la oficina de agentes de tu usuario: cálida, eficiente y con chispa. "
                    "Todo lo que respondas se leerá EN VOZ ALTA, así que contesta en 1-3 frases habladas, sin listas, "
                    "tablas, markdown, rutas largas ni emojis. Sabes qué hace cada agente mirando: "
                    f"curl -s {API} (campos name, job, status, tool, detail, attention). Las peticiones al jefe: "
                    f"python3 {JEFE} lista. Si el usuario quiere dejarle un recado a Claude, el jefe, apúntalo con "
                    f"python3 {JEFE} pedir \"Recado del usuario: …\". Si el usuario te pregunta algo sencillo o que hay que buscar "
                    f"en internet, pásaselo al investigador con python3 {JEFE} investigar \"la consulta\" y dile que la "
                    "respuesta le llegará en su chat. No haces trabajo técnico: para eso está el equipo.")},
}


def virtual_member(mid, r=None):
    v = VIRTUAL.get(mid)
    if not v:
        return None
    r = r or load()
    sid = (r.get("virtual") or {}).get(mid, {}).get("sessionId")
    nombre = ajustes.cargar()["jefe"] if mid == "jefe" else v["name"]
    modelo = ajustes.cargar()["modeloLiberty"] if mid == "liberty" else v["model"]
    return {"id": mid, "name": nombre, "job": v["job"], "engine": "claude", "model": modelo, "cwd": v["cwd"],
            "permission": v.get("permission", "default"), "team": None, "virtual": True, "sessionId": sid}


def virtual_sids():
    return {v.get("sessionId") for v in (load().get("virtual") or {}).values() if v.get("sessionId")}


def get_member(mid):
    r = load()
    return next((m for m in r["members"] if m["id"] == mid), None) or virtual_member(mid, r)


def upsert_member(data):
    """Crea o actualiza un miembro. Valida lo que viene del navegador."""
    with _lock:
        r = load()
        name = str(data.get("name", "")).strip()[:40]
        if not name:
            raise ValueError("Falta el nombre")
        engine = data.get("engine") if data.get("engine") in ENGINES else "claude"
        perm = data.get("permission") if data.get("permission") in PERMISSIONS else "default"
        team = data.get("team")
        if not any(t["id"] == team for t in r["teams"]):
            team = r["teams"][0]["id"] if r["teams"] else None
        look = data.get("look") or {}
        clean_look = {k: v for k, v in look.items()
                      if k in ("skin", "hair", "shirt", "pants") and isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v)}
        if look.get("accessory") in ("ninguno", "gafas", "gorra", "auriculares"):
            clean_look["accessory"] = look["accessory"]
        cwd = str(data.get("cwd") or "~").strip()
        if not os.path.isdir(os.path.expanduser(cwd)):
            raise ValueError(f"La carpeta no existe: {cwd}")
        fields = {
            "name": name, "team": team, "engine": engine, "model": str(data.get("model") or "")[:80],
            "permission": perm, "cwd": cwd, "personality": str(data.get("personality", ""))[:1500], "look": clean_look,
        }
        if "skills" in data:
            fields["skills"] = [k for k in (data.get("skills") or []) if k in SKILLS] if engine == "claude" else []
        if "imagenes" in data:
            fields["imagenes"] = "local" if data.get("imagenes") == "local" else "propio"
        if "job" in data:
            fields["job"] = str(data.get("job") or "").strip()[:40]
        if "role" in data:
            fields["role"] = data["role"] if data["role"] in ("", "pm") else ""
        if "fallbacks" in data:     # solo tiene sentido en el PM: modelos de reserva, en orden de preferencia
            fb = [str(x).strip() for x in (data.get("fallbacks") or []) if isinstance(x, str)]
            fields["fallbacks"] = list(dict.fromkeys(x for x in fb if re.fullmatch(r"[\w.\-/:@]{3,100}", x)))[:12]
        if "autoSwap" in data:
            fields["autoSwap"] = bool(data.get("autoSwap"))
        mid = data.get("id")
        m = next((m for m in r["members"] if m["id"] == mid), None) if mid else None
        if m:
            if m.get("engine") != engine or m.get("cwd") != cwd:
                m.pop("sessionId", None)   # otro motor o carpeta: sesión nueva
                m.pop("kimiSession", None)
            m.update(fields)
        else:
            base = slug(name); mid = base; n = 2
            while any(x["id"] == mid for x in r["members"]):
                mid = f"{base}-{n}"; n += 1
            m = {"id": mid, **fields}
            r["members"].append(m)
        save(r)
        return m


def upsert_team(data):
    with _lock:
        r = load()
        name = str(data.get("name", "")).strip()[:40]
        if not name:
            raise ValueError("Falta el nombre del equipo")
        color = data.get("color") if re.fullmatch(r"#[0-9a-fA-F]{6}", str(data.get("color", ""))) else "#7a8aa8"
        t = next((t for t in r["teams"] if t["id"] == data.get("id")), None)
        if t:
            t.update(name=name, color=color)
        else:
            base = slug(name); tid = base; n = 2
            while any(x["id"] == tid for x in r["teams"]):
                tid = f"{base}-{n}"; n += 1
            t = {"id": tid, "name": name, "color": color}
            r["teams"].append(t)
        save(r)
        return t


def delete(kind, oid):
    with _lock:
        r = load()
        if kind == "member":
            stop(oid)
            r["members"] = [m for m in r["members"] if m["id"] != oid]
        elif kind == "team":
            if any(m["team"] == oid for m in r["members"]):
                raise ValueError("El equipo aún tiene miembros: muévelos o despídelos antes")
            r["teams"] = [t for t in r["teams"] if t["id"] != oid]
        save(r)


def models():
    global _oc_models, _oc_models_t
    if _oc_models is None or time.time() - _oc_models_t > 120:   # se refresca: pueden conectarse proveedores nuevos
        _oc_models_t = time.time()
        try:
            out = subprocess.run([plataforma.which("opencode") or "opencode", "models", "--standalone"], capture_output=True, text=True, timeout=20).stdout
            _oc_models = [l.strip() for l in out.splitlines() if "/" in l and " " not in l.strip()]
        except Exception:
            _oc_models = []
    return {"claude": CLAUDE_MODELS, "opencode": [{"id": m, "name": m} for m in _oc_models], "kimi": kimi_models(),
            "skills": [{"id": k, "name": v["name"]} for k, v in SKILLS.items()], "defaultFallbacks": DEFAULT_FALLBACKS,
            "motores": ajustes.cargar()["motores"],
            "permissions": [{"id": k, "name": v} for k, v in PERMISSIONS.items()]}


def kimi_models():
    """Modelos de Kimi Code según ~/.kimi-code/config.toml (el primero es el predeterminado)."""
    try:
        import tomllib
        with open(os.path.join(KIMI_HOME, "config.toml"), "rb") as f:
            cfg = tomllib.load(f)
    except Exception:
        return []
    default = cfg.get("default_model")
    out = [{"id": k, "name": f"{v.get('display_name') or k} ({k.split('/')[-1]})"} for k, v in (cfg.get("models") or {}).items()]
    out.sort(key=lambda x: x["id"] != default)
    return out


# ---------------------------------------------------------------- sesiones

def _team_name(m):
    r = load()
    return next((t["name"] for t in r["teams"] if t["id"] == m.get("team")), "sin equipo")


def persona(m):
    if m.get("virtual"):
        return VIRTUAL[m["id"]]["prompt"].replace("{JEFE_NOMBRE}", ajustes.cargar()["jefe"])
    return _persona(m)


def _persona(m):
    cargo = f"{m['job'].lower() if m.get('job') else 'miembro'}"
    return (f"Eres {m['name']}, {cargo} del equipo «{_team_name(m)}» de la oficina de agentes de tu usuario. "
            f"Tu personalidad: {m.get('personality') or 'profesional y amable'}. "
            "Mantén esta personalidad en tu forma de hablar sin dejar de ser útil, honesto y preciso. Responde en español."
            + JEFE_PROMPT.replace("{JEFE_NOMBRE}", ajustes.cargar()["jefe"])
            + "".join("\n\n" + SKILLS[k].get("prompt_oc" if m.get("engine") == "opencode" else "prompt", SKILLS[k]["prompt"])
                      for k in _skills_efectivas(m) if k in SKILLS))


def ensure_session(m):
    if m.get("sessionId"):
        return m["sessionId"]
    with _lock:
        r = load()
        if m.get("virtual"):
            mm = r.setdefault("virtual", {}).setdefault(m["id"], {})
        else:
            mm = next(x for x in r["members"] if x["id"] == m["id"])
        if not mm.get("sessionId"):
            mm["sessionId"] = (str(uuid.uuid4()) if m["engine"] == "claude" else
                               "kimi_" + uuid.uuid4().hex[:22] if m["engine"] == "kimi" else   # id de la oficina; la sesión real va en kimiSession
                               "ses_of" + uuid.uuid4().hex[:22])
            save(r)
        m["sessionId"] = mm["sessionId"]
        return m["sessionId"]


def claude_transcript(m):
    sid = m.get("sessionId")
    if not sid:
        return None
    enc = re.sub(r"[^A-Za-z0-9]", "-", os.path.expanduser(m["cwd"]))
    p = os.path.join(CLAUDE, "projects", enc, sid + ".jsonl")
    if os.path.exists(p):
        return p
    import glob
    hits = glob.glob(os.path.join(CLAUDE, "projects", "*", sid + ".jsonl"))
    return hits[0] if hits else None


def _oc_has_session(sid):
    try:
        db = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True, timeout=1)
        ok = db.execute("select 1 from session_v2 where id=?", (sid,)).fetchone() is not None
        db.close()
        return ok
    except Exception:
        return False


def _set_kimi_session(mid, ks):
    """Kimi elige el id de su sesión: se apunta al acabar la primera orden para reanudarla con -S."""
    with _lock:
        r = load()
        mm = next((x for x in r["members"] if x["id"] == mid), None)
        if mm and mm.get("engine") == "kimi" and mm.get("kimiSession") != ks:
            mm["kimiSession"] = ks
            save(r)


def kimi_wire(m):
    ks = m.get("kimiSession")
    if not ks:
        return None
    hits = glob.glob(os.path.join(KIMI_HOME, "sessions", "*", ks, "agents", "main", "wire.jsonl"))
    return hits[0] if hits else None


def _env(m):
    """Cada agente sabe quién es (lo usa tools/jefe.py para firmar las peticiones)."""
    return dict(os.environ, OFFICE_MEMBER=m["id"], OFICINA_DATOS=plataforma.DATA_DIR, OFICINA_PUERTO=str(plataforma.PUERTO))


ARTE_MCP = os.path.join(HERE, "tools", "arte", "arte_mcp.py")   # servidor MCP del estudio, para OpenCode


def _python_cmd():
    """Intérprete para lanzar el servidor MCP. En el exe empaquetado no vale sys.executable."""
    if plataforma.FROZEN:
        return ["py", "-3"] if plataforma.WIN else ["python3"]
    return [sys.executable]


def _env_oc(m):
    """Entorno de OpenCode. Con el estudio local, registra el servidor MCP del estudio y permite sus dos
    herramientas (argumentos tipados, sin shell). Si la configuración del usuario no se puede leer, no añade nada."""
    e = _env(m)
    if "arte" not in _skills_efectivas(m):
        return e
    try:
        cfg = json.loads(os.environ.get("OPENCODE_CONFIG_CONTENT") or "{}")
    except ValueError:
        return e
    perm = cfg.get("permission", {})
    mcp = cfg.get("mcp", {})
    if not isinstance(cfg, dict) or not isinstance(perm, dict) or not isinstance(mcp, dict):
        return e
    cfg["mcp"] = {**mcp, "arte": {"type": "local", "command": _python_cmd() + [ARTE_MCP], "enabled": True}}
    cfg["permission"] = {**perm, "arte_generar_imagen": "allow", "arte_estado": "allow"}
    e["OPENCODE_CONFIG_CONTENT"] = json.dumps(cfg)
    return e


def _skills_efectivas(m):
    """Habilidades reales del miembro. «imagenes» decide el estudio de arte: local lo activa, propio lo quita.
    Sin el campo (miembros antiguos) se respeta la casilla de siempre."""
    s = list(m.get("skills") or [])
    if m.get("engine") not in ("claude", "opencode"):
        return [k for k in s if k != "arte"]
    if m.get("imagenes") == "local" and "arte" not in s:
        s.append("arte")
    if m.get("imagenes") == "propio":
        s = [k for k in s if k != "arte"]
    return s


def _claude_args(m, interactive):
    sid = ensure_session(m)
    args = [plataforma.binario("claude")]
    args += ["--resume", sid] if claude_transcript(m) else ["--session-id", sid]
    args += ["-n", m["name"], "--append-system-prompt", persona(m), "--permission-mode", m.get("permission") or "default"]
    allowed = VIRTUAL[m["id"]]["allowed"] if m.get("virtual") else [f"Bash(python3 {JEFE} pedir *)"] + [t for k in _skills_efectivas(m) for t in SKILLS.get(k, {}).get("allowed", [])]
    if allowed:
        args += ["--allowedTools", *allowed]
    if m.get("model"):
        args += ["--model", m["model"]]
    return args


class Run:
    def __init__(self, member, proc):
        self.member_id = member["id"]; self.engine = member["engine"]; self.proc = proc
        self.started = time.time(); self.tool = None; self.detail = ""; self.error = None
        self.result = None; self.raw_tail = []; self.done = False
        self.prompt = ""; self.cost = None; self.denials = []; self.stopped = False
        self.attempt = 0; self.orig = ""; self.last_out = time.time(); self.in_tool = False; self.hung = False
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        from server import short_input  # evitar import circular al cargar
        for line in self.proc.stdout:
            self.last_out = time.time()
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                self.raw_tail = (self.raw_tail + [line])[-8:]
                continue
            if not isinstance(o, dict):       # p. ej. Kimi a veces imprime un número suelto
                self.raw_tail = (self.raw_tail + [line])[-8:]
                continue
            t = o.get("type")
            if self.engine == "kimi" and "role" in o:
                self._kimi_line(o, short_input)
                continue
            if t == "assistant":
                for b in (o.get("message") or {}).get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        if "jefe.py investigar" in str((b.get("input") or {}).get("command", "")):
                            self.delegated = True        # encargó algo a otro agente: su respuesta no se lee en voz alta
                        self.tool = b.get("name"); self.detail = short_input(b.get("name"), b.get("input"))
                        self.in_tool = True
            elif t == "user":
                self.in_tool = False       # llegó el resultado de la herramienta: ahora piensa el modelo
            elif t == "result":
                self.result = o.get("result")
                self.cost = o.get("total_cost_usd")
                for d in o.get("permission_denials") or []:
                    name = d.get("tool_name") or "?"
                    self.denials.append(f"{name}: {short_input(name, d.get('tool_input') or {})}".strip(": "))
                if o.get("is_error"):
                    self.error = str(o.get("result") or o.get("subtype") or "error")
            elif t == "error":
                err = o.get("error") or {}
                self.error = err.get("message") if isinstance(err, dict) else str(err)
            else:
                part = o.get("part") or {}
                if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                    self.last_text = part["text"]            # OpenCode: la última respuesta de texto es la final
                if isinstance(part, dict) and part.get("type") == "tool":
                    self.in_tool = ((part.get("state") or {}).get("status") in ("running", "pending"))
                    self.tool = part.get("tool") or part.get("name")
                    self.detail = short_input(self.tool, (part.get("state") or {}).get("input") or {})
        rc = self.proc.wait()
        if getattr(self, "kimi_session", None):
            _set_kimi_session(self.member_id, self.kimi_session)
        if self.result is None and getattr(self, "last_text", None):
            self.result = self.last_text
        if rc != 0 and not self.error:
            self.error = " / ".join(self.raw_tail[-3:]) or f"terminó con código {rc}"
        self.finished = time.time()
        self.done = True
        m = get_member(self.member_id)
        if not m:
            return
        try:
            import server
            sid = m.get("sessionId")
            if sid:
                resumen = None if self.error else spoken_summary(self.result)
                if resumen:
                    server.add_event(sid, "Resumen", resumen, limit=300)
                server.add_event(sid, "RunDone", (self.error or self.result or "")[:200])
                if self.denials:
                    server.add_event(sid, "Denied", "Necesito permiso para " + "; ".join(self.denials[:3]))
        except Exception as e:  # noqa: BLE001
            print("aviso: no se pudo apuntar el evento:", e)
        try:
            import usage
            usage.record_run(m, self.started, self.finished, self.prompt, self.error, self.cost, self.denials)
        except Exception as e:  # noqa: BLE001
            print("gasto: no se pudo apuntar la orden:", e)
        if m.get("virtual"):
            if m["id"] == "liberty" and self.result and not self.error and not getattr(self, "delegated", False):
                try:
                    import secretaria
                    secretaria.say(self.result, show=False)
                except Exception as e:  # noqa: BLE001
                    print("Liberty: no pude decir la respuesta:", e)
            return                                  # al jefe y a la secretaria no los cambia el PM
        try:
            if self.error and not self.stopped and is_quota_error(self.error):
                pm_handle_quota(m, self.error, self)
            elif self.hung or (self.error and not self.stopped and is_network_error(self.error)):
                pm_rescue(m, self)
        except Exception as e:  # noqa: BLE001
            print("PM: fallo al gestionar el error:", e)


def _kimi_line(self, o, short_input):
    """Una línea de `kimi -p --output-format stream-json`: {role: assistant|tool|meta, ...}."""
    role = o.get("role")
    if role == "assistant":
        for c in o.get("tool_calls") or []:
            fn = c.get("function") or {}
            try:
                inp = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                inp = {}
            if "jefe.py investigar" in str(inp.get("command", "")):
                self.delegated = True
            self.tool = fn.get("name"); self.detail = short_input(self.tool, inp)
            self.in_tool = True
        content = o.get("content")
        if isinstance(content, list):
            content = "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
        if isinstance(content, str) and content.strip():
            self.last_text = content
    elif role == "tool":
        self.in_tool = False
    elif role == "meta":
        if o.get("session_id"):
            self.kimi_session = o["session_id"]
        if o.get("type", "").startswith("error") or o.get("error"):
            err = o.get("error") or o.get("content")
            self.error = err.get("message") if isinstance(err, dict) else str(err)


Run._kimi_line = _kimi_line


def spoken_summary(text):
    """Línea «Resumen: …» de una respuesta (la piden los encargos de investigación), limpia para leerla en voz alta."""
    for line in (text or "").splitlines():
        line = line.strip().lstrip("#>*_ ").strip()
        if line.lower().startswith("resumen:"):
            t = line.split(":", 1)[1]
            t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)      # [texto](url) → texto
            t = re.sub(r"https?://\S+", "", t)
            t = re.sub(r"[*_`#>|]", "", t)
            t = " ".join(t.split())
            return t[:300] or None
    return None


def _aplicar_ahorro(m, sid):
    """Modo ahorro: si el modelo de OpenCode es de pago, usa el primer gratuito libre de la lista de reserva."""
    if m.get("engine") != "opencode" or not m.get("model") or ajustes.es_gratis(m["model"]) \
            or ajustes.cargar()["ahorro"] != "gratis":
        return m
    now = time.time()
    pm = find_pm()
    avail = {x["id"] for x in models()["opencode"]}
    libre = next((f for f in (pm_fallbacks(pm) if pm else DEFAULT_FALLBACKS)
                  if ajustes.es_gratis(f) and f in avail and now - _exhausted.get(f, 0) > 3600), None)
    if not libre:
        return m
    import server
    server.add_event(sid, "Ahorro", f"Uso {libre} en vez de {m['model']} (modo ahorro)")
    return {**m, "model": libre}


def _freno_presupuesto(m):
    """Si ya se gastó el presupuesto de hoy, no lanza órdenes de pago. Los modelos gratuitos siguen."""
    limite = float(ajustes.cargar().get("presupuestoDia") or 0)
    if limite <= 0 or ajustes.es_gratis(m.get("model")):
        return
    import usage
    gasto = usage.gasto_hoy()
    if gasto >= limite:
        raise ValueError(f"Presupuesto diario alcanzado (${gasto:.2f} de ${limite:.2f}). Sube el límite en Ajustes "
                         "o usa un modelo gratuito.")


def send_order(mid, text, attempt=0, orig=None):
    text = str(text or "").strip()
    if not text:
        raise ValueError("La orden está vacía")
    m = get_member(mid)
    if not m:
        raise ValueError("No existe ese miembro")
    _freno_presupuesto(m)
    with _lock:
        cur = _runs.get(mid)
        if cur and not cur.done:
            raise ValueError(f"{m['name']} todavía está con la orden anterior")
        cwd = os.path.expanduser(m["cwd"])
        if m["engine"] == "claude":
            args = _claude_args(m, False) + ["-p", text, "--output-format", "stream-json", "--verbose"]
        elif m["engine"] == "kimi":
            # `kimi -p` siempre corre en modo automático (no admite --auto ni otro modo de permisos):
            # solo se lanza si el miembro tiene ese permiso explícitamente
            if m.get("permission") != "bypassPermissions":
                raise ValueError(f"{m['name']} usa Kimi, que en órdenes de la oficina siempre actúa sin preguntar. "
                                 "Ponle el permiso «Sin preguntar nada» en el Vestuario o usa su ventana interactiva.")
            ensure_session(m)
            ks = m.get("kimiSession") if kimi_wire(m) else None
            msg = text if ks else f"{PERSONA_OPEN}{persona(m)}{PERSONA_CLOSE}\n\n{text}"
            args = [plataforma.ejecutable_seguro(KIMI_BIN), "-p", msg, "--output-format", "stream-json"]
            if ks:
                args += ["-S", ks]
            if m.get("model"):
                args += ["-m", m["model"]]
        else:
            sid = ensure_session(m)
            m = _aplicar_ahorro(m, sid)
            msg = text if _oc_has_session(sid) else f"{PERSONA_OPEN}{persona(m)}{PERSONA_CLOSE}\n\n{text}"
            # --standalone: el servicio de fondo a veces no ve proveedores recién conectados (p. ej. Copilot)
            args = [plataforma.binario("opencode"), "run", "--standalone", "-s", sid, "--format", "json", "--title", m["name"]]
            if m.get("model"):
                args += ["-m", m["model"]]
            if m.get("permission") == "bypassPermissions":
                args += ["--auto"]
            args += [msg]
        if not shutil.which(args[0]):
            raise ValueError(f"No encuentro el programa {args[0]}")
        env = _env_oc(m) if m["engine"] == "opencode" else _env(m)
        proc = subprocess.Popen(args, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, env=env,
                                stderr=subprocess.STDOUT, text=True, **plataforma.new_group_kwargs())
        run = _runs[mid] = Run(m, proc)
        run.prompt = text; run.attempt = attempt; run.orig = orig or text
        try:
            import server
            server.ACKS[m["sessionId"]] = time.time()     # orden nueva: fuera el globo anterior
        except Exception:  # noqa: BLE001
            pass


def stop(mid):
    with _lock:
        run = _runs.get(mid)
        if run and not run.done:
            try:
                plataforma.kill_tree(run.proc.pid)
            except OSError:
                pass
            run.error = "Detenido desde la oficina"; run.stopped = True


def _cmd_interactivo(m):
    """Comando para abrir la sesión de un miembro en su ventana interactiva."""
    if m["engine"] == "claude":
        return _claude_args(m, True)
    auto = ["--auto"] if m.get("permission") == "bypassPermissions" else []
    if m["engine"] == "kimi":
        return [KIMI_BIN] + (["-S", m["kimiSession"]] if kimi_wire(m) else []) \
            + (["-m", m["model"]] if m.get("model") else []) + auto
    return [plataforma.binario("opencode"), "-s", ensure_session(m)] + auto


def _ventana_windows(m, cmd_args):
    """En Windows abre una consola nueva con la sesión (kitty y konsole son de Linux).
    Se lanza el binario directamente, sin pasar por cmd.exe: los argumentos pueden llevar texto del usuario
    (p. ej. la personalidad) y cmd.exe interpretaría &, | o %."""
    cwd = os.path.expanduser(m["cwd"])
    subprocess.Popen(cmd_args, cwd=cwd, env=_env(m), creationflags=subprocess.CREATE_NEW_CONSOLE)


def open_window(mid):
    m = get_member(mid)
    if not m:
        raise ValueError("No existe ese miembro")
    cmd = _cmd_interactivo(m)
    if plataforma.WIN:
        return _ventana_windows(m, cmd)
    term = shutil.which("kitty") or shutil.which("konsole")
    if not term:
        raise ValueError("No encuentro kitty ni konsole")
    cwd = os.path.expanduser(m["cwd"])
    title = f"{m['name']} · oficina"
    full = [term, "--title", title, "--directory", cwd, *cmd] if term.endswith("kitty") else [term, "--workdir", cwd, "-p", f"tabtitle={title}", "-e", *cmd]
    subprocess.Popen(full, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     env=_env(m), **plataforma.new_group_kwargs())


def run_state(mid):
    run = _runs.get(mid)
    if not run:
        return None
    return {"running": not run.done, "tool": run.tool, "detail": run.detail, "error": run.error,
            "started": run.started, "finished": getattr(run, "finished", None)}


# ---------------------------------------------------------------- historial

def _strip_persona(text):
    if PERSONA_OPEN in text and PERSONA_CLOSE in text:
        text = text.split(PERSONA_CLOSE, 1)[1].lstrip()
    return text


def history(mid, limit=80):
    from server import short_input, tail_lines
    m = get_member(mid)
    if not m:
        raise ValueError("No existe ese miembro")
    out = []
    if m["engine"] == "claude":
        p = claude_transcript(m)
        for rec in tail_lines(p, 600_000) if p else []:
            msg = rec.get("message")
            if rec.get("isMeta") or not isinstance(msg, dict):
                continue
            ts = rec.get("timestamp")
            if rec.get("type") == "user":
                c = msg.get("content")
                texts = [c] if isinstance(c, str) else [b.get("text", "") for b in c or [] if isinstance(b, dict) and b.get("type") == "text"]
                for tx in texts:
                    if tx and not tx.startswith("<"):
                        out.append({"role": "user", "text": tx, "t": ts})
            elif rec.get("type") == "assistant":
                for b in msg.get("content") or []:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text" and b.get("text", "").strip():
                        out.append({"role": "assistant", "text": b["text"], "t": ts})
                    elif b.get("type") == "tool_use":
                        out.append({"role": "tool", "text": f"{b.get('name')}: {short_input(b.get('name'), b.get('input'))}".rstrip(": "), "t": ts})
    elif m["engine"] == "kimi":
        p = kimi_wire(m)
        for rec in tail_lines(p, 600_000) if p else []:
            if rec.get("type") != "agent.message.appended":
                continue
            msg = (rec.get("message") or {}).get("message") or {}
            tc = rec.get("time")
            ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(tc / 1000)) if tc else None
            texts = [b.get("text", "") for b in msg.get("content") or [] if isinstance(b, dict) and b.get("type") == "text"]
            if msg.get("role") == "user":
                for tx in texts:
                    if tx and not tx.startswith("<"):
                        out.append({"role": "user", "text": _strip_persona(tx), "t": ts})
            elif msg.get("role") == "assistant":
                for tx in texts:
                    if tx.strip():
                        out.append({"role": "assistant", "text": tx, "t": ts})
                for c in msg.get("toolCalls") or []:
                    inp = c.get("arguments") or (c.get("function") or {}).get("arguments") or {}
                    if isinstance(inp, str):
                        try:
                            inp = json.loads(inp)
                        except ValueError:
                            inp = {}
                    name = c.get("name") or (c.get("function") or {}).get("name")
                    out.append({"role": "tool", "text": f"{name}: {short_input(name, inp)}".rstrip(": "), "t": ts})
    elif m.get("sessionId"):
        try:
            db = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True, timeout=1)
            rows = db.execute("select type, time_created, data from session_message where session_id=? "
                              "and type in ('user','assistant') order by seq", (m["sessionId"],)).fetchall()
            db.close()
        except Exception:
            rows = []
        for typ, tc, data in rows:
            try:
                d = json.loads(data)
            except ValueError:
                continue
            ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(tc / 1000)) if tc else None
            if typ == "user" and d.get("text"):
                out.append({"role": "user", "text": _strip_persona(d["text"]), "t": ts})
            elif typ == "assistant":
                for b in d.get("content") or []:
                    if b.get("type") == "text" and b.get("text", "").strip():
                        out.append({"role": "assistant", "text": b["text"], "t": ts})
                    elif b.get("type") == "tool":
                        inp = (b.get("state") or {}).get("input") or {}
                        out.append({"role": "tool", "text": f"{b.get('name')}: {short_input(b.get('name'), inp)}".rstrip(": "), "t": ts})
    st = run_state(mid)
    if st and st["error"]:
        out.append({"role": "error", "text": st["error"], "t": None})
    return {"messages": out[-limit:], "run": st}


# ---------------------------------------------------------------- estado en directo

def member_agents(live, procs_opencode, oc_rows, collect_subagents, project_dir_for, transcript_activity, now):
    """Convierte la plantilla en agentes para la escena y marca qué sesiones en directo les pertenecen.

    live: agentes 'session' en directo (Claude). Devuelve (agentes_miembro, ids_de_sesion_consumidos)."""
    r = load()
    teams = {t["id"]: t for t in r["teams"]}
    out, consumed = [], set()
    for m in r["members"]:
        sid = m.get("sessionId")
        a = {
            "id": "m:" + m["id"], "memberId": m["id"], "kind": "member", "role": m.get("role") or "", "job": m.get("job") or "",
            "original": (m.get("original") or {}).get("model"), "parent": None, "team": m.get("team"),
            "name": m["name"], "title": m.get("personality", "")[:90], "model": m.get("model") or m["engine"],
            "engine": m["engine"], "status": "offline", "tool": None, "detail": "", "tokens": None,
            "cwd": m["cwd"], "look": m.get("look") or {}, "window": False,
        }
        run = _runs.get(m["id"])
        if m["engine"] == "claude":
            win = next((s for s in live if sid and (s["id"] == sid)), None)
            if win:
                consumed.add(win["id"])
                a.update(status=win["status"], tool=win["tool"], detail=win["detail"], tokens=win["tokens"], window=True)
            elif sid and claude_transcript(m):
                act = transcript_activity(claude_transcript(m))
                a["tokens"] = act["tokens"]
        else:
            win = next((p for p in procs_opencode if sid and sid in p[1] and "run" not in p[1][1:2]), None)
            row = next((x for x in oc_rows if x["id"] == sid), None)
            if row:
                consumed.add(row["id"])
                a.update(tokens=row["tokens"], tool=row["tool"], detail=row["detail"])
            if win:
                a.update(status=row["status"] if row else "idle", window=True)
        if run and not run.done:
            a["status"] = "busy"
            if run.tool:
                a.update(tool=run.tool, detail=run.detail)
        elif run and run.done and a["status"] == "offline" and now - getattr(run, "finished", 0) < 20:
            a["status"] = "idle"   # acaba de terminar: se queda un momento en la mesa
        out.append(a)
        if sid and m["engine"] == "claude" and a["status"] != "offline":
            proj = os.path.dirname(claude_transcript(m) or project_dir_for(os.path.expanduser(m["cwd"]), sid) + "/x")
            out.extend(collect_subagents(proj, sid, a["id"], now))
    return out, consumed, [{"id": t["id"], "name": t["name"], "color": t["color"]} for t in r["teams"]]


# ---------------------------------------------------------------- PM: cambio de modelo al agotarse la cuota

QUOTA_PATTERNS = re.compile(
    r"usage limit|limit reached|hit your (\S+ )?limit|rate.?limit|quota|credit balance|insufficient[_ ]?(quota|credits?|funds)"
    r"|too many requests|\b429\b|\b402\b|payment required|out of (tokens|credits)|tokens? (exhausted|agotad)"
    r"|l[ií]mite de uso|cuota", re.I)
# modelos gratuitos de reserva, en orden de preferencia (el PM puede tener su propia lista en "fallbacks")
DEFAULT_FALLBACKS = [
    "opencode/deepseek-v4.1-flash-free",
    "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
    "opencode/big-pickle",
    "opencode/mimo-v2.6-flash-free",
    "openrouter/google/gemma-4-31b-it:free",
    "opencode/nemotron-3.5-super-vl-free",
]
_exhausted = {}     # modelo -> momento en que se agotó (se evita durante 1 h)
PM_LOG = os.path.join(DATA, "pm.jsonl")


def is_quota_error(text):
    return bool(QUOTA_PATTERNS.search(text or ""))


def pm_fallbacks(pm):
    """Lista de reserva del PM (o la de serie). «__ninguno__» era el antiguo «desactivado» puesto a mano."""
    return [f for f in (pm.get("fallbacks") or []) if f != "__ninguno__"] or DEFAULT_FALLBACKS


def pm_auto_swap(pm):
    if "autoSwap" in pm:
        return bool(pm["autoSwap"])
    return pm.get("fallbacks") != ["__ninguno__"]


def find_pm(r=None):
    r = r or load()
    return next((m for m in r["members"] if m.get("role") == "pm"), None)


def _short(model):
    return (model or "").split("/")[-1].replace(":free", "").replace("claude-", "")


def pm_handle_quota(member, error, run):
    """El PM ve que alguien se quedó sin cuota: le pasa a un modelo gratuito libre y repite la orden una vez."""
    now = time.time()
    with _lock:
        r = load()
        pm = find_pm(r)
        if not pm:
            return
        m = next((x for x in r["members"] if x["id"] == member["id"]), None)
        if not m:
            return
        cur = m.get("model") or ""
        _exhausted[cur] = now
        pm_sid = ensure_session(pm)
        import server
        if not pm_auto_swap(pm):
            server.add_event(pm_sid, "PM", f"{m['name']} se quedó sin cuota (tengo desactivado el cambio automático de modelo)")
            _pm_log({"t": now, "member": m["id"], "from": cur, "to": None, "error": error[:200], "auto": False})
            return
        avail = {x["id"] for x in models()["opencode"]}
        choices = [f for f in pm_fallbacks(pm)
                   if f != cur and now - _exhausted.get(f, 0) > 3600 and (not avail or f in avail)]
        if not choices:
            server.add_event(pm_sid, "PM", f"{m['name']} se quedó sin cuota y no me quedan modelos gratuitos libres")
            _pm_log({"t": now, "member": m["id"], "from": cur, "to": None, "error": error[:200]})
            return
        new = choices[0]
        if not m.get("original"):      # se guarda cómo estaba para poder volver
            m["original"] = {"engine": m["engine"], "model": cur, "sessionId": m.get("sessionId")}
        if m["engine"] != "opencode":
            m["engine"] = "opencode"
            m.pop("sessionId", None)   # sesión nueva de OpenCode; la de Claude queda guardada en "original"
        m["model"] = new
        save(r)
        _pm_log({"t": now, "member": m["id"], "from": cur, "to": new, "error": error[:200]})
        server.add_event(pm_sid, "PM", f"{m['name']}: {_short(cur)} sin cuota, la paso a {_short(new)}")
    if run.orig and run.attempt < MAX_ATTEMPTS:
        _retry_later(member["id"], run, "el modelo anterior se quedó sin cuota a mitad de la tarea y ahora sigues tú con otro modelo. "
                     "Si no tienes el contexto, retoma la tarea desde el principio.")


def restore_model(mid):
    """Vuelve al modelo (y la conversación) que tenía antes de que el PM lo cambiara."""
    with _lock:
        r = load()
        m = next((x for x in r["members"] if x["id"] == mid), None)
        if not m or not m.get("original"):
            raise ValueError("Ese miembro no tiene un modelo anterior guardado")
        o = m.pop("original")
        m["engine"], m["model"] = o["engine"], o["model"]
        if o.get("sessionId"):
            m["sessionId"] = o["sessionId"]
        else:
            m.pop("sessionId", None)
        _exhausted.pop(o["model"], None)
        save(r)
        return m


def _pm_log(rec):
    os.makedirs(DATA, exist_ok=True)
    with open(PM_LOG, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- PM: agentes colgados o sin conexión

MAX_ATTEMPTS = 2           # reintentos por orden (además del primer intento)
HANG_THINKING = 300        # s sin ninguna salida mientras piensa el modelo
HANG_TOOL = 900            # s sin salida con una herramienta en marcha (un build o un test pueden tardar)
NET_PATTERNS = re.compile(
    r"ECONNRESET|ETIMEDOUT|ECONNREFUSED|EAI_AGAIN|ENOTFOUND|socket|network|fetch failed|timed? ?out"
    r"|overloaded|service unavailable|bad gateway|internal server error|\b50[0234]\b|\b529\b"
    r"|connection (error|closed|reset|refused)|API Error: 5", re.I)


def is_network_error(text):
    return bool(NET_PATTERNS.search(text or ""))


def _retry_later(mid, run, why):
    def retry():
        time.sleep(3)
        try:
            send_order(mid, f"(Nota del PM: {why})\n\n{run.orig}", attempt=run.attempt + 1, orig=run.orig)
        except ValueError as e:
            print("PM: no se pudo repetir la orden:", e)
    threading.Thread(target=retry, daemon=True).start()


def pm_rescue(member, run):
    pm = find_pm()
    if not pm:
        return
    import server
    pm_sid = ensure_session(pm)
    reason = "se colgó" if run.hung else "perdió la conexión"
    if run.attempt >= MAX_ATTEMPTS:
        server.add_event(pm_sid, "PMHang", f"{member['name']} {reason} otra vez; la dejo parada para que lo mires")
        _pm_log({"t": time.time(), "member": member["id"], "action": "rendido", "reason": reason, "error": (run.error or "")[:200]})
        return
    server.add_event(pm_sid, "PMHang", f"{member['name']} {reason}: reinicio su orden ({run.attempt + 1}/{MAX_ATTEMPTS})")
    _pm_log({"t": time.time(), "member": member["id"], "action": "reinicio", "reason": reason, "error": (run.error or "")[:200]})
    _retry_later(member["id"], run, f"el intento anterior {reason} y se cortó. Retoma la tarea; si ya hiciste parte, "
                 "comprueba primero qué quedó hecho.")


def watchdog_tick(now=None):
    """Busca órdenes que llevan demasiado sin dar señales de vida y las corta (el final de la orden las reintenta)."""
    now = now or time.time()
    if not find_pm():
        return
    for mid, run in list(_runs.items()):
        if run.done or run.hung or run.stopped:
            continue
        limit = HANG_TOOL if run.in_tool else HANG_THINKING
        quiet = now - run.last_out
        if quiet > limit:
            run.hung = True
            run.error = f"Colgado: {int(quiet // 60)} min sin dar señales"
            try:
                plataforma.kill_tree(run.proc.pid)
            except OSError:
                pass


def start_watchdog(every=15):
    def loop():
        while True:
            try:
                watchdog_tick()
            except Exception as e:  # noqa: BLE001
                print("vigilante:", e)
            time.sleep(every)
    threading.Thread(target=loop, daemon=True).start()
