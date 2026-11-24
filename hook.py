#!/usr/bin/env python3
"""Hook de Claude Code (Notification, Stop y UserPromptSubmit): apunta el aviso en data/events.jsonl para que la
oficina muestre un globo encima del agente. Nunca falla ni bloquea: sale siempre con código 0."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def boss_inbox(d):
    """En la sesión del jefe (Claude en la carpeta personal), cada mensaje del usuario lleva pegadas las
    peticiones nuevas que le han hecho los agentes."""
    try:
        with open(os.path.join(os.environ.get("OFICINA_DATOS") or os.path.join(HERE, "data"), "roster.json")) as f:
            r = json.load(f)
    except (OSError, ValueError):
        return
    sid = d.get("session_id")
    if sid in {m.get("sessionId") for m in r.get("members", [])} | {v.get("sessionId") for v in (r.get("virtual") or {}).values()}:
        return                                           # un agente de la oficina, no el jefe
    fixed = (r.get("boss") or {}).get("sessionId")
    if (fixed and sid != fixed) or (not fixed and os.path.realpath(d.get("cwd") or "") != os.path.expanduser("~")):
        return
    sys.path.insert(0, os.path.join(HERE, "tools"))
    import jefe
    new = jefe.pending_for_hook()
    if not new:
        return
    lines = [f"#{i['id']} de {i['name']}: {i['text']}" for i in new]
    ctx = ("Buzón de la oficina de agentes: tienes peticiones nuevas de tu equipo (eres su jefe). Cuéntaselas al "
           "usuario, atiéndelas si procede y contesta a cada agente con: python3 " + os.path.join(HERE, "tools", "jefe.py")
           + " responder ID \"respuesta\" (o «lista» para verlas todas).\n" + "\n".join(lines))
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}))


try:
    d = json.load(sys.stdin)
    rec = {"t": round(time.time(), 2), "sid": d.get("session_id"), "ev": d.get("hook_event_name"),
           "type": d.get("notification_type") or "", "msg": str(d.get("message") or "")[:200]}
    if rec["sid"] and rec["ev"] == "UserPromptSubmit":
        boss_inbox(d)
    elif rec["sid"] and rec["ev"] in ("Notification", "Stop"):
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "events.jsonl")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
except Exception:  # noqa: BLE001
    pass
sys.exit(0)
