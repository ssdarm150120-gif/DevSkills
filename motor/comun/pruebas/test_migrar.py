"""Pruebas de la migración de datos desde una instalación previa estilo _servicios.

Correr desde motor/:  python -m unittest discover -s comun/pruebas -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

MOTOR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MOTOR))

from comun import migrar  # noqa: E402


def escribir(ruta: Path, texto: str = "x") -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")


class Migrar(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.base = Path(t.name).resolve()
        self.origen = self.base / "previa"
        self.destino = self.base / "datos"
        for ruta, texto in {
            "proyectos.json": '{"proyectos": []}',
            "panel/preferencias.json": '{"acento": "#ffffff"}',
            "panel/estado/acciones.json": "{}",
            "panel/estado/avisos.json": "[]",
            "panel/estado-18953/avisos.json": "[]",
            "panel/.token": "SECRETO",
            "panel/.token-18953": "SECRETO",
            "panel/panel.log": "log",
            "orquestador/.token": "SECRETO",
            "orquestador/orquestador.log": "log",
            "orquestador/historial/a.json": "{}",
            "orquestador/propuestas/p.json": "{}",
            "orquestador/sesiones_propias.json": "[]",
            "orquestador/config.json": "{}",
            "orquestador/enrutamiento-fallos.jsonl": "",
            "orquestador/.venv/Lib/x.py": "no",
            "orquestador/nucleo/__pycache__/x.pyc": "no",
        }.items():
            escribir(self.origen / ruta, texto)

    def relativos(self, base: Path) -> set:
        return {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}

    def test_copia_datos_y_excluye_secretos_logs_y_venv(self):
        informe = migrar.migrar(self.origen, self.destino)
        esperado = {"proyectos.json", "preferencias.json", "panel/estado/acciones.json", "panel/estado/avisos.json",
                    "panel/estado-18953/avisos.json", "orquestador/historial/a.json",
                    "orquestador/propuestas/p.json", "orquestador/sesiones_propias.json",
                    "orquestador/config.json", "orquestador/enrutamiento-fallos.jsonl"}
        self.assertEqual(self.relativos(self.destino), esperado)
        self.assertEqual(len(informe["copiados"]), len(esperado))

    def test_no_toca_el_origen(self):
        antes = {p: p.read_bytes() for p in self.origen.rglob("*") if p.is_file()}
        migrar.migrar(self.origen, self.destino)
        despues = {p: p.read_bytes() for p in self.origen.rglob("*") if p.is_file()}
        self.assertEqual(antes, despues)

    def test_no_sobrescribe_salvo_con_forzar(self):
        escribir(self.destino / "proyectos.json", "MIO")
        informe = migrar.migrar(self.origen, self.destino)
        self.assertEqual((self.destino / "proyectos.json").read_text(encoding="utf-8"), "MIO")
        self.assertIn(str(self.destino / "proyectos.json"), informe["omitidos"])
        migrar.migrar(self.origen, self.destino, forzar=True)
        self.assertEqual((self.destino / "proyectos.json").read_text(encoding="utf-8"), '{"proyectos": []}')

    def test_origen_inexistente_o_igual_al_destino(self):
        with self.assertRaises(SystemExit):
            migrar.migrar(self.base / "no-existe", self.destino)
        with self.assertRaises(SystemExit):
            migrar.migrar(self.origen, self.origen)

    def test_carpeta_sin_datos(self):
        vacia = self.base / "vacia"
        vacia.mkdir()
        self.assertEqual(migrar.main(["--desde", str(vacia), "--destino", str(self.destino)]), 1)


if __name__ == "__main__":
    unittest.main()
