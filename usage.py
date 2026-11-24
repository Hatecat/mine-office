"""Gasto aproximado por agente.

Lee el campo `usage` de cada respuesta en las transcripciones de Claude Code (~/.claude/projects/**.jsonl)
y el coste que OpenCode guarda en su base de datos, y lo va apuntando en data/usage.json. El libro se
guarda aparte para que el historial sobreviva aunque se borren las transcripciones.

Es una estimación a precio de API: con un plan de suscripción (Pro/Max) no se cobra por token.
"""
import glob
import json
import os
import sqlite3
import threading
import time
from datetime import datetime

HOME = os.path.expanduser("~")
PROJECTS = os.path.join(HOME, ".claude", "projects")
HERE = os.path.dirname(os.path.abspath(__file__))
import plataforma

DATA = plataforma.DATA_DIR
LEDGER_FILE = os.path.join(DATA, "usage.json")
RUNS_FILE = os.path.join(DATA, "runs.jsonl")
OPENCODE_DB = os.path.join(HOME, ".local", "share", "opencode", "opencode.db")

OTHER_CC = "cc"      # sesiones de Claude Code que no son de la plantilla
OTHER_OC = "oc"      # sesiones de OpenCode que no son de la plantilla

# $ por millón de tokens: entrada, salida, escritura de caché 5 min, escritura 1 h, lectura de caché.
# Fuente: tabla de modelos de la referencia de la API de Claude (noviembre de 2026).
PRICES = {
    "claude-fable-5-2": (8, 40, 10, 16, 0.20),
    "claude-mythos-5-2": (8, 40, 10, 16, 0.20),
    "claude-fable-5-1": (10, 50, 12.5, 20, 0.25),
    "claude-fable-5": (10, 50, 12.5, 20, 1.0),
    "claude-opus-5-5": (4, 20, 5, 8, 0.20),
    "claude-opus-5": (5, 25, 6.25, 10, 0.50),
    "claude-opus-4": (5, 25, 6.25, 10, 0.50),
    "claude-sonnet-5-5": (2, 10, 2.5, 4, 0.10),
    "claude-sonnet-5": (2, 10, 2.5, 4, 0.20),
    "claude-sonnet-4": (3, 15, 3.75, 6, 0.30),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.20, 0.01),
    "claude-haiku-4": (1, 5, 1.25, 2, 0.10),
}


def price_for(model):
    model = (model or "").split("[")[0]
    best = None
    for k in PRICES:   # el prefijo más largo gana (claude-opus-5-5 antes que claude-opus-5)
        if model.startswith(k) and (best is None or len(k) > len(best)):
            best = k
    return PRICES.get(best)


def claude_cost(model, u, speed=None):
    p = price_for(model)
    if not p:
        return None
    inp, out = u.get("input_tokens") or 0, u.get("output_tokens") or 0
    cr = u.get("cache_read_input_tokens") or 0
    cw = u.get("cache_creation_input_tokens") or 0
    det = u.get("cache_creation") or {}
    cw1 = det.get("ephemeral_1h_input_tokens") or 0
    cw5 = max(cw - cw1, 0)
    pi, po, p5, p1, pr = p
    if model.startswith("claude-haiku-5-5") and inp + cr + cw > 100_000:
        pi, po, p5, p1, pr = (x * 5 for x in p)     # tramo de contexto largo de Haiku 5.5
    mult = 2 if speed == "fast" else 1
    return mult * (inp * pi + out * po + cw5 * p5 + cw1 * p1 + cr * pr) / 1e6


