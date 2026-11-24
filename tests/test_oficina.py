"""Pruebas de lo que más puede romperse en silencio. Solo biblioteca estándar.

Ejecutar desde la carpeta del proyecto:  python3 -m unittest discover -s tests -v
Usan una carpeta temporal para OFICINA_DATOS, así que no tocan data/ del proyecto.
"""
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

TMP = tempfile.mkdtemp(prefix="oficina-test-")
os.environ["OFICINA_DATOS"] = TMP
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import ajustes  # noqa: E402
import plataforma  # noqa: E402
import roster  # noqa: E402


class AjustesTest(unittest.TestCase):
    def test_nombre_vacio_se_rechaza(self):
        with self.assertRaises(ValueError):
            ajustes.validar({"jefe": "   "})

    def test_hace_falta_al_menos_un_motor(self):
        with self.assertRaises(ValueError):
            ajustes.validar({"motores": {"claude": False, "opencode": False, "kimi": False}})

    def test_modo_de_ahorro_invalido(self):
        with self.assertRaises(ValueError):
            ajustes.validar({"ahorro": "raro"})

    def test_valores_validos_se_guardan_limpios(self):
        limpio = ajustes.validar({"jefe": "  Ana  ", "ahorro": "gratis", "configurado": True,
                                  "motores": {"claude": True, "opencode": False, "kimi": False}})
        self.assertEqual(limpio["jefe"], "Ana")
        self.assertEqual(limpio["ahorro"], "gratis")
        self.assertTrue(limpio["configurado"])

    def test_es_gratis(self):
        self.assertTrue(ajustes.es_gratis("opencode/glm-5-free"))
        self.assertTrue(ajustes.es_gratis("openrouter/google/gemma-4-31b-it:free"))
        self.assertTrue(ajustes.es_gratis("opencode/big-pickle"))
        self.assertFalse(ajustes.es_gratis("openai/gpt-6.2-astra"))
        self.assertFalse(ajustes.es_gratis(None))

    def test_modelo_de_liberty_se_valida_y_se_guarda(self):
        limpio = ajustes.validar({"modeloLiberty": "claude-haiku-5-5"})
        self.assertEqual(limpio["modeloLiberty"], "claude-haiku-5-5")
        with self.assertRaises(ValueError):
            ajustes.validar({"modeloLiberty": "gpt-6; rm -rf /"})

    def test_liberty_usa_el_modelo_elegido(self):
        ajustes.guardar({**ajustes.DEFECTO, "modeloLiberty": "claude-haiku-5-5", "configurado": True})
        with mock.patch.object(roster, "load", return_value={"members": [], "virtual": {}}):
            self.assertEqual(roster.virtual_member("liberty")["model"], "claude-haiku-5-5")
        ajustes.guardar({**ajustes.DEFECTO, "configurado": True})

    def test_proveedores_opencode_lee_los_guardados(self):
        salida = ("GitHub Copilot  GitHub Copilot   stored\n"
                  "Groq            Groq             stored\n"
                  "Cerebras        Cerebras         missing\n")
        with mock.patch.object(ajustes, "which", return_value="/usr/bin/opencode"), \
             mock.patch.object(ajustes.subprocess, "run",
                               return_value=types.SimpleNamespace(stdout=salida)):
            self.assertEqual(ajustes.proveedores_opencode(), ["GitHub Copilot", "Groq"])


