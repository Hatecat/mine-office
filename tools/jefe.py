#!/usr/bin/env python3
"""Buzón del jefe: los agentes de la oficina le piden cosas a Claude (el jefe) y él les contesta.

  jefe.py pedir "texto"            un agente pide algo (instalar, descargar, permisos, una decisión…)
  jefe.py lista [--todas]          peticiones pendientes (o todas)
  jefe.py responder ID "texto"     el jefe contesta: se cierra la petición y la respuesta llega al
                                   agente como una orden nueva en su chat
  jefe.py cerrar ID                cerrar sin contestar
  jefe.py investigar "texto"       encargar una consulta sencilla o una búsqueda en internet al investigador
                                   de la oficina (el miembro con puesto «Investigador»)

Quién pide se sabe por la variable OFFICE_MEMBER, que la oficina pone al lanzar a cada agente.
Las peticiones viven en data/peticiones.json; cada una deja un aviso en events.jsonl (globo + Liberty).
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("OFICINA_DATOS") or os.path.join(HERE, "data")   # la oficina lo pone al lanzar a cada agente

try:
    import fcntl

    def _bloquear(f, bloquear):
        fcntl.flock(f, fcntl.LOCK_EX if bloquear else fcntl.LOCK_UN)
except ImportError:                      # Windows
    import msvcrt

    def _bloquear(f, bloquear):
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK if bloquear else msvcrt.LK_UNLCK, 1)
FILE = os.path.join(DATA, "peticiones.json")
EVENTS = os.path.join(DATA, "events.jsonl")
SERVER = f"http://127.0.0.1:{os.environ.get('OFICINA_PUERTO') or 8765}"


class Store:
    """Lee y escribe peticiones.json con bloqueo (varios agentes pueden pedir a la vez)."""
    def __enter__(self):
        os.makedirs(DATA, exist_ok=True)
        self.f = open(FILE, "a+")
        _bloquear(self.f, True)
        self.f.seek(0)
        try:
            self.data = json.loads(self.f.read() or "{}")
        except ValueError:
            self.data = {}
        self.data.setdefault("next", 1)
        self.data.setdefault("items", [])
        return self.data

    def __exit__(self, *exc):
        if exc[0] is None:
            self.f.seek(0); self.f.truncate()
            json.dump(self.data, self.f, ensure_ascii=False, indent=1)
        _bloquear(self.f, False)
        self.f.close()


def member():
    mid = os.environ.get("OFFICE_MEMBER", "")
    try:
        with open(os.path.join(DATA, "roster.json")) as f:
            r = json.load(f)
        for m in r["members"]:
            if m["id"] == mid:
                return m
        if mid in ("jefe", "liberty"):         # el jefe y la secretaria no son miembros contratados
            v = (r.get("virtual") or {}).get(mid) or {}
            return {"id": mid, "name": {"jefe": "Claude", "liberty": "Liberty"}[mid], "sessionId": v.get("sessionId")}
    except (OSError, ValueError, KeyError):
        pass
    return None


def event(sid, ev, msg):
    with open(EVENTS, "a") as f:
        f.write(json.dumps({"t": round(time.time(), 2), "sid": sid, "ev": ev, "type": "", "msg": msg[:200]},
                           ensure_ascii=False) + "\n")


def cmd_pedir(a):
    text = " ".join(a.texto.split()).strip()
    if not text:
        sys.exit("La petición está vacía.")
    m = member()
    who, mid = (m["name"], m["id"]) if m else (os.environ.get("OFFICE_MEMBER") or "alguien", None)
    with Store() as d:
        pid = d["next"]; d["next"] += 1
        d["items"].append({"id": pid, "t": time.time(), "from": mid, "name": who, "text": text[:2000],
                           "estado": "pendiente", "entregada": False})
    event(m.get("sessionId") if m else "jefe", "BossAsk", f"{who} le pide al jefe: {text}")
    print(f"Petición #{pid} enviada al jefe (Claude). Liberty se la anuncia al usuario y, cuando Claude la "
          "atienda, su respuesta te llegará como un mensaje nuevo en tu chat. No hace falta que esperes: "
          "termina tu turno diciendo al usuario qué has pedido.")


def cmd_lista(a):
    with Store() as d:
        items = [i for i in d["items"] if a.todas or i["estado"] == "pendiente"]
    if not items:
        print("No hay peticiones pendientes.")
    for i in items:
        print(f"#{i['id']} [{i['estado']}] {time.strftime('%d/%m %H:%M', time.localtime(i['t']))} "
              f"{i['name']}: {i['text']}" + (f"\n    respuesta: {i['respuesta']}" if i.get("respuesta") else ""))


def _close(pid, estado, respuesta=None):
    with Store() as d:
        for i in d["items"]:
            if i["id"] == pid:
                i.update(estado=estado, cerrada=time.time(), respuesta=respuesta)
                return i
    sys.exit(f"No existe la petición #{pid}.")


def cmd_responder(a):
    i = _close(a.id, "respondida", a.texto)
    if not i.get("from"):
        print("Petición cerrada (no venía de un miembro de la oficina, no hay a quién mandarla)."); return
    msg = (f"Mensaje de Claude, el jefe, sobre tu petición #{i['id']} («{i['text'][:200]}»):\n\n{a.texto}\n\n"
           "Sigue con tu trabajo teniéndolo en cuenta.")
    try:
        token = open(os.path.join(DATA, "token")).read().strip()
        req = urllib.request.Request(SERVER + "/api/order", data=json.dumps({"id": i["from"], "text": msg}).encode(),
                                     headers={"Content-Type": "application/json", "X-Office-Token": token})
        urllib.request.urlopen(req, timeout=10).read()
        print(f"Respuesta enviada a {i['name']}; ya está trabajando con ella.")
    except Exception as e:  # noqa: BLE001
        print(f"Petición cerrada, pero no pude mandar la respuesta a {i['name']} ({e}). ¿Está la oficina abierta?")


def _order(mid, text):
    token = open(os.path.join(DATA, "token")).read().strip()
    req = urllib.request.Request(SERVER + "/api/order", data=json.dumps({"id": mid, "text": text}).encode(),
                                 headers={"Content-Type": "application/json", "X-Office-Token": token})
    urllib.request.urlopen(req, timeout=10).read()


def cmd_investigar(a):
    text = " ".join(a.texto.split()).strip()
    if not text:
        sys.exit("El encargo está vacío.")
    try:
        with open(os.path.join(DATA, "roster.json")) as f:
            inv = next((m for m in json.load(f)["members"] if (m.get("job") or "").lower() == "investigador"), None)
    except (OSError, ValueError, KeyError):
        inv = None
    if not inv:
        sys.exit("No hay ningún miembro con el puesto «Investigador» en la oficina.")
    m = member()
    who = m["name"] if m else ("Liberty" if os.environ.get("OFFICE_MEMBER") == "liberty" else "el jefe")
    try:
        _order(inv["id"], f"Encargo de investigación (te lo pasa {who} de parte del usuario):\n\n{text[:2000]}\n\n"
                          "Responde al usuario directamente, breve y citando las fuentes que hayas consultado. "
                          "EMPIEZA tu respuesta con una sola línea «Resumen: …» de una o dos frases que Liberty leerá "
                          "en voz alta: lenguaje hablado, sin enlaces, URLs, markdown ni listas. Debajo, la respuesta "
                          "completa con sus fuentes.")
    except urllib.error.HTTPError as e:
        sys.exit(f"{inv['name']} no puede recibirlo ahora ({e.read().decode(errors='replace')[:200]}). Prueba en un rato.")
    except Exception as e:  # noqa: BLE001
        sys.exit(f"No pude mandar el encargo a {inv['name']} ({e}). ¿Está la oficina abierta?")
    event(inv.get("sessionId") or "jefe", "Say", f"{who} le pasa a {inv['name']} una consulta: {text}")
    print(f"Encargo enviado a {inv['name']}; la respuesta aparecerá en su chat.")


def cmd_cerrar(a):
    _close(a.id, "cerrada"); print(f"Petición #{a.id} cerrada.")


def pending_for_hook():
    """Para el hook del jefe: peticiones pendientes aún no entregadas (y las marca como entregadas)."""
    if not os.path.exists(FILE):
        return []
    with Store() as d:
        new = [i for i in d["items"] if i["estado"] == "pendiente" and not i.get("entregada")]
        for i in new:
            i["entregada"] = True
    return new


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pedir"); p.add_argument("texto")
    p = sub.add_parser("lista"); p.add_argument("--todas", action="store_true")
    p = sub.add_parser("responder"); p.add_argument("id", type=int); p.add_argument("texto")
    p = sub.add_parser("cerrar"); p.add_argument("id", type=int)
    p = sub.add_parser("investigar"); p.add_argument("texto")
    a = ap.parse_args()
    {"pedir": cmd_pedir, "lista": cmd_lista, "responder": cmd_responder, "cerrar": cmd_cerrar,
     "investigar": cmd_investigar}[a.cmd](a)


if __name__ == "__main__":
    main()
