"""Pruebas de las rutas del motor: el estado vive en DEVSKILLS_DATOS o ~/.devskills, nunca junto al código.

Correr desde motor/:  python -m unittest discover -s comun/pruebas -v
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MOTOR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MOTOR))

from comun import rutas  # noqa: E402


class Rutas(unittest.TestCase):
    def test_variable_de_entorno_manda(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.dict(os.environ, {"DEVSKILLS_DATOS": t}):
            self.assertEqual(rutas.datos(), Path(t).resolve())
            self.assertEqual(rutas.registro(), Path(t).resolve() / "proyectos.json")
            self.assertEqual(rutas.orquestador_token(), Path(t).resolve() / "orquestador" / ".token")
            self.assertEqual(rutas.servicios_pids(), Path(t).resolve() / "servicios" / "pids")

    def test_por_omision_es_devskills_en_el_home(self):
        entorno = {k: v for k, v in os.environ.items() if k != "DEVSKILLS_DATOS"}
        with mock.patch.dict(os.environ, entorno, clear=True):
            self.assertEqual(rutas.datos(), Path.home() / ".devskills")

    def test_variable_vacia_se_ignora(self):
        with mock.patch.dict(os.environ, {"DEVSKILLS_DATOS": "  "}):
            self.assertEqual(rutas.datos(), Path.home() / ".devskills")

    def test_carpeta_de_claude_code_respeta_claude_config_dir(self):
        entorno = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
        with mock.patch.dict(os.environ, entorno, clear=True):
            self.assertEqual(rutas.claude_dir(), Path.home() / ".claude")
            self.assertEqual(rutas.claude_json(), Path.home() / ".claude.json")
        with tempfile.TemporaryDirectory() as t, mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": t}):
            self.assertEqual(rutas.claude_dir(), Path(t).resolve())
            self.assertEqual(rutas.claude_json(), Path(t).resolve() / ".claude.json")

    def test_instancias_de_prueba_no_pisan_la_principal(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.dict(os.environ, {"DEVSKILLS_DATOS": t}):
            self.assertEqual(rutas.panel_token(18950).name, ".token")
            self.assertEqual(rutas.panel_token(18953).name, ".token-18953")
            self.assertEqual(rutas.preferencias(18950).name, "preferencias.json")
            self.assertEqual(rutas.preferencias(18953).name, "preferencias-18953.json")
            self.assertEqual(rutas.panel_estado(18950).name, "estado")
            self.assertEqual(rutas.panel_estado(18953).name, "estado-18953")

    def test_el_estado_nunca_cae_dentro_del_codigo(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.dict(os.environ, {"DEVSKILLS_DATOS": t}):
            for ruta in (rutas.registro(), rutas.preferencias(), rutas.panel_estado(), rutas.panel_token(),
                         rutas.panel_log(), rutas.orquestador_token(), rutas.orquestador_historial(),
                         rutas.orquestador_propuestas(), rutas.orquestador_fallos(), rutas.servicios_logs()):
                self.assertFalse(str(ruta).startswith(str(rutas.CODIGO)), ruta)

    def test_python_del_venv_segun_sistema(self):
        venv = Path("v")
        esperado = Path("v/Scripts/python.exe") if os.name == "nt" else Path("v/bin/python")
        self.assertEqual(rutas.python_del_venv(venv), esperado)


if __name__ == "__main__":
    unittest.main()