class AhorroTest(unittest.TestCase):
    """_aplicar_ahorro: solo cambia modelos de pago de OpenCode, y solo con el modo «gratis»."""

    def setUp(self):
        ajustes.guardar({**ajustes.DEFECTO, "ahorro": "gratis", "configurado": True})
        self.eventos = []
        sys.modules["server"] = types.SimpleNamespace(
            add_event=lambda sid, ev, msg="", limit=200: self.eventos.append((sid, ev, msg)))
        self.patches = [
            mock.patch.object(roster, "models", return_value={"opencode": [
                {"id": "opencode/big-pickle"}, {"id": "openrouter/x:free"}]}),
            mock.patch.object(roster, "find_pm", return_value=None),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        sys.modules.pop("server", None)
        ajustes.guardar({**ajustes.DEFECTO, "configurado": True})

    def test_cambia_un_modelo_de_pago_de_opencode(self):
        m = roster._aplicar_ahorro({"id": "x", "engine": "opencode", "model": "openai/gpt-6.2-astra"}, "ses_1")
        self.assertEqual(m["model"], "opencode/big-pickle")
        self.assertEqual(len(self.eventos), 1)

    def test_no_toca_a_claude(self):
        m = roster._aplicar_ahorro({"id": "x", "engine": "claude", "model": "claude-opus-5-5"}, "s")
        self.assertEqual(m["model"], "claude-opus-5-5")

    def test_no_cambia_un_modelo_ya_gratis(self):
        m = roster._aplicar_ahorro({"id": "x", "engine": "opencode", "model": "opencode/glm-5-free"}, "s")
        self.assertEqual(m["model"], "opencode/glm-5-free")

    def test_modo_normal_no_cambia_nada(self):
        ajustes.guardar({**ajustes.DEFECTO, "ahorro": "normal", "configurado": True})
        m = roster._aplicar_ahorro({"id": "x", "engine": "opencode", "model": "openai/gpt-6.2-astra"}, "s")
        self.assertEqual(m["model"], "openai/gpt-6.2-astra")


class PresupuestoTest(unittest.TestCase):
    def setUp(self):
        import usage
        self.tmp = tempfile.NamedTemporaryFile("w", delete=False, suffix=".jsonl")
        self.tmp.close()
        self.p = mock.patch.object(usage, "RUNS_FILE", self.tmp.name)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        os.unlink(self.tmp.name)
        ajustes.guardar({**ajustes.DEFECTO, "configurado": True})

    def test_presupuesto_no_valido(self):
        for malo in (-1, "mucho", 99999):
            with self.assertRaises(ValueError):
                ajustes.validar({"presupuestoDia": malo})
        self.assertEqual(ajustes.validar({"presupuestoDia": "2.5"})["presupuestoDia"], 2.5)

    def test_gasto_de_hoy_suma_solo_lo_de_hoy(self):
        import json, time, usage
        with open(self.tmp.name, "w") as f:
            f.write(json.dumps({"t": time.time(), "cost": 1.25}) + "\n")
            f.write(json.dumps({"t": time.time() - 3 * 86400, "cost": 9.0}) + "\n")
        self.assertEqual(usage.gasto_hoy(), 1.25)

    def test_frena_ordenes_de_pago_al_llegar_al_limite(self):
        import usage
        ajustes.guardar({**ajustes.DEFECTO, "presupuestoDia": 1.0, "configurado": True})
        with mock.patch.object(usage, "gasto_hoy", return_value=1.5):
            with self.assertRaises(ValueError):
                roster._freno_presupuesto({"model": "claude-opus-5-5"})

    def test_modelos_gratuitos_no_se_frenan(self):
        import usage
        ajustes.guardar({**ajustes.DEFECTO, "presupuestoDia": 1.0, "configurado": True})
        with mock.patch.object(usage, "gasto_hoy", return_value=5.0):
            roster._freno_presupuesto({"model": "opencode/big-pickle"})  # no lanza

    def test_limite_cero_no_frena(self):
        import usage
        ajustes.guardar({**ajustes.DEFECTO, "presupuestoDia": 0, "configurado": True})
        with mock.patch.object(usage, "gasto_hoy", return_value=500.0):
            roster._freno_presupuesto({"model": "claude-opus-5-5"})


class ModelosLocalesTest(unittest.TestCase):
    def setUp(self):
        import modelos_locales
        self.dir = tempfile.mkdtemp(prefix="ml-")
        self.p = [mock.patch.object(modelos_locales, "CONFIG", os.path.join(self.dir, "opencode.json")),
                  mock.patch.object(modelos_locales, "REGISTRO", os.path.join(self.dir, "reg.json"))]
        for x in self.p:
            x.start()
        self.ml = modelos_locales

    def tearDown(self):
        for x in self.p:
            x.stop()

    def test_solo_servidores_de_este_equipo(self):
        with self.assertRaises(ValueError):
            self.ml.validar({"nombre": "x1", "url": "http://otro.com:11434", "modelos": ["a"]})
        with self.assertRaises(ValueError):
            self.ml.validar({"nombre": "x1", "url": "http://127.0.0.1", "modelos": ["a"]})
        n, base, m = self.ml.validar({"nombre": "ollama", "url": "http://localhost:11434/algo", "modelos": "llama3.2, qwen"})
        self.assertEqual((n, base, m), ("ollama", "http://localhost:11434/v1", ["llama3.2", "qwen"]))

    def test_agregar_y_quitar_sin_tocar_lo_de_a_mano(self):
        cfg = os.path.join(self.dir, "opencode.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"provider": {"nvidia": {"models": {}}}, "permission": {"webfetch": "allow"}}, f)
        self.ml.agregar({"nombre": "ollama", "url": "http://127.0.0.1:11434", "modelos": ["llama3.2"]})
        c = json.load(open(cfg, encoding="utf-8"))
        self.assertIn("nvidia", c["provider"])
        self.assertEqual(c["provider"]["ollama"]["options"]["baseURL"], "http://127.0.0.1:11434/v1")
        self.assertEqual(c["permission"], {"webfetch": "allow"})
        self.ml.quitar("ollama")
        c = json.load(open(cfg, encoding="utf-8"))
        self.assertNotIn("ollama", c["provider"])
        self.assertIn("nvidia", c["provider"])

    def test_no_pisa_un_proveedor_a_mano(self):
        cfg = os.path.join(self.dir, "opencode.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"provider": {"groq": {"models": {}}}}, f)
        with self.assertRaises(ValueError):
            self.ml.agregar({"nombre": "groq", "url": "http://127.0.0.1:1234", "modelos": ["a"]})

    def test_no_toca_una_configuracion_invalida(self):
        cfg = os.path.join(self.dir, "opencode.json")
        with open(cfg, "w", encoding="utf-8") as f:
            f.write("{ esto no es json")
        with self.assertRaises(ValueError):
            self.ml.agregar({"nombre": "ollama", "url": "http://127.0.0.1:11434", "modelos": ["a"]})
        self.assertEqual(open(cfg, encoding="utf-8").read(), "{ esto no es json")


class ImagenesTest(unittest.TestCase):
    def test_local_activa_el_estudio(self):
        self.assertIn("arte", roster._skills_efectivas({"engine": "claude", "imagenes": "local", "skills": []}))

    def test_propio_quita_el_estudio(self):
        self.assertNotIn("arte", roster._skills_efectivas({"engine": "claude", "imagenes": "propio", "skills": ["arte"]}))

    def test_opencode_usa_el_estudio_con_su_propio_prompt(self):
        self.assertIn("arte", roster._skills_efectivas({"engine": "opencode", "imagenes": "local", "skills": []}))

    def test_miembros_antiguos_mantienen_su_casilla(self):
        self.assertIn("arte", roster._skills_efectivas({"engine": "claude", "skills": ["arte"]}))
        self.assertEqual(roster._skills_efectivas({"engine": "claude", "skills": []}), [])

    def test_opencode_local_registra_el_servidor_mcp_y_sus_dos_herramientas(self):
        import json as _j
        env = roster._env_oc({"id": "x", "engine": "opencode", "imagenes": "local", "skills": []})
        cfg = _j.loads(env["OPENCODE_CONFIG_CONTENT"])
        self.assertEqual(cfg["mcp"]["arte"]["type"], "local")
        self.assertTrue(cfg["mcp"]["arte"]["command"][-1].endswith("arte_mcp.py"))
        self.assertEqual(cfg["permission"], {"arte_generar_imagen": "allow", "arte_estado": "allow"})

    def test_opencode_propio_no_recibe_nada(self):
        self.assertNotIn("OPENCODE_CONFIG_CONTENT", roster._env_oc({"id": "x", "engine": "opencode", "imagenes": "propio", "skills": []}))

    def test_kimi_nunca_recibe_el_estudio(self):
        self.assertNotIn("arte", roster._skills_efectivas({"engine": "kimi", "skills": ["arte"], "imagenes": "local"}))

    def test_el_prompt_del_estudio_solo_aparece_si_es_local(self):
        base = {"name": "Ana", "job": "Artista", "team": "x", "personality": "", "skills": [], "engine": "claude"}
        with mock.patch.object(roster, "_team_name", return_value="Equipo"):
            self.assertNotIn("estudio de arte", roster.persona({**base, "imagenes": "propio"}))
            self.assertIn("estudio de arte", roster.persona({**base, "imagenes": "local"}))


class CuotaTest(unittest.TestCase):
    def test_detecta_limites_de_cuota(self):
        self.assertTrue(roster.is_quota_error("Error: usage limit reached for this key"))
        self.assertTrue(roster.is_quota_error("You hit your daily limit"))
        self.assertTrue(roster.is_quota_error("HTTP 429 Too Many Requests"))
        self.assertFalse(roster.is_quota_error("Todo bien, aquí tienes el resumen"))
        self.assertFalse(roster.is_quota_error(""))


class PlataformaTest(unittest.TestCase):
    def test_pid_vivo_y_muerto(self):
        self.assertTrue(plataforma.pid_alive(os.getpid()))
        self.assertFalse(plataforma.pid_alive(999999999))

    @unittest.skipIf(plataforma.WIN, "killpg solo en POSIX")
    def test_kill_tree_para_el_proceso(self):
        p = subprocess.Popen(["sleep", "30"], **plataforma.new_group_kwargs())
        plataforma.kill_tree(p.pid)
        p.wait(timeout=10)
        self.assertNotEqual(p.returncode, None)

    def test_script_de_windows_no_se_lanza_con_texto(self):
        with mock.patch.object(plataforma, "WIN", True):
            with self.assertRaises(ValueError):
                plataforma.ejecutable_seguro(r"C:\npm\claude.cmd")
            self.assertEqual(plataforma.ejecutable_seguro(r"C:\bin\claude.exe"), r"C:\bin\claude.exe")

    def test_puerto_desde_argumentos(self):
        with mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch.object(sys, "argv", ["server.py", "--port", "9100"]):
            os.environ.pop("OFICINA_PUERTO", None)
            self.assertEqual(plataforma._puerto(), 9100)
        with mock.patch.dict(os.environ, {"OFICINA_PUERTO": "9200"}):
            self.assertEqual(plataforma._puerto(), 9200)


if __name__ == "__main__":
    unittest.main()
