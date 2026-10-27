"""Pruebas de los scripts de integración con Graphify (sin Graphify instalado).

Correr desde motor/:  python -m unittest discover -s graphify/pruebas -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CARPETA = Path(__file__).resolve().parents[1]


def correr(script, *args, entrada="", **env):
    return subprocess.run([sys.executable, str(CARPETA / script), *args], input=entrada, capture_output=True,
                          text=True, encoding="utf-8", timeout=30, env={**os.environ, **env})


class HookGuard(unittest.TestCase):
    def test_sin_grafo_no_hace_nada_y_sale_con_cero(self):
        with tempfile.TemporaryDirectory() as t:
            for modo in ("search", "read", "raro"):
                r = correr("hook_guard.py", modo, CLAUDE_PROJECT_DIR=t)
                self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_desactivado_por_variable(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "graphify-out").mkdir()
            (Path(t) / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
            r = correr("hook_guard.py", "search", CLAUDE_PROJECT_DIR=t, GRAPHIFY_GUARDIA="0")
            self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_con_grafo_pero_sin_graphify_instalado_no_falla(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "graphify-out").mkdir()
            (Path(t) / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
            r = correr("hook_guard.py", "read", CLAUDE_PROJECT_DIR=t, PATH=t, HOME=t, USERPROFILE=t)
            self.assertEqual(r.returncode, 0)

    def test_no_usa_bash(self):
        texto = (CARPETA / "hook_guard.py").read_text(encoding="utf-8")
        self.assertNotIn("bash", texto.split('"""', 2)[2])  # el código (no la docstring) no lanza bash


class RevisarGrafo(unittest.TestCase):
    def grafo(self, contenido):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        (Path(t.name) / "graph.json").write_text(json.dumps(contenido), encoding="utf-8")
        return t.name

    def test_grafo_limpio(self):
        r = correr("revisar_grafo.py", self.grafo({"nodes": [{"label": "funcion_normal"}]}))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_detecta_literales_sensibles(self):
        carpeta = self.grafo({"nodes": [{"label": "persona@ejemplo.org"}, {"label": "ghp_" + "a" * 30},
                                        {"label": "C:\\Users\\alguien\\x"}]})
        r = correr("revisar_grafo.py", carpeta)
        self.assertEqual(r.returncode, 1)
        for clave in ("correo", "token_github", "ruta_usuario"):
            self.assertIn(clave, r.stdout)

    def test_permitir_falsos_positivos(self):
        carpeta = self.grafo({"nodes": [{"label": "persona@ejemplo.org"}]})
        self.assertEqual(correr("revisar_grafo.py", carpeta, "--permitir", "ejemplo").returncode, 0)


class SesionInicio(unittest.TestCase):
    def test_sin_grafo_no_imprime_nada(self):
        with tempfile.TemporaryDirectory() as t:
            r = correr("sesion_inicio.py", entrada=json.dumps({"cwd": t}), CLAUDE_PROJECT_DIR=t)
            self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_con_grafo_inyecta_contexto(self):
        with tempfile.TemporaryDirectory() as t:
            carpeta = Path(t) / "graphify-out"
            carpeta.mkdir()
            (carpeta / "graph.json").write_text("{}", encoding="utf-8")
            (carpeta / "GRAPH_REPORT.md").write_text("## Summary\n- 10 nodos\n", encoding="utf-8")
            r = correr("sesion_inicio.py", entrada="{}", CLAUDE_PROJECT_DIR=t)
            self.assertEqual(r.returncode, 0)
            salida = json.loads(r.stdout)["hookSpecificOutput"]
            self.assertEqual(salida["hookEventName"], "SessionStart")
            self.assertIn("Graphify", salida["additionalContext"])


if __name__ == "__main__":
    unittest.main()