def _ts(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return time.time()


class Ledger:
    """Entradas: key -> {msgid: [t, modelo, entrada, salida, caché_escrita, caché_leída, coste]}"""

    def __init__(self):
        self.lock = threading.RLock()
        self.data = {"v": 1, "files": {}, "entries": {}, "names": {}, "oc_since": 0}
        self.ready = False
        self.dirty = False
        try:
            with open(LEDGER_FILE) as f:
                d = json.load(f)
            if d.get("v") == 1:
                self.data = d
        except (OSError, ValueError):
            pass

    def save(self):
        with self.lock:
            if not self.dirty:
                return
            os.makedirs(DATA, exist_ok=True)
            tmp = LEDGER_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.data, f, separators=(",", ":"))
            os.replace(tmp, LEDGER_FILE)
            self.dirty = False

    def put(self, key, mid, row):
        e = self.data["entries"].setdefault(key, {})
        if e.get(mid) != row:
            e[mid] = row
            self.dirty = True

    # ------------------------------------------------------------ Claude Code
    def _owner(self, path, sid_owner):
        parts = path[len(PROJECTS) + 1:].split(os.sep)
        sid = parts[1] if len(parts) > 2 else os.path.splitext(parts[-1])[0]   # subagentes: <sid>/subagents/x.jsonl
        return sid_owner.get(sid) or self.data["files"].get(path, {}).get("owner") or OTHER_CC

    def scan_claude(self, sid_owner, only=None):
        paths = only if only is not None else glob.glob(os.path.join(PROJECTS, "**", "*.jsonl"), recursive=True)
        for p in paths:
            try:
                st = os.stat(p)
            except OSError:
                continue
            with self.lock:
                info = self.data["files"].get(p) or {"off": 0}
                owner = self._owner(p, sid_owner)
                if info.get("owner") != owner:   # pasó a ser de un miembro: mover lo ya contado
                    old = info.get("owner")
                    if old and old in self.data["entries"]:
                        src = self.data["entries"][old]
                        moved = {k: v for k, v in src.items() if len(v) > 7 and v[7] == p}
                        for k in moved:
                            src.pop(k)
                        self.data["entries"].setdefault(owner, {}).update(moved)
                    info["owner"] = owner
                    self.dirty = True
                if st.st_size < info["off"]:     # el archivo se reescribió
                    info["off"] = 0
                if st.st_size == info["off"]:
                    self.data["files"][p] = info
                    continue
            off = self._read_claude(p, info["off"], owner)
            with self.lock:
                info["off"] = off
                self.data["files"][p] = info
                self.dirty = True

    def _read_claude(self, path, off, owner):
        with open(path, "rb") as f:
            f.seek(off)
            chunk = f.read()
        end = chunk.rfind(b"\n") + 1      # solo líneas completas
        for line in chunk[:end].split(b"\n"):
            if b'"usage"' not in line or b'"assistant"' not in line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            msg = o.get("message") or {}
            u = msg.get("usage")
            if o.get("type") != "assistant" or not isinstance(u, dict):
                continue
            model = msg.get("model") or ""
            if model.startswith("<"):        # <synthetic>: respuestas que no gastan
                continue
            mid = msg.get("id") or o.get("uuid")
            cw = u.get("cache_creation_input_tokens") or 0
            cost = claude_cost(model, u, u.get("speed"))
            row = [round(_ts(o.get("timestamp")), 1), model, u.get("input_tokens") or 0, u.get("output_tokens") or 0,
                   cw, u.get("cache_read_input_tokens") or 0, None if cost is None else round(cost, 6), path]
            with self.lock:
                self.put(owner, mid, row)
        return off + end

    # ------------------------------------------------------------ OpenCode
    def scan_opencode(self, sid_owner):
        if not os.path.exists(OPENCODE_DB):
            return
        try:
            db = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True, timeout=2)
            rows = db.execute(
                "select m.id, m.session_id, s.parent_id, m.time_updated, m.data from session_message m "
                "left join session_v2 s on s.id = m.session_id where m.type = 'assistant' and m.time_updated > ? "
                "order by m.time_updated", (self.data.get("oc_since", 0),)).fetchall()
            db.close()
        except sqlite3.Error:
            return
        with self.lock:
            for mid, sid, parent, tu, data in rows:
                try:
                    d = json.loads(data)
                except ValueError:
                    continue
                tok = d.get("tokens") or {}
                cache = tok.get("cache") or {}
                model = (d.get("model") or {}).get("id") or ""
                prov = (d.get("model") or {}).get("providerID") or ""
                t = ((d.get("time") or {}).get("created") or tu) / 1000
                owner = sid_owner.get(sid) or sid_owner.get(parent) or OTHER_OC
                row = [round(t, 1), f"{prov}/{model}" if prov else model, tok.get("input") or 0,
                       (tok.get("output") or 0) + (tok.get("reasoning") or 0), cache.get("write") or 0,
                       cache.get("read") or 0, round(float(d.get("cost") or 0), 6), "opencode"]
                self.put(owner, mid, row)
                self.data["oc_since"] = max(self.data.get("oc_since", 0), tu)

    # ------------------------------------------------------------ consultas
    def window(self, key, t0, t1):
        with self.lock:
            rows = [r for r in self.data["entries"].get(key, {}).values() if t0 <= r[0] <= t1]
        return sum(r[6] or 0 for r in rows), len(rows)


LEDGER = Ledger()
_scan_lock = threading.Lock()


def _owners():
    import roster
    r = roster.load()
    owners = {}
    for m in r["members"]:
        if m.get("sessionId"):
            owners[m["sessionId"]] = "m:" + m["id"]
        LEDGER.data["names"]["m:" + m["id"]] = m["name"]
    return owners, r


