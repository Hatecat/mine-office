"""Pruebas de lo que más puede romperse en silencio. Solo biblioteca estándar.

Ejecutar desde la carpeta del proyecto:  python3 -m unittest discover -s tests -v
Usan una carpeta temporal para OFICINA_DATOS, así que no tocan data/ del proyecto.
"""
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
