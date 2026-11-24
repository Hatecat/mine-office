#!/usr/bin/env python3
"""Oficina de agentes: servidor local que lee el estado de Claude Code y OpenCode.

Uso:  python3 server.py [--port 8765]
Abre http://127.0.0.1:8765  (añade ?demo=1 para ver agentes de ejemplo)
"""
import argparse
import glob
import json
import os
import re
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import ajustes
import plataforma
import voz
import roster
import usage
import secretaria

HOME = os.path.expanduser("~")
CLAUDE = os.path.join(HOME, ".claude")
HERE = os.path.dirname(os.path.abspath(__file__))
SUBAGENT_STALE = 15 * 60  # s sin escribir => se considera muerto aunque no marque finished


def pid_alive(pid):
    return plataforma.pid_alive(pid)


def tail_lines(path, max_bytes=96_000):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            data = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    lines = data.splitlines()
    if size > max_bytes:
        lines = lines[1:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def short_input(name, inp):
    if not isinstance(inp, dict):
        return ""
    for key in ("description", "command", "file_path", "pattern", "url", "query", "prompt", "skill"):
        v = inp.get(key)
        if isinstance(v, str) and v:
            v = v.replace(HOME, "~").strip().splitlines()[0]
            return v[:70]
    return ""


def transcript_activity(path):
    """Último modelo, última herramienta y marca de tiempo de una transcripción."""
    info = {"model": None, "tool": None, "detail": "", "last": None, "tokens": None}
    for rec in reversed(tail_lines(path)):
        if info["last"] is None and rec.get("timestamp"):
            info["last"] = rec["timestamp"]
        msg = rec.get("message")
        if rec.get("type") != "assistant" or not isinstance(msg, dict):
            continue
        if info["model"] is None and msg.get("model"):
            info["model"] = msg["model"]
            usage = msg.get("usage") or {}
            ctx = sum(usage.get(k, 0) or 0 for k in
                      ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            info["tokens"] = ctx or None
        if info["tool"] is None:
            for block in reversed(msg.get("content") or []):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    info["tool"] = block.get("name")
                    info["detail"] = short_input(block.get("name"), block.get("input"))
                    break
        if info["model"] and info["tool"]:
            break
    return info


def project_dir_for(cwd, session_id):
    enc = re.sub(r"[^A-Za-z0-9]", "-", cwd or "")
    cand = os.path.join(CLAUDE, "projects", enc)
    if os.path.exists(os.path.join(cand, session_id + ".jsonl")):
        return cand
    hits = glob.glob(os.path.join(CLAUDE, "projects", "*", session_id + ".jsonl"))
    return os.path.dirname(hits[0]) if hits else cand


def collect_subagents(proj_dir, session_id, parent_id, now):
    subs = []
    for meta_path in glob.glob(os.path.join(proj_dir, session_id, "subagents", "*.meta.json")):
        try:
            meta = json.load(open(meta_path))
        except (OSError, ValueError):
            continue
        jsonl = meta_path[: -len(".meta.json")] + ".jsonl"
        try:
            mtime = os.path.getmtime(jsonl)
        except OSError:
            mtime = os.path.getmtime(meta_path)
        if meta.get("finished") or now - mtime > SUBAGENT_STALE:
            continue
        act = transcript_activity(jsonl)
        aid = os.path.basename(jsonl)[:-6]
        subs.append({
            "id": aid,
            "kind": "subagent",
            "parent": parent_id,
            "name": meta.get("agentType") or "subagente",
            "title": meta.get("description") or "",
            "model": act["model"] or meta.get("pickedEffortModel"),
            "status": "busy" if now - mtime < 90 else "idle",
            "tool": act["tool"],
            "detail": act["detail"],
            "tokens": act["tokens"],
            "cwd": None,
        })
    return subs


def collect_teams():
    teams = []
    for cfg in glob.glob(os.path.join(CLAUDE, "teams", "*", "config.json")):
        try:
            data = json.load(open(cfg))
        except (OSError, ValueError):
            continue
        members = data.get("members") or data.get("teammates") or []
        teams.append({
            "name": data.get("name") or os.path.basename(os.path.dirname(cfg)),
            "members": [
                {"name": m.get("name") or m.get("agentId") or "?",
                 "type": m.get("agentType") or m.get("type") or "",
                 "model": m.get("model")}
                for m in members if isinstance(m, dict)
            ],
        })
    return teams


OPENCODE_DB = os.path.join(HOME, ".local", "share", "opencode", "opencode.db")
OC_RECENT = 30 * 60  # s: sesiones de OpenCode tocadas hace menos de esto


def opencode_processes():
    """(cwd, args) de cada opencode vivo, sin contar el servicio de fondo."""
    procs = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            args = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
            cwd = os.readlink(f"/proc/{pid}/cwd")
        except OSError:
            continue
        args = [a.decode("utf-8", "replace") for a in args if a]
        if not args or not os.path.basename(args[0]).startswith("opencode"):
            continue
        if len(args) > 1 and args[1] == "serve":
            continue
        procs.append((cwd, args))
    return procs


def oc_last_tool(db, sid):
    row = db.execute("select data from session_message where session_id=? and type='assistant' "
                     "order by seq desc limit 1", (sid,)).fetchone()
    if not row:
        return None, ""
    try:
        content = json.loads(row[0]).get("content") or []
    except ValueError:
        return None, ""
    for b in reversed(content):
        if isinstance(b, dict) and b.get("type") == "tool":
            inp = (b.get("state") or {}).get("input") or {}
            return b.get("name"), short_input(b.get("name"), inp)
    return None, ""


def collect_opencode(now, exclude_sids=()):
    procs = [p for p in opencode_processes() if not any(sid in p[1] for sid in exclude_sids)]
    if not procs:
        return []
    dirs = {cwd for cwd, _ in procs}
    try:
        import sqlite3
        db = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True, timeout=1)
        rows = db.execute(
            "select id, parent_id, directory, title, model, agent, time_updated, time_idle, "
            "tokens_input, tokens_cache_read from session_v2 "
            "where time_archived is null and time_updated > ? order by time_updated desc",
            (int((now - OC_RECENT) * 1000),)).fetchall()
    except Exception:
        rows, db = [], None
    out, keep = [], set()
    for sid, parent, d, title, model, agent, upd, idle, tin, tcache in rows:
        if parent is None and d not in dirs:
            continue
        if parent is not None and parent not in keep:
            continue
        keep.add(sid)
        try:
            m = json.loads(model or "{}")
            model_name = f"{m.get('providerID', '')}/{m.get('id', '')}".strip("/") or "opencode"
        except ValueError:
            model_name = "opencode"
        busy = not (idle and idle >= upd) and now - upd / 1000 < 300
        tool, detail = oc_last_tool(db, sid)
        out.append({
            "id": sid, "kind": "opencode", "parent": parent,
            "name": ("opencode · " + agent) if parent is None and agent else (agent or "opencode"),
            "title": title or "", "model": model_name,
            "status": "busy" if busy else "idle", "tool": tool, "detail": detail,
            "tokens": (tin or 0) + (tcache or 0) or None, "cwd": d.replace(HOME, "~"),
            # sin cerrar el turno y sin novedades: posible atasco en su ventana
            "stalledFor": (now - upd / 1000) if not (idle and idle >= upd) else 0,
        })
    if db:
        db.close()
    if not any(o["parent"] is None for o in out):
        # sin sesión en la base de datos (aún): enseñar los procesos tal cual
        for cwd, args in procs:
            out.append({"id": f"oc-{cwd}", "kind": "opencode", "parent": None, "name": "opencode",
                        "title": cwd.replace(HOME, "~"), "model": "opencode", "status": "idle",
                        "tool": None, "detail": "", "tokens": None, "cwd": cwd.replace(HOME, "~")})
    return out


def claude_sessions(now):
    """Sesiones interactivas vivas de Claude Code y sus subagentes."""
    sessions, subs = [], []
    for path in glob.glob(os.path.join(CLAUDE, "sessions", "*.json")):
        try:
            s = json.load(open(path))
        except (OSError, ValueError):
            continue
        if not pid_alive(s.get("pid")):
            continue
        sid = s.get("sessionId", "")
        proj = project_dir_for(s.get("cwd"), sid)
        act = transcript_activity(os.path.join(proj, sid + ".jsonl"))
        cwd = (s.get("cwd") or "").replace(HOME, "~") or "~"
        sessions.append({
            "id": sid, "kind": "session", "parent": None,
            "name": s.get("name") or os.path.basename(s.get("cwd") or "") or sid[:8],
            "title": cwd, "model": act["model"], "status": s.get("status") or "idle",
            "tool": act["tool"], "detail": act["detail"], "tokens": act["tokens"], "cwd": cwd, "pid": s.get("pid"),
            "updated": s.get("updatedAt") or 0, "home": (s.get("cwd") or "") == HOME,
        })
        subs.extend(collect_subagents(proj, sid, sid, now))
    return sessions, subs


def snapshot():
    now = time.time()
    sessions, subs = claude_sessions(now)
    member_sids = [m.get("sessionId") for m in roster.load()["members"] if m.get("sessionId")]
    oc = collect_opencode(now, member_sids)
    members, consumed, teams = roster.member_agents(
        sessions, opencode_processes(), oc, collect_subagents, project_dir_for, transcript_activity, now)
    visitors = [a for a in sessions + subs + oc if a["id"] not in consumed and a.get("parent") not in consumed]
    r = roster.load()
    sid_of = {"m:" + m["id"]: m.get("sessionId") for m in r["members"]}
    vsids = roster.virtual_sids()
    visitors = [a for a in visitors if a["id"] not in vsids]      # el chat del jefe y de Liberty no son visitas
    visitors = mark_boss(r.get("boss") or roster.BOSS_DEFAULT, visitors) + [secretaria.agent()]
    for a in visitors:
        vid = "jefe" if a.get("boss") else "liberty" if a.get("secretary") else None
        if vid:
            a["memberId"] = vid
            run = roster.run_state(vid)
            if run and run.get("running"):
                a.update(status="busy", tool=run.get("tool") or "Respondiendo", detail=run.get("detail") or "")
    att = attention_map(now)
    pend = boss_inbox()
    for a in visitors:
        if a.get("boss") and pend:
            att[a["id"]] = {"kind": "buzon", "t": pend[-1]["t"],
                            "msg": f"{len(pend)} petición{'es' if len(pend) > 1 else ''}: {pend[-1]['name']} — {pend[-1]['text']}"}
    asking = {i.get("from") for i in pend}
    for a in members + visitors:
        sid = sid_of.get(a["id"]) if a.get("kind") == "member" else a["id"]
        if sid in att and not (att[sid]["kind"] == "peticion" and a.get("memberId") not in asking):
            a["attention"] = {**att[sid], "sid": sid}
    return {"time": now, "agents": members + visitors, "teams": teams, "claudeTeams": collect_teams()}


def boss_inbox():
    try:
        with open(os.path.join(plataforma.DATA_DIR, "peticiones.json")) as f:
            return [i for i in json.load(f)["items"] if i["estado"] == "pendiente"]
    except (OSError, ValueError, KeyError):
        return []


def mark_boss(boss, visitors):
    """El jefe soy yo, Claude: la sesión interactiva de Claude Code con la que hablas.
    Si hay varias, la de la carpeta personal más reciente; si no hay ninguna, descansa."""
    sess = [a for a in visitors if a.get("kind") == "session"]
    fixed = [a for a in sess if a["id"] == boss.get("sessionId")]
    pick = (fixed or sorted(sess, key=lambda a: (a.get("home", False), a.get("updated", 0)), reverse=True) or [None])[0]
    info = {"boss": True, "name": boss["name"], "look": boss["look"], "bossTitle": boss.get("title", "Jefe"), "job": boss.get("job", "Jefe")}
    if pick:
        pick.update(info, sessionName=pick["name"])
        return visitors
    return [{"id": "boss", "kind": "session", "parent": None, "title": "sin ventana abierta", "model": "claude-opus-5-5",
             "status": "offline", "tool": None, "detail": "", "tokens": 0, "cwd": "~", **info}] + visitors


EVENTS_FILE = os.path.join(plataforma.DATA_DIR, "events.jsonl")
ACKS = {}          # sid -> momento en que se vio el globo (o empezó una orden nueva)
_tp_cache = {}


def _transcript_mtime(sid):
    p = _tp_cache.get(sid)
    if not p or not os.path.exists(p):
        hits = glob.glob(os.path.join(CLAUDE, "projects", "*", sid + ".jsonl"))
        p = _tp_cache[sid] = hits[0] if hits else None
    try:
        return os.path.getmtime(p) if p else 0
    except OSError:
        return 0


def attention_map(now):
    """Globos de aviso: el último evento de cada sesión que siga vigente.
    listo = terminó y espera; permiso = está parada esperando que le confirmes algo."""
    try:
        if os.path.getsize(EVENTS_FILE) > 2_000_000:       # que no crezca sin límite
            lines = open(EVENTS_FILE).readlines()[-2000:]
            with open(EVENTS_FILE, "w") as f:
                f.writelines(lines)
        off = max(0, os.path.getsize(EVENTS_FILE) - 200_000)
        with open(EVENTS_FILE, "rb") as f:
            f.seek(off)
            raw = f.read().decode(errors="replace").splitlines()[1 if off else 0:]
    except OSError:
        return {}
    last = {}
    for ln in raw:
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        typ, msg = e.get("type") or "", (e.get("msg") or "").lower()
        if e.get("ev") == "Notification":
            if typ == "idle_prompt" or "waiting for your input" in msg:
                continue
            kind = "permiso" if (typ == "permission_prompt" or "permission" in msg) else "pregunta"
        elif e.get("ev") == "Denied":
            kind = "permiso"
        elif e.get("ev") == "PM":
            kind = "cambio"
        elif e.get("ev") == "PMHang":
            kind = "rescate"
        elif e.get("ev") == "Stuck":
            kind = "atasco"
        elif e.get("ev") == "Say":
            kind = "voz"
        elif e.get("ev") == "BossAsk":
            kind = "peticion"
        else:
            kind = "listo"
        prev = last.get(e["sid"])
        if kind == "listo" and prev and prev["kind"] == "peticion" and e["t"] - prev["t"] < 600:
            continue                                    # terminó su turno tras pedir: sigue esperando al jefe
        last[e["sid"]] = {"kind": kind, "t": e["t"], "msg": e.get("msg") or "", "ev": e.get("ev")}
    sess = {}
    for f in glob.glob(os.path.join(CLAUDE, "sessions", "*.json")):
        try:
            d = json.load(open(f))
            sess[d.get("sessionId")] = (d.get("status"), (d.get("statusUpdatedAt") or 0) / 1000)
        except (OSError, ValueError):
            pass
    out = {}
    for sid, e in last.items():
        t = e["t"]
        ttl = {"listo": 1800, "voz": 25}.get(e["kind"], 7200)
        if ACKS.get(sid, 0) >= t or now - t > ttl:
            continue
        st, st_t = sess.get(sid, (None, 0))
        if st == "busy" and st_t > t + 1 and e["kind"] == "listo":
            continue                                    # ya está con otra cosa
        if e["kind"] in ("permiso", "pregunta", "atasco") and e["ev"] in ("Notification", "Stuck") and _transcript_mtime(sid) > t + 2:
            continue                                    # ya se respondió
        out[sid] = e
    return out


# ---------------------------------------------------------------- ventanas atascadas
STUCK_THINKING, STUCK_TOOL = 300, 900
_stuck_seen = {}     # sid -> marca de actividad ya avisada (para avisar una sola vez por atasco)


def _last_is_pending_tool(path):
    """¿La última entrada del transcript es una llamada a herramienta sin resultado? (está ejecutando algo)"""
    for o in reversed(tail_lines(path, 60_000)):
        if not isinstance(o, dict):
            continue
        if o.get("type") == "assistant":
            c = (o.get("message") or {}).get("content") or []
            return any(isinstance(b, dict) and b.get("type") == "tool_use" for b in c)
        if o.get("type") == "user":
            return False
    return False


def check_stuck_windows():
    """Tomás avisa si alguien lleva demasiado sin avanzar en su propia ventana (ahí no puede reiniciarlo)."""
    pm = roster.find_pm()
    if not pm:
        return
    now = time.time()
    data = snapshot()
    att = {a["attention"]["sid"]: a["attention"]["kind"] for a in data["agents"] if a.get("attention")}
    sid_of = {"m:" + m["id"]: m.get("sessionId") for m in roster.load()["members"]}
    for a in data["agents"]:
        if a.get("status") != "busy":
            continue
        if a.get("kind") == "member":
            run = roster.run_state(a["memberId"])
            if (run and run["running"]) or not a.get("window"):
                continue                    # las órdenes del chat las vigila el watchdog, que sí puede reiniciar
            sid = sid_of.get(a["id"])
        elif a.get("kind") in ("session", "opencode") and not a.get("parent"):
            sid = a["id"]
        else:
            continue
        if not sid or att.get(sid) in ("permiso", "pregunta"):
            continue                        # está esperándote a ti, no atascado
        if sid.startswith("ses_"):          # OpenCode
            quiet, mark = a.get("stalledFor") or 0, int(now - (a.get("stalledFor") or 0))
            limit = STUCK_THINKING
        else:
            hits = glob.glob(os.path.join(CLAUDE, "projects", "*", sid + ".jsonl"))
            if not hits:
                continue
            mark = int(os.path.getmtime(hits[0]))
            quiet = now - mark
            limit = STUCK_TOOL if _last_is_pending_tool(hits[0]) else STUCK_THINKING
        if quiet < limit or _stuck_seen.get(sid) == mark:
            continue
        _stuck_seen[sid] = mark
        mins = int(quiet // 60)
        add_event(sid, "Stuck", f"{mins} min sin avanzar")
        add_event(roster.ensure_session(pm), "PMHang",
                  f"{a['name']} lleva {mins} min sin avanzar en su ventana; échale un vistazo")


def start_stuck_watch(every=30):
    def loop():
        while True:
            try:
                check_stuck_windows()
            except Exception as e:  # noqa: BLE001
                print("ventanas atascadas:", e)
            time.sleep(every)
    threading.Thread(target=loop, daemon=True).start()


def add_event(sid, ev, msg="", limit=200):
    os.makedirs(os.path.dirname(EVENTS_FILE), exist_ok=True)
    with open(EVENTS_FILE, "a") as f:
        f.write(json.dumps({"t": round(time.time(), 2), "sid": sid, "ev": ev, "type": "", "msg": msg[:limit]},
                           ensure_ascii=False) + "\n")


def _load_token():
    """El token sobrevive a los reinicios: así las pestañas abiertas siguen funcionando."""
    path = os.path.join(plataforma.DATA_DIR, "token")
    try:
        with open(path) as f:
            t = f.read().strip()
        if len(t) >= 24:
            return t
    except OSError:
        pass
    t = secrets.token_urlsafe(24)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(t)
    return t


TOKEN = _load_token()
PORT = plataforma.PUERTO


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj, code=200):
        self.send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def host_ok(self):
        # contra DNS rebinding: solo se responde a quien nos llama por 127.0.0.1/localhost
        return self.headers.get("Host", "") in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def do_GET(self):
        if not self.host_ok():
            return self.send(403, b"host", "text/plain")
        path, _, qs = self.path.partition("?")
        q = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
        try:
            if path == "/api/agents":
                return self.send_json(snapshot())
            if path == "/api/roster":
                return self.send_json(roster.load())
            if path == "/api/voice":
                return self.send_json(secretaria.conf())
            if path == "/api/usage":
                return self.send_json(usage.report())
            if path == "/api/models":
                return self.send_json(roster.models())
            if path == "/api/voz/estado":
                return self.send_json(voz.estado())
            if path == "/api/ajustes":
                gratis = [m["id"] for m in roster.models()["opencode"] if ajustes.es_gratis(m["id"])]
                return self.send_json({"ajustes": ajustes.cargar(), "detectados": ajustes.detectar(),
                                       "gratisOpenCode": gratis, "proveedores": ajustes.proveedores_opencode(),
                                       "gastoHoy": usage.gasto_hoy(),
                                       "voz": voz.estado()})
            if path == "/api/chat":
                from urllib.parse import unquote
                return self.send_json(roster.history(unquote(q.get("id", ""))))
        except ValueError as e:
            return self.send_json({"error": str(e)}, 400)
        if path == "/":
            return self.static("index.html")
        self.static(path.lstrip("/"))

    def do_POST(self):
        # escritura: mismo host, origen propio y el token que va dentro de la página
        origin = self.headers.get("Origin")
        if (not self.host_ok() or self.headers.get("X-Office-Token") != TOKEN
                or (origin and origin not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"))):
            return self.send(403, b"prohibido", "text/plain")
        if self.path.split("?", 1)[0] == "/api/stt":           # audio crudo: float32 mono 16 kHz
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 < n <= 3_000_000:
                return self.send_json({"error": "audio vacío o demasiado largo"}, 400)
            try:
                return self.send_json(secretaria.transcribe(self.rfile.read(n)))
            except Exception as e:  # noqa: BLE001
                return self.send_json({"error": f"transcriptor: {e}"}, 503)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(n, 200_000)) or b"{}")
        except ValueError:
            return self.send_json({"error": "JSON no válido"}, 400)
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/ajustes":
                try:
                    limpios = ajustes.validar(body)
                except ValueError as e:
                    return self.send_json({"error": str(e)}, 400)
                ajustes.guardar(limpios)
                return self.send_json(limpios)
            if path == "/api/voz/descargar":
                return self.send_json({"iniciada": voz.iniciar(), **voz.estado()})
            if path == "/api/member":
                return self.send_json(roster.upsert_member(body))
            if path == "/api/team":
                return self.send_json(roster.upsert_team(body))
            if path == "/api/delete":
                roster.delete(body.get("kind"), body.get("id")); return self.send_json({"ok": True})
            if path == "/api/order":
                roster.send_order(body.get("id"), body.get("text")); return self.send_json({"ok": True})
            if path == "/api/voice":
                return self.send_json(secretaria.set_voice(body.get("on")))
            if path == "/api/stt/start":
                return self.send_json(secretaria.stt_status())
            if path == "/api/say":
                secretaria.say(str(body.get("text") or "Hola, soy Liberty. Te avisaré cuando alguien te necesite."))
                return self.send_json({"ok": True})
            if path == "/api/ack":
                ACKS[str(body.get("sid"))] = time.time(); return self.send_json({"ok": True})
            if path == "/api/restore":
                return self.send_json(roster.restore_model(body.get("id")))
            if path == "/api/stop":
                roster.stop(body.get("id")); return self.send_json({"ok": True})
            if path == "/api/open":
                roster.open_window(body.get("id")); return self.send_json({"ok": True})
        except ValueError as e:
            return self.send_json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001 - que el navegador vea el fallo
            return self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)
        self.send(404, b"no", "text/plain")

    STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                    ".png": "image/png", ".css": "text/css"}

    def static(self, rel):
        if rel == "favicon.ico":
            return self.send(204, b"", "image/x-icon")
        ext = os.path.splitext(rel)[1]
        top = rel.split("/", 1)[0]
        ok = ext in self.STATIC_TYPES and (("/" not in rel and ext == ".html") or top in ("lib", "rooms", "vendor"))
        fp = os.path.realpath(os.path.join(HERE, rel))
        if not ok or not fp.startswith(HERE + os.sep) or not os.path.isfile(fp):
            return self.send(404, b"no", "text/plain")
        with open(fp, "rb") as f:
            data = f.read()
        if rel == "index.html":
            data = data.replace(b"__OFFICE_TOKEN__", TOKEN.encode())
        self.send(200, data, self.STATIC_TYPES[ext])


def main(argv=None):
    global PORT
    sys.modules.setdefault("server", sys.modules[__name__])  # roster.py importa utilidades de aquí
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=plataforma.PUERTO)
    a = ap.parse_args(argv)
    PORT = a.port
    usage.start_background()
    roster.start_watchdog()
    start_stuck_watch()
    secretaria.start()
    print(f"MineOffice en http://127.0.0.1:{a.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
