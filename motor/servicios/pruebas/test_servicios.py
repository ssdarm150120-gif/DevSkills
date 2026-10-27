"""Pruebas del lanzador de servicios: lista blanca, validaciones y --simular (sin ejecutar nada real).

Correr desde motor/:  python -m unittest discover -s servicios/pruebas -t . -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MOTOR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MOTOR))
SCRIPT = MOTOR / "servicios" / "servicios.py"

from servicios import servicios as sv  # noqa: E402


def registro_de_prueba(base: Path, arranque: dict, puertos=(20999,), servicio="demo-api") -> dict:
    return {"proyectos": [{
        "id": "demo", "nombre": "Demo", "carpeta": str(base),
        "servicios": [{"id": servicio, "nombre": "API", "puertos": list(puertos),
                       "url": f"http://localhost:{puertos[0]}", "arranque": arranque}],
    }]}


class Validaciones(unittest.TestCase):
    def test_ruta_segura_acepta_relativas(self):
        base = Path(tempfile.gettempdir()) / "base"
        self.assertEqual(sv.ruta_segura(base, "."), base)
        self.assertEqual(sv.ruta_segura(base, ""), base)
        self.assertEqual(sv.ruta_segura(base, None), base)
        self.assertEqual(sv.ruta_segura(base, "backend\\Api"), base / "backend" / "Api")
        self.assertEqual(sv.ruta_segura(base, "codigo/despliegue"), base / "codigo" / "despliegue")

    def test_ruta_segura_rechaza_escapes_y_absolutas(self):
        base = Path(tempfile.gettempdir())
        for mala in ("..", "../x", "a/../b", "a\\..\\b", "/etc", "\\\\servidor\\x", "C:\\x", "c:/x", "x\x00y"):
            with self.subTest(mala=mala), self.assertRaises(sv.ErrorServicios):
                sv.ruta_segura(base, mala)

    def test_patrones_estrictos(self):
        for bueno in ("dev", "build:prod", "start_1.2-x"):
            self.assertEqual(sv.validar(bueno, sv.RE_SCRIPT_NPM, "s"), bueno)
        for malo in ("dev; rm -rf /", "dev && x", "a b", "", "dev\n", "$(x)", "`x`", None, 5):
            with self.subTest(malo=malo), self.assertRaises(sv.ErrorServicios):
                sv.validar(malo, sv.RE_SCRIPT_NPM, "script")
        for malo in ("os;x", "1mod", "a-b", "a b", "a/b"):
            with self.subTest(modulo=malo), self.assertRaises(sv.ErrorServicios):
                sv.validar(malo, sv.RE_MODULO, "módulo")
        for malo in ("--x $(y)", "a;b", "a b", "a|b", "'x'", ""):
            with self.subTest(argumento=malo), self.assertRaises(sv.ErrorServicios):
                sv.validar(malo, sv.RE_ARGUMENTO, "argumento")
        for bueno in ("--port=20000", "app.main:app", "--ui", "x_y.z"):
            self.assertEqual(sv.validar(bueno, sv.RE_ARGUMENTO, "argumento"), bueno)
        for malo in ("A B", "1A", "A-B", "A=B", ""):
            with self.subTest(entorno=malo), self.assertRaises(sv.ErrorServicios):
                sv.validar(malo, sv.RE_ENTORNO, "variable")

    def test_lista_blanca_de_tipos(self):
        self.assertEqual(set(sv.TIPOS_PERMITIDOS),
                         {"dotnet", "npm", "django-devskills", "python-modulo", "docker-compose"})
        p = registro_de_prueba(Path(tempfile.gettempdir()), {"tipo": "powershell", "carpeta": "."})["proyectos"][0]
        with self.assertRaises(sv.ErrorServicios):
            sv.plan_arranque(p, p["servicios"][0])


class Planes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)

    def plan(self, arranque, so="linux"):
        p = registro_de_prueba(self.base, arranque)["proyectos"][0]
        return sv.plan_arranque(p, p["servicios"][0], so)

    def test_dotnet_con_entorno(self):
        plan = self.plan({"tipo": "dotnet", "carpeta": "backend", "entorno": {"A__B": "false"}})
        self.assertEqual(plan["env"]["A__B"], "false")
        self.assertEqual(Path(plan["cwd"]), self.base / "backend")
        self.assertEqual(Path(plan["pasos"][0]["argv"][0]).stem.lower(), "dotnet")
        self.assertEqual(plan["pasos"][0]["argv"][1:], ["run"])

    def test_entorno_invalido(self):
        with self.assertRaises(sv.ErrorServicios):
            self.plan({"tipo": "dotnet", "carpeta": ".", "entorno": {"MALA VAR": "x"}})

    def test_npm_instala_si_falta_la_marca(self):
        arr = {"tipo": "npm", "carpeta": "web", "script": "dev", "instalar_si_falta": "node_modules"}
        plan = self.plan(arr)
        self.assertEqual([paso["argv"][1:] for paso in plan["pasos"]], [["ci"], ["run", "dev"]])
        (self.base / "web" / "node_modules").mkdir(parents=True)
        plan = self.plan(arr)
        self.assertEqual([paso["argv"][1:] for paso in plan["pasos"]], [["run", "dev"]])

    def test_npm_rechaza_script_peligroso(self):
        with self.assertRaises(sv.ErrorServicios):
            self.plan({"tipo": "npm", "carpeta": ".", "script": "dev; calc"})

    def test_python_modulo_con_venv_por_sistema(self):
        arr = {"tipo": "python-modulo", "carpeta": ".", "venv": ".venv", "modulo": "uvicorn",
               "argumentos": ["app:app", "--port=1"]}
        win = self.plan(arr, "windows")["pasos"][0]["argv"]
        pos = self.plan(arr, "linux")["pasos"][0]["argv"]
        self.assertTrue(win[0].replace("\\", "/").endswith(".venv/Scripts/python.exe"))
        self.assertTrue(pos[0].replace("\\", "/").endswith(".venv/bin/python"))
        self.assertEqual(win[1:], ["-m", "uvicorn", "app:app", "--port=1"])

    def test_python_modulo_rechaza_modulo_y_argumentos(self):
        with self.assertRaises(sv.ErrorServicios):
            self.plan({"tipo": "python-modulo", "carpeta": ".", "modulo": "os; x"})
        with self.assertRaises(sv.ErrorServicios):
            self.plan({"tipo": "python-modulo", "carpeta": ".", "modulo": "app", "argumentos": ["--x;y"]})

    def test_venv_con_escape_se_rechaza(self):
        with self.assertRaises(sv.ErrorServicios):
            self.plan({"tipo": "python-modulo", "carpeta": ".", "venv": "../otro", "modulo": "app"})

    def test_carpeta_con_escape_se_rechaza(self):
        for carpeta in ("../fuera", "/abs", "C:\\x"):
            with self.subTest(carpeta=carpeta), self.assertRaises(sv.ErrorServicios):
                self.plan({"tipo": "dotnet", "carpeta": carpeta})

    def test_django_usa_el_primer_puerto(self):
        plan = self.plan({"tipo": "django-devskills", "carpeta": "codigo"})
        self.assertEqual(plan["pasos"][0]["django"]["puerto"], 20999)

    def test_docker_compose_pide_su_archivo(self):
        arr = {"tipo": "docker-compose", "carpeta": "despliegue", "requiere_archivo": ".env", "construir": True}
        plan = self.plan(arr)
        self.assertIn("Falta .env", plan["aviso"])
        (self.base / "despliegue").mkdir()
        (self.base / "despliegue" / ".env").write_text("X=1", encoding="utf-8")
        plan = self.plan(arr)
        self.assertIsNone(plan["aviso"])
        self.assertEqual(plan["pasos"][0]["argv"][1:], ["compose", "up", "-d", "--build"])


class Procesos(unittest.TestCase):
    def test_pids_en_windows(self):
        salida = ("  Proto  Direccion local  Direccion remota  Estado  PID\n"
                  "  TCP    0.0.0.0:20999   0.0.0.0:0   LISTENING   4242\n"
                  "  TCP    [::]:20999      [::]:0      LISTENING   4242\n"
                  "  TCP    0.0.0.0:80      0.0.0.0:0   LISTENING   7\n"
                  "  TCP    127.0.0.1:20999 127.0.0.1:5 ESTABLISHED 9\n")
        self.assertEqual(sv.pids_en_puerto(20999, "windows", lambda argv: salida), [4242])

    def test_pids_con_lsof(self):
        if sv.shutil.which("lsof") is None:
            self.skipTest("sin lsof")
        self.assertEqual(sv.pids_en_puerto(20999, "linux", lambda argv: "11\n12\n"), [11, 12])

    def test_no_mata_pid_propio_ni_bajo(self):
        llamadas = []
        original = sv.os.kill
        sv.os.kill = lambda *a: llamadas.append(a)
        try:
            sv._matar(os.getpid(), "linux")
            sv._matar(1, "linux")
            sv._matar(0, "linux")
        finally:
            sv.os.kill = original
        self.assertEqual(llamadas, [])


class Simulacion(unittest.TestCase):
    """Ejecuta el lanzador de verdad como proceso, con --simular, en los tres sistemas."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        self.datos = self.base / "datos"
        self.registro = self.base / "proyectos.json"

    def correr(self, *args, registro=None):
        if registro is not None:
            self.registro.write_text(json.dumps(registro), encoding="utf-8")
        env = {**os.environ, "DEVSKILLS_DATOS": str(self.datos), "PYTHONIOENCODING": "utf-8"}
        return subprocess.run([sys.executable, str(SCRIPT), *args, "--registro", str(self.registro)],
                              capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)

    def test_levantar_simulado_en_los_tres_sistemas(self):
        reg = registro_de_prueba(self.base, {"tipo": "python-modulo", "carpeta": ".", "modulo": "app",
                                             "argumentos": ["--port=20999"]})
        for so, texto in (("windows", "ventana nueva"), ("macos", "proceso en segundo plano"),
                          ("linux", "proceso en segundo plano")):
            with self.subTest(so=so):
                r = self.correr("levantar", "demo-api", "--simular", "--so", so, registro=reg)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn(f"Simulación ({texto})", r.stdout)
                self.assertIn("-m app --port=20999", r.stdout)
        self.assertFalse(self.datos.exists(), "--simular no debe crear nada en el directorio de datos")

    def test_levantar_proyecto_completo_simulado(self):
        reg = registro_de_prueba(self.base, {"tipo": "dotnet", "carpeta": "."})
        r = self.correr("levantar", "demo", "--simular", registro=reg)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Simulación", r.stdout)

    def test_apagar_simulado_y_compatibilidad(self):
        reg = registro_de_prueba(self.base, {"tipo": "dotnet", "carpeta": "."})
        for args in (("apagar", "demo-api"), ("detener", "demo-api"), ("levantar", "demo-api", "apagar")):
            with self.subTest(args=args):
                r = self.correr(*args, "--simular", registro=reg)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("Simulación: apagaría demo-api (puertos 20999, tipo dotnet)", r.stdout)

    def test_listar(self):
        reg = registro_de_prueba(self.base, {"tipo": "dotnet", "carpeta": "."})
        r = self.correr("listar", registro=reg)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("demo-api", r.stdout)
        self.assertIn(":20999", r.stdout)

    def test_objetivo_inexistente(self):
        reg = registro_de_prueba(self.base, {"tipo": "dotnet", "carpeta": "."})
        r = self.correr("levantar", "no-existe", "--simular", registro=reg)
        self.assertEqual(r.returncode, 2)
        self.assertIn("No existe 'no-existe'", r.stderr)

    def test_rechaza_ruta_y_argumento_invalidos(self):
        malos = [{"tipo": "dotnet", "carpeta": "../fuera"},
                 {"tipo": "dotnet", "carpeta": "C:\\Windows"},
                 {"tipo": "npm", "carpeta": ".", "script": "dev && calc"},
                 {"tipo": "python-modulo", "carpeta": ".", "modulo": "app", "argumentos": ["--x;y"]},
                 {"tipo": "dotnet", "carpeta": ".", "entorno": {"A B": "x"}},
                 {"tipo": "cmd", "carpeta": "."}]
        for arranque in malos:
            with self.subTest(arranque=arranque):
                r = self.correr("levantar", "demo-api", "--simular", registro=registro_de_prueba(self.base, arranque))
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn("Error:", r.stderr)

    def test_so_solo_con_simular(self):
        reg = registro_de_prueba(self.base, {"tipo": "dotnet", "carpeta": "."})
        r = self.correr("levantar", "demo-api", "--so", "windows", registro=reg)
        self.assertEqual(r.returncode, 1)

    def test_registro_inexistente(self):
        r = self.correr("listar")
        self.assertEqual(r.returncode, 1)
        self.assertIn("No encontré el registro", r.stderr)


if __name__ == "__main__":
    unittest.main()