def scan(only_paths=None):
    with _scan_lock:
        owners, _ = _owners()
        LEDGER.scan_claude(owners, only_paths)
        LEDGER.scan_opencode(owners)
        LEDGER.ready = True
        LEDGER.save()


def start_background(every=30):
    def loop():
        while True:
            try:
                scan()
            except Exception as e:  # noqa: BLE001 - que un fallo no pare el hilo
                print("usage: fallo al escanear:", e)
            time.sleep(every)
    threading.Thread(target=loop, daemon=True).start()


def record_run(member, started, finished, prompt, error, reported_cost=None, denials=None):
    """Se llama al terminar una orden del chat: apunta lo que costó en data/runs.jsonl."""
    import roster
    paths = []
    if member["engine"] == "claude":
        tp = roster.claude_transcript(member)
        if tp:
            paths = [tp] + glob.glob(os.path.join(os.path.splitext(tp)[0], "subagents", "*.jsonl"))
    try:
        scan(paths)
    except Exception as e:  # noqa: BLE001
        print("usage: fallo al escanear la orden:", e)
    cost, msgs = LEDGER.window("m:" + member["id"], started - 2, finished + 2)
    rec = {"t": round(finished, 1), "start": round(started, 1), "member": member["id"], "name": member["name"],
           "engine": member["engine"], "model": member.get("model") or "", "prompt": (prompt or "")[:160],
           "cost": round(cost, 6), "reported": reported_cost, "msgs": msgs, "error": error,
           "denials": denials or []}
    os.makedirs(DATA, exist_ok=True)
    with open(RUNS_FILE, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _runs(limit=60):
    try:
        with open(RUNS_FILE) as f:
            lines = f.readlines()[-limit:]
    except OSError:
        return []
    out = []
    for ln in reversed(lines):
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return out


def gasto_hoy():
    """Coste estimado de las órdenes de hoy (desde medianoche, hora local)."""
    hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    return round(sum(float(r.get("cost") or 0) for r in _runs(limit=100000) if (r.get("t") or 0) >= hoy), 4)


def report(days=30):
    _, r = _owners()
    teams = {t["id"]: t for t in r["teams"]}
    now = time.time()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    day_keys = [datetime.fromtimestamp(today - 86400 * i).strftime("%Y-%m-%d") for i in range(days - 1, -1, -1)]
    agents, by_day = [], {d: {} for d in day_keys}
    members = {"m:" + m["id"]: m for m in r["members"]}
    with LEDGER.lock:
        keys = list(dict.fromkeys(list(members) + list(LEDGER.data["entries"])))
        for key in keys:
            rows = list(LEDGER.data["entries"].get(key, {}).values())
            m = members.get(key)
            if not rows and not m:
                continue
            a = {"key": key, "today": 0.0, "week": 0.0, "month": 0.0, "total": 0.0, "msgs": len(rows),
                 "tokIn": 0, "tokOut": 0, "tokCache": 0, "last": max((x[0] for x in rows), default=None),
                 "unpriced": 0, "models": {}}
            for t, model, i, o, cw, cr, c, _src in rows:
                c = c or 0
                if c == 0 and model.startswith("claude") and price_for(model) is None:
                    a["unpriced"] += 1
                a["total"] += c
                a["tokIn"] += i + cw; a["tokOut"] += o; a["tokCache"] += cr
                a["models"][model] = a["models"].get(model, 0) + c
                if t >= today:
                    a["today"] += c
                if t >= now - 7 * 86400:
                    a["week"] += c
                if t >= today - (days - 1) * 86400:
                    a["month"] += c
                    d = datetime.fromtimestamp(t).strftime("%Y-%m-%d")
                    if d in by_day:
                        by_day[d][key] = by_day[d].get(key, 0) + c
            if m:
                tm = teams.get(m.get("team")) or {}
                a.update(name=m["name"], engine=m["engine"], model=m.get("model") or "", team=tm.get("name"),
                         member=m["id"], kind="member")
            elif key == OTHER_CC:
                a.update(name="Otras sesiones de Claude Code", engine="claude", kind="other")
            elif key == OTHER_OC:
                a.update(name="Otras sesiones de OpenCode", engine="opencode", kind="other")
            else:
                a.update(name=(LEDGER.data["names"].get(key) or key) + " (ya no está)", kind="former",
                         engine="claude" if any(x[1].startswith("claude") for x in rows) else "opencode")
            agents.append(a)
    return {"now": now, "ready": LEDGER.ready, "agents": agents,
            "days": [{"date": d, "by": by_day[d]} for d in day_keys], "runs": _runs(),
            "prices": {k: v for k, v in PRICES.items()}}
