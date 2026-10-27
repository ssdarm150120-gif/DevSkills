"""Pruebas del panel (solo biblioteca estándar; el único tráfico es loopback).

Correr desde motor/:  python -m unittest discover -s panel/pruebas -v
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

MOTOR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MOTOR))
sys.path.insert(0, str(MOTOR / "panel"))

import panel  # noqa: E402

PLANTILLA = MOTOR / "plantillas" / "proyectos.ejemplo.json"


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Registro(unittest.TestCase):
    def test_la_plantilla_de_ejemplo_es_valida(self):
        datos = json.loads(PLANTILLA.read_text(encoding="utf-8"))
        reg = panel.validar_registro(datos)
        self.assertEqual([p["id"] for p in reg["proyectos"]], ["ejemplo"])
        self.assertEqual(set(reg["servicios"]), {"ejemplo-api", "ejemplo-web"})
        # '~/...' se expande a la carpeta personal de quien usa el panel
        self.assertEqual(reg["proyectos"][0]["carpeta"], os.path.expanduser("~/proyectos/ejemplo"))

    def test_rutas_absolutas_de_windows_y_posix(self):
        for ok in ("C:\\x", "c:/x", "/home/u/x"):
            self.assertTrue(panel.es_ruta_absoluta(ok), ok)
        for mal in ("x", "./x", "~/x", "", None, 5):
            self.assertFalse(panel.es_ruta_absoluta(mal), mal)

    def test_carpeta_relativa_se_rechaza(self):
        datos = {"proyectos": [{"id": "a", "carpeta": "relativa/x"}]}
        with self.assertRaises(panel.ErrorRegistro):
            panel.validar_registro(datos)

    def test_tipo_de_arranque_fuera_de_la_lista_blanca(self):
        carpeta = str(Path(tempfile.gettempdir()).resolve())
        datos = {"proyectos": [{"id": "a", "carpeta": carpeta, "servicios": [
            {"id": "a-x", "puertos": [20000], "url": "http://localhost:20000", "arranque": {"tipo": "bash"}}]}]}
        with self.assertRaises(panel.ErrorRegistro):
            panel.validar_registro(datos)

    def test_raices_de_deteccion(self):
        self.assertEqual(panel.validar_raices(["/srv/x"]), ["/srv/x"])
        with self.assertRaises(panel.ErrorRegistro):
            panel.validar_raices(["/srv/../etc"])
        with self.assertRaises(panel.ErrorRegistro):
            panel.validar_raices(["relativa"])

    def test_tipos_del_panel_y_del_lanzador_coinciden(self):
        from servicios import servicios as sv
        self.assertEqual(panel.TIPOS_ARRANQUE, set(sv.TIPOS_PERMITIDOS))


class Comandos(unittest.TestCase):
    def test_retomar_en_posix_y_windows(self):
        sesion = "11111111-2222-3333-4444-555555555555"
        r = panel.comando_retomar("/home/u/mi proyecto", sesion)
        self.assertEqual(r["comando"], f"cd '/home/u/mi proyecto'\nclaude --resume {sesion}")
        r = panel.comando_retomar("C:\\Proyectos\\x", sesion)
        self.assertEqual(r["comando"], f'cd "C:\\Proyectos\\x"\nclaude --resume {sesion}')

    def test_comilla_simple_en_posix(self):
        self.assertEqual(panel.comando_iniciar("/tmp/o'brien")["comando"], "cd '/tmp/o'\\''brien'\nclaude")

    def test_rutas_invalidas(self):
        self.assertIsNone(panel.comando_iniciar("relativa")["comando"])
        self.assertIsNone(panel.comando_iniciar("/tmp/x\ny")["comando"])
        self.assertIsNone(panel.comando_retomar("/tmp/x", "no-es-uuid")["comando"])


class Estado(unittest.TestCase):
    def test_el_estado_sale_de_devskills_datos(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.dict(os.environ, {"DEVSKILLS_DATOS": t}):
            base = Path(t).resolve()
            self.assertEqual(panel.archivo_token(18953), base / "panel" / ".token-18953")
            self.assertEqual(panel.archivo_preferencias(18950), base / "preferencias.json")
            self.assertEqual(panel.carpeta_estado_por_omision(18953), base / "panel" / "estado-18953")

    def test_puertos_en_escucha_no_falla(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            puerto = s.getsockname()[1]
            escuchando = panel.puertos_en_escucha()
            if escuchando is not None:  # sin netstat/ss/lsof se devuelve None y el panel sondea puerto por puerto
                self.assertIn(puerto, escuchando)
            self.assertTrue(panel.puerto_escucha(puerto))


class Servidor(unittest.TestCase):
    """Levanta el panel real en un puerto libre, con --simular y un directorio de datos temporal."""

    def test_arranca_responde_y_se_apaga(self):
        with tempfile.TemporaryDirectory() as t:
            datos = Path(t).resolve()
            registro = datos / "proyectos.json"
            registro.write_text(PLANTILLA.read_text(encoding="utf-8"), encoding="utf-8")
            puerto = puerto_libre()
            env = {**os.environ, "DEVSKILLS_DATOS": str(datos), "PYTHONIOENCODING": "utf-8"}
            base = [sys.executable, str(MOTOR / "panel" / "panel.py")]
            proceso = subprocess.Popen([*base, "servir", "--simular", "--puerto", str(puerto)], env=env,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                url = f"http://127.0.0.1:{puerto}"
                for _ in range(60):
                    try:
                        with urllib.request.urlopen(url + "/api/ping", timeout=1) as r:
                            self.assertTrue(json.loads(r.read())["panel"])
                            break
                    except OSError:
                        time.sleep(0.25)
                else:
                    self.fail("el panel no respondió")
                self.assertTrue((datos / "panel" / f".token-{puerto}").exists())
                # sin token, la API de lectura se rechaza
                with self.assertRaises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen(url + "/api/proyectos", timeout=3)
                self.assertIn(e.exception.code, (401, 403))
                subprocess.run([*base, "apagar", "--puerto", str(puerto)], env=env, timeout=20,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                proceso.wait(timeout=15)
                self.assertFalse((datos / "panel" / f".token-{puerto}").exists())
            finally:
                if proceso.poll() is None:
                    proceso.kill()
                    proceso.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
