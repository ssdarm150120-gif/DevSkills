"""Pruebas de «Aplicar cambios» del panel (receta por proyecto, solo lo necesario, ejecución en segundo plano, chat).

Todo corre con un proyecto temporal (front con package.json y back con venv falso) y fakes para npm, pip y el
lanzador de servicios: nada se instala, nada se compila y no se toca el registro real.
Correr desde motor/:  python -m unittest discover -s panel/pruebas -v
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
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

ESPERAR_SALUD_REAL = panel._esperar_salud   # el Entorno la sustituye por un fake; ésta es la de verdad


def escribir(ruta, texto="x\n"):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8", newline="\n")


def puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def crear_proyecto(base, puerto):
    """Front (frontend/) con package.json y script build, back (backend/) con requirements y un venv falso en .venv."""
    base = Path(base)
    escribir(base / "frontend" / "package.json", json.dumps({"name": "f", "scripts": {"build": "node build.js", "dev": "x"}}))
    escribir(base / "frontend" / "package-lock.json", '{"lockfileVersion": 3}')
    escribir(base / "frontend" / "src" / "app.js", "console.log(1)\n")
    escribir(base / "frontend" / "node_modules" / "paquete" / "index.js", "basura\n")
    escribir(base / "backend" / "api.py", "app = 1\n")
    escribir(base / "backend" / "requirements.txt", "fastapi\n")
    escribir(base / "README.md", "hola\n")
    for rel in ("Scripts/python.exe", "bin/python"):
        escribir(base / ".venv" / rel, "")
    return {"version": 1, "proyectos": [{
        "id": "demo", "nombre": "Demo Tablero", "descripcion": "x", "carpeta": str(base),
        "servicios": [{"id": "demo-web", "nombre": "Demo web", "puertos": [puerto], "url": f"http://127.0.0.1:{puerto}",
                       "salud": "/healthz", "abrir": "/",
                       "arranque": {"tipo": "python-modulo", "carpeta": "backend", "venv": ".venv", "modulo": "uvicorn",
                                    "argumentos": ["api:app", "--port", str(puerto)]}}]}]}


PASOS = [
    {"id": "npm-install-frontend", "tipo": "npm-install", "carpeta": "frontend"},
    {"id": "npm-build-frontend", "tipo": "npm-script", "carpeta": "frontend", "script": "build"},
    {"id": "pip-backend", "tipo": "pip-requisitos", "venv": ".venv", "requisitos": "backend/requirements.txt"},
    {"id": "reiniciar-demo-web", "tipo": "reiniciar-servicio", "servicio": "demo-web"},
]


class Entorno(unittest.TestCase):
    """Proyecto temporal + registro temporal + fakes. `self.llamadas` guarda lo que «se ejecutó»."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.dir = self.base / "proyecto demo"
        self.puerto = puerto_libre()
        self.datos = crear_proyecto(self.dir, self.puerto)
        self.registro_ruta = self.base / "proyectos.json"
        self.escribir_registro(self.datos)
        for p in (mock.patch.object(panel, "REGISTRO", self.registro_ruta),
                  mock.patch.object(panel, "ARCHIVO_LOG", self.base / "panel.log"),
                  mock.patch.dict(panel.ESTADO, {"estado_dir": str(self.base / "estado"), "simular": False}),
                  mock.patch.object(panel, "_buscar_npm", lambda: "npm"),
                  mock.patch.object(panel, "_dormir", lambda s: None),
                  mock.patch.object(panel, "_correr_proceso", self.falso_proceso),
                  mock.patch.object(panel, "_lanzador_cli", self.falso_lanzador),
                  mock.patch.object(panel, "_esperar_puertos_libres", lambda puertos: True),
                  mock.patch.object(panel, "_esperar_salud", self.falsa_salud)):
            p.start()
            self.addCleanup(p.stop)
        panel._registro_cache.update(mtime=None, datos=None, error=None)
        for d in (panel._plan_cache, panel._propuesta_cache, panel._aplicaciones):
            d.clear()
        self.llamadas = []
        self.fallar = set()          # claves de llamadas que devuelven fallo: "npm run build", "levantar", …
        self.bloqueo = None          # threading.Event: si existe, los pasos esperan a que se libere
        self.salud_ok = True
        self.addCleanup(self.esperar_hilos)

    # ---- fakes
    def falso_proceso(self, argv, cwd, timeout):
        clave = " ".join(Path(argv[0]).name if i == 0 else a for i, a in enumerate(argv))
        clave = clave.split(" -r ")[0].replace("python.exe", "python")
        self.llamadas.append(("proceso", clave, cwd, timeout))
        if self.bloqueo is not None:
            self.bloqueo.wait(10)
        if any(f in clave for f in self.fallar):
            return 1, "ERR! algo salió mal"
        return 0, "listo \x1b[32mok\x1b[0m"

    def falso_lanzador(self, accion, objetivo):
        self.llamadas.append(("lanzador", accion, objetivo))
        if accion in self.fallar:
            return 1, "no se pudo"
        return 0, f"{accion} {objetivo}"

    def falsa_salud(self, s):
        self.llamadas.append(("salud", s["id"]))
        return (self.salud_ok, "responde HTTP 200" if self.salud_ok else "no respondió")

    def esperar_hilos(self):
        for h in threading.enumerate():
            if h.name.startswith("aplicar-"):
                if self.bloqueo is not None:
                    self.bloqueo.set()
                h.join(15)

    # ---- utilidades
    def escribir_registro(self, datos):
        self.registro_ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        panel._registro_cache.update(mtime=None, datos=None, error=None)

    def aprobar(self, pasos=None):
        codigo, r = panel.guardar_receta("demo", pasos if pasos is not None else PASOS)
        self.assertEqual(codigo, 200, r)
        return r

    def aplicar(self, forzar=False):
        codigo, r = panel.iniciar_aplicacion("demo", forzar)
        if codigo != 202:
            return codigo, r
        return codigo, self.terminar()

    def terminar(self):
        for h in threading.enumerate():
            if h.name == "aplicar-demo":
                h.join(20)
        return panel.estado_aplicar("demo")["ejecucion"]

    def procesos(self):
        return [x[1] for x in self.llamadas if x[0] == "proceso"]

    def acciones_plan(self):
        return {x["id"]: x["accion"] for x in panel.planear("demo")}

    def aplicar_todo_y_limpiar(self):
        self.aprobar()
        self.aplicar()
        self.llamadas.clear()


class Deteccion(Entorno):
    def test_propone_receta_con_front_y_back(self):
        r = panel.proponer_receta("demo")
        self.assertEqual([(x["tipo"], x["id"]) for x in r["pasos"]],
                         [("npm-install", "npm-install-frontend"), ("npm-script", "npm-build-frontend"),
                          ("pip-requisitos", "pip-backend"), ("reiniciar-servicio", "reiniciar-demo-web")])
        build = r["pasos"][1]
        self.assertEqual((build["carpeta"], build["script"]), ("frontend", "build"))
        pip = r["pasos"][2]
        self.assertEqual((pip["venv"], pip["requisitos"]), (".venv", "backend/requirements.txt"))
        self.assertEqual(r["pasos"][3]["servicio"], "demo-web")
        self.assertTrue(all(x["titulo"] and x["area"] for x in r["pasos"]))
        self.assertEqual({x["area"] for x in r["pasos"]}, {"frontend", "backend"})

    def test_ignora_node_modules_y_carpetas_sin_build(self):
        escribir(self.dir / "frontend" / "node_modules" / "otro" / "package.json",
                 json.dumps({"scripts": {"build": "x"}}))
        escribir(self.dir / "herramientas" / "package.json", json.dumps({"scripts": {"test": "x"}}))
        r = panel.proponer_receta("demo")
        self.assertEqual([x["carpeta"] for x in r["pasos"] if x["tipo"] == "npm-script"], ["frontend"])

    def test_sin_front_ni_requisitos_lo_dice(self):
        (self.dir / "frontend" / "package.json").unlink()
        (self.dir / "backend" / "requirements.txt").unlink()
        r = panel.proponer_receta("demo")
        self.assertEqual([x["tipo"] for x in r["pasos"]], ["reiniciar-servicio"])
        self.assertEqual(len(r["notas"]), 2)

    def test_requisitos_en_la_raiz_del_proyecto(self):
        (self.dir / "backend" / "requirements.txt").unlink()
        escribir(self.dir / "requirements.txt", "x\n")
        r = panel.proponer_receta("demo")
        self.assertIn("requirements.txt", [x.get("requisitos") for x in r["pasos"]])

    def test_no_propone_reiniciar_docker_ni_servidores_de_desarrollo(self):
        d = json.loads(self.registro_ruta.read_text(encoding="utf-8"))
        d["proyectos"][0]["servicios"] += [
            {"id": "demo-dev", "nombre": "Vite", "puertos": [puerto_libre()], "url": "http://127.0.0.1:5999",
             "arranque": {"tipo": "npm", "carpeta": "frontend", "script": "dev"}},
            {"id": "demo-db", "nombre": "Base", "puertos": [puerto_libre()], "url": "http://127.0.0.1:5998",
             "arranque": {"tipo": "docker-compose", "carpeta": "."}}]
        d["proyectos"][0]["servicios"][1]["url"] = f"http://127.0.0.1:{d['proyectos'][0]['servicios'][1]['puertos'][0]}"
        d["proyectos"][0]["servicios"][2]["url"] = f"http://127.0.0.1:{d['proyectos'][0]['servicios'][2]['puertos'][0]}"
        self.escribir_registro(d)
        r = panel.proponer_receta("demo")
        self.assertEqual([x["servicio"] for x in r["pasos"] if x["tipo"] == "reiniciar-servicio"], ["demo-web"])

    def test_proyecto_inexistente(self):
        with self.assertRaises(KeyError):
            panel.proponer_receta("no")


class Validacion(Entorno):
    def v(self, paso, base=True):
        return panel.validar_paso(paso, ["demo-web"], self.dir if base else None)

    def test_acepta_los_cuatro_tipos(self):
        for p in PASOS:
            self.assertEqual(self.v(p)["tipo"], p["tipo"])
        self.assertEqual(self.v({**PASOS[1], "timeout": 60})["timeout"], 60)

    def test_rechaza_rutas_peligrosas(self):
        malas = ["..", "../x", "frontend/../../x", "..\\x", "/etc", "C:\\Windows", "C:/x", "\\\\srv\\share", "a;b", "a|b",
                 "a$b", "frontend\n", "", None, 5, "x" * 300]
        for ruta in malas:
            for tipo in ("npm-install", "npm-script"):
                paso = {"id": "p", "tipo": tipo, "carpeta": ruta, **({"script": "build"} if tipo == "npm-script" else {})}
                with self.assertRaises(panel.ErrorRegistro, msg=repr(ruta)):
                    self.v(paso, base=False)
        for ruta in ("..", "/etc", "C:\\x", "../backend/requirements.txt", "backend/../../x.txt"):
            with self.assertRaises(panel.ErrorRegistro, msg=ruta):
                self.v({"id": "p", "tipo": "pip-requisitos", "venv": ".venv", "requisitos": ruta}, base=False)
            with self.assertRaises(panel.ErrorRegistro, msg=ruta):
                self.v({"id": "p", "tipo": "pip-requisitos", "venv": ruta, "requisitos": "backend/requirements.txt"}, base=False)

    def test_rechaza_scripts_malos_o_inexistentes(self):
        for script in ("build; rm -rf /", "build && x", "a b", "$(x)", "", None, "x" * 80):
            with self.assertRaises(panel.ErrorRegistro, msg=repr(script)):
                self.v({"id": "p", "tipo": "npm-script", "carpeta": "frontend", "script": script}, base=False)
        with self.assertRaisesRegex(panel.ErrorRegistro, "no existe en el package.json"):
            self.v({"id": "p", "tipo": "npm-script", "carpeta": "frontend", "script": "deploy"})

    def test_rechaza_tipo_desconocido_y_claves_ajenas(self):
        for paso in ({"id": "p", "tipo": "shell", "comando": "ls"}, {"id": "p", "tipo": "npm-install"},
                     {"id": "p", "tipo": "npm-install", "carpeta": "frontend", "args": ["--force"]},
                     {"id": "p", "tipo": "reiniciar-servicio", "servicio": "demo-web", "comando": "x"},
                     {"id": "P", "tipo": "npm-install", "carpeta": "frontend"}, {"tipo": "npm-install", "carpeta": "frontend"},
                     "npm install", None, {"id": "p", "tipo": None}):
            with self.assertRaises(panel.ErrorRegistro, msg=repr(paso)):
                self.v(paso)

    def test_rechaza_lo_que_no_existe_en_disco(self):
        with self.assertRaisesRegex(panel.ErrorRegistro, "no existe dentro del proyecto"):
            self.v({"id": "p", "tipo": "npm-install", "carpeta": "no-existe"})
        with self.assertRaisesRegex(panel.ErrorRegistro, "No hay package.json"):
            self.v({"id": "p", "tipo": "npm-install", "carpeta": "backend"})
        with self.assertRaisesRegex(panel.ErrorRegistro, "no existe dentro del proyecto"):
            self.v({"id": "p", "tipo": "pip-requisitos", "venv": ".venv", "requisitos": "backend/otro.txt"})
        with self.assertRaisesRegex(panel.ErrorRegistro, ".txt"):
            self.v({"id": "p", "tipo": "pip-requisitos", "venv": ".venv", "requisitos": "backend/api.py"})

    def test_servicio_de_otro_proyecto(self):
        with self.assertRaisesRegex(panel.ErrorRegistro, "no es de este proyecto"):
            self.v({"id": "p", "tipo": "reiniciar-servicio", "servicio": "ajeno"})

    def test_timeout_fuera_de_rango(self):
        for t in (0, 5, 4000, "60", True, 1.5):
            with self.assertRaises(panel.ErrorRegistro, msg=repr(t)):
                self.v({**PASOS[0], "timeout": t})

    def test_receta_completa(self):
        ok = panel.validar_aplicar({"version": 1, "aprobada": "hoy", "pasos": PASOS}, ["demo-web"], self.dir)
        self.assertEqual(len(ok["pasos"]), 4)
        self.assertIsNone(panel.validar_aplicar(None, []))
        for malo in ({"pasos": []}, {"pasos": PASOS + [PASOS[0]]}, {"pasos": PASOS, "extra": 1}, {"version": 2, "pasos": PASOS},
                     {"pasos": [{**PASOS[0], "id": f"p{i}"} for i in range(panel.MAX_PASOS + 1)]}, [], "x"):
            with self.assertRaises(panel.ErrorRegistro, msg=repr(malo)[:60]):
                panel.validar_aplicar(malo, ["demo-web"], self.dir)

    def test_una_receta_danada_en_el_registro_no_tumba_el_panel(self):
        d = json.loads(self.registro_ruta.read_text(encoding="utf-8"))
        d["proyectos"][0]["aplicar"] = {"version": 1, "pasos": [{"id": "x", "tipo": "shell", "comando": "rm -rf /"}]}
        self.escribir_registro(d)
        p = panel.registro()["por_id"]["demo"]
        self.assertIsNone(p["aplicar"])
        self.assertIn("Tipo de paso no permitido", p["aplicar_error"])
        codigo, r = panel.iniciar_aplicacion("demo")
        self.assertEqual(codigo, 409)
        self.assertEqual(self.llamadas, [])


class GuardarReceta(Entorno):
    def test_guarda_en_proyectos_json_y_conserva_el_resto(self):
        antes = json.loads(self.registro_ruta.read_text(encoding="utf-8"))
        antes["proyectos"][0]["nota"] = "se conserva"
        self.escribir_registro(antes)
        r = self.aprobar()
        self.assertEqual(len(r["receta"]["pasos"]), 4)
        texto = self.registro_ruta.read_text(encoding="utf-8")
        self.assertTrue(texto.endswith("\n") and '\n  "proyectos"' in texto)  # sangría de 2 y salto final
        crudo = json.loads(texto)
        p = crudo["proyectos"][0]
        self.assertEqual(p["nota"], "se conserva")
        self.assertEqual(p["aplicar"]["version"], 1)
        self.assertEqual([x["id"] for x in p["aplicar"]["pasos"]], [x["id"] for x in PASOS])
        self.assertTrue(p["aplicar"]["aprobada"])
        self.assertEqual(panel.registro()["por_id"]["demo"]["aplicar"]["pasos"][1]["script"], "build")

    def test_rechaza_pasos_invalidos_sin_tocar_el_archivo(self):
        antes = self.registro_ruta.read_text(encoding="utf-8")
        for pasos in ([{"id": "x", "tipo": "shell", "comando": "ls"}], [{**PASOS[0], "carpeta": ".."}],
                      [{**PASOS[1], "script": "inexistente"}], "no es lista", [PASOS[0]] * 2):
            with self.assertRaises(ValueError, msg=repr(pasos)[:50]):
                panel.guardar_receta("demo", pasos)
        self.assertEqual(self.registro_ruta.read_text(encoding="utf-8"), antes)

    def test_lista_vacia_quita_la_receta_y_las_huellas(self):
        self.aplicar_todo_y_limpiar()
        self.assertTrue(panel._huellas_guardadas("demo"))
        codigo, r = panel.guardar_receta("demo", [])
        self.assertEqual(codigo, 200)
        self.assertNotIn("aplicar", json.loads(self.registro_ruta.read_text(encoding="utf-8"))["proyectos"][0])
        self.assertEqual(panel._huellas_guardadas("demo"), {})

    def test_editar_la_receta_vuelve_a_ejecutar_el_paso_cambiado(self):
        self.aplicar_todo_y_limpiar()
        self.assertEqual(set(self.acciones_plan().values()), {"omitir"})
        escribir(self.dir / "frontend" / "package.json",
                 json.dumps({"name": "f", "scripts": {"build": "node build.js", "dev": "x", "compilar": "y"}}))
        nuevos = [PASOS[0], {**PASOS[1], "script": "compilar"}, PASOS[2], PASOS[3]]
        self.aprobar(nuevos)
        acc = self.acciones_plan()
        self.assertEqual(acc["npm-build-frontend"], "ejecutar")
        self.assertEqual(acc["pip-backend"], "omitir")

    def test_no_se_edita_mientras_corre(self):
        self.aprobar()
        self.bloqueo = threading.Event()
        self.assertEqual(panel.iniciar_aplicacion("demo")[0], 202)
        codigo, r = panel.guardar_receta("demo", [])
        self.assertEqual(codigo, 409)
        self.bloqueo.set()
        self.terminar()

    def test_proyecto_inexistente(self):
        with self.assertRaises(KeyError):
            panel.guardar_receta("no", PASOS)


class SoloLoNecesario(Entorno):
    """Cada caso de las huellas: qué se ejecuta y qué se omite."""

    def setUp(self):
        super().setUp()
        self.aplicar_todo_y_limpiar()

    def assertPlan(self, esperado):
        self.assertEqual(self.acciones_plan(), {"npm-install-frontend": esperado[0], "npm-build-frontend": esperado[1],
                                                "pip-backend": esperado[2], "reiniciar-demo-web": esperado[3]})

    def test_primera_vez_todo_corre(self):
        self.escribir_registro(json.loads(self.registro_ruta.read_text(encoding="utf-8")))
        panel._guardar_estado_aplicar("demo", todo=True)
        self.assertPlan(["ejecutar"] * 4)
        self.assertEqual(panel.pendientes_de(panel.planear("demo"))["areas"], ["frontend", "backend"])

    def test_sin_cambios_todo_se_omite(self):
        self.assertPlan(["omitir"] * 4)
        self.assertEqual(panel.pendientes_de(panel.planear("demo")), {"hay": False, "areas": [], "texto": None})

    def test_cambia_el_codigo_del_front(self):
        escribir(self.dir / "frontend" / "src" / "app.js", "console.log('nuevo, más largo')\n")
        self.assertPlan(["omitir", "ejecutar", "omitir", "ejecutar"])  # el back se reinicia porque hubo build
        self.assertEqual(panel.pendientes_de(panel.planear("demo")),
                         {"hay": True, "areas": ["frontend"], "texto": "Hay cambios sin aplicar: frontend"})

    def test_un_archivo_nuevo_en_el_front(self):
        escribir(self.dir / "frontend" / "src" / "otro.js", "x\n")
        self.assertPlan(["omitir", "ejecutar", "omitir", "ejecutar"])

    def test_un_archivo_borrado_en_el_front(self):
        (self.dir / "frontend" / "src" / "app.js").unlink()
        self.assertPlan(["omitir", "ejecutar", "omitir", "ejecutar"])

    def test_cambia_el_lock_del_front(self):
        escribir(self.dir / "frontend" / "package-lock.json", '{"lockfileVersion": 3, "x": 1}')
        self.assertPlan(["ejecutar", "ejecutar", "omitir", "ejecutar"])

    def test_cambia_package_json(self):
        escribir(self.dir / "frontend" / "package.json",
                 json.dumps({"name": "f2", "scripts": {"build": "node build.js", "dev": "x"}}))
        self.assertPlan(["ejecutar", "ejecutar", "omitir", "ejecutar"])

    def test_falta_node_modules(self):
        import shutil
        shutil.rmtree(self.dir / "frontend" / "node_modules")
        self.assertEqual(self.acciones_plan()["npm-install-frontend"], "ejecutar")

    def test_cambian_los_requisitos(self):
        escribir(self.dir / "backend" / "requirements.txt", "fastapi\nuvicorn\n")
        acc = self.acciones_plan()
        self.assertEqual((acc["pip-backend"], acc["reiniciar-demo-web"], acc["npm-build-frontend"]), ("ejecutar", "ejecutar", "omitir"))

    def test_cambia_solo_el_back(self):
        escribir(self.dir / "backend" / "api.py", "app = 2  # cambió\n")
        self.assertPlan(["omitir", "omitir", "omitir", "ejecutar"])
        self.assertEqual(panel.pendientes_de(panel.planear("demo"))["areas"], ["backend"])

    def test_cambios_fuera_de_front_y_back_no_cuentan(self):
        escribir(self.dir / "README.md", "otro texto más largo\n")
        escribir(self.dir / "docs" / "nota.md", "x\n")
        self.assertPlan(["omitir"] * 4)

    def test_node_modules_y_pycache_no_cuentan(self):
        escribir(self.dir / "frontend" / "node_modules" / "paquete" / "nuevo.js", "otra cosa\n")
        escribir(self.dir / "backend" / "__pycache__" / "api.cpython-312.pyc", "bin\n")
        escribir(self.dir / "frontend" / "dist" / "bundle.js", "salida\n")
        self.assertPlan(["omitir"] * 4)

    def test_forzar_todo(self):
        plan = panel.planear("demo", forzar=True)
        self.assertEqual({x["accion"] for x in plan}, {"ejecutar"})
        self.assertEqual({x["razon"] for x in plan}, {"Forzado"})
        self.aplicar(forzar=True)
        self.assertEqual(len(self.procesos()), 3)
        self.assertIn(("lanzador", "levantar", "demo-web"), self.llamadas)

    def test_cambiar_la_definicion_de_un_paso_lo_invalida(self):
        self.aprobar([PASOS[0], PASOS[1], PASOS[2], {**PASOS[3], "timeout": 99}])
        self.assertEqual(self.acciones_plan()["reiniciar-demo-web"], "omitir")  # el timeout no cambia la huella
        d = json.loads(self.registro_ruta.read_text(encoding="utf-8"))
        d["proyectos"][0]["aplicar"]["pasos"][0]["carpeta"] = "backend"  # ya no es válido en disco: no debe correr nada raro
        self.escribir_registro(d)
        self.assertEqual(panel.registro()["por_id"]["demo"]["aplicar"]["pasos"][0]["carpeta"], "backend")

    def test_un_git_real_respeta_gitignore(self):
        import shutil
        git = shutil.which("git")
        if not git:
            self.skipTest("git no está disponible")
        subprocess.run([git, "init", "-q"], cwd=self.dir, check=True, capture_output=True)
        escribir(self.dir / ".gitignore", "frontend/salida/\n")
        panel._guardar_estado_aplicar("demo", todo=True)
        self.aplicar()
        self.assertEqual(set(self.acciones_plan().values()), {"omitir"})
        escribir(self.dir / "frontend" / "salida" / "bundle.js", "ignorado por git\n")
        self.assertEqual(set(self.acciones_plan().values()), {"omitir"})
        escribir(self.dir / "frontend" / "src" / "nuevo.js", "visible\n")
        self.assertEqual(self.acciones_plan()["npm-build-frontend"], "ejecutar")


class Ejecucion(Entorno):
    def test_aplica_todo_en_orden_y_guarda_las_huellas(self):
        self.aprobar()
        codigo, ej = self.aplicar()
        self.assertEqual(codigo, 202)
        self.assertEqual(ej["estado"], "ok")
        self.assertEqual([p["estado"] for p in ej["pasos"]], ["ok"] * 4)
        claves = self.procesos()
        self.assertTrue(claves[0].startswith("npm ci"))   # hay package-lock.json
        self.assertEqual(claves[1], "npm run build")
        self.assertTrue(claves[2].endswith("-m pip install"))
        self.assertEqual([x[1:] for x in self.llamadas if x[0] == "lanzador"], [("apagar", "demo-web"), ("levantar", "demo-web")])
        self.assertEqual(self.llamadas[-1], ("salud", "demo-web"))
        self.assertEqual(ej["abrir"]["url"], f"http://127.0.0.1:{self.puerto}/")
        self.assertIn("Listo: 4", ej["resumen"])
        self.assertEqual(set(self.acciones_plan().values()), {"omitir"})
        self.assertFalse(panel.estado_aplicar("demo")["pendientes"]["hay"])
        guardado = json.loads((self.base / "estado" / "aplicar.json").read_text(encoding="utf-8"))
        self.assertEqual(len(guardado["demo"]["pasos"]), 4)
        self.assertEqual(guardado["demo"]["ultima"]["estado"], "ok")

    def test_npm_install_si_no_hay_lock(self):
        (self.dir / "frontend" / "package-lock.json").unlink()
        self.aprobar()
        self.aplicar()
        self.assertTrue(self.procesos()[0].startswith("npm install"))

    def test_los_pasos_corren_en_su_carpeta_con_timeout(self):
        self.aprobar([PASOS[0], {**PASOS[1], "timeout": 77}])
        self.aplicar()
        carpetas = [os.path.basename(x[2]) for x in self.llamadas if x[0] == "proceso"]
        self.assertEqual(carpetas, ["frontend", "frontend"])
        self.assertEqual([x[3] for x in self.llamadas if x[0] == "proceso"], [panel.TIMEOUT_PASO["npm-install"], 77])

    def test_se_detiene_en_el_primer_fallo(self):
        self.aprobar()
        self.fallar = {"npm run build"}
        codigo, ej = self.aplicar()
        self.assertEqual(ej["estado"], "fallo")
        self.assertEqual([p["estado"] for p in ej["pasos"]], ["ok", "fallo", "omitido", "omitido"])
        self.assertIn("falló «npm-build-frontend»", ej["pasos"][2]["razon"])
        self.assertIn("ERR! algo salió mal", ej["pasos"][1]["salida"])
        self.assertFalse([x for x in self.llamadas if x[0] == "lanzador"])      # nunca se llegó al reinicio
        self.assertFalse([c for c in self.procesos() if "pip" in c])
        self.assertIsNone(ej["abrir"])
        self.assertIn("Falló", ej["resumen"])
        # Reintento: lo que ya salió bien no se repite; el build y lo que sigue sí.
        self.fallar = set()
        self.llamadas.clear()
        _, ej = self.aplicar()
        self.assertEqual(ej["estado"], "ok")
        self.assertEqual([p["estado"] for p in ej["pasos"]], ["omitido", "ok", "ok", "ok"])

    def test_si_el_reinicio_falla_se_reintenta_aunque_el_codigo_no_cambie(self):
        self.aprobar()
        self.aplicar()
        escribir(self.dir / "frontend" / "src" / "app.js", "console.log('v2 más largo')\n")
        self.fallar = {"levantar"}
        _, ej = self.aplicar()
        self.assertEqual([p["estado"] for p in ej["pasos"]], ["omitido", "ok", "omitido", "fallo"])
        self.fallar = set()
        self.llamadas.clear()
        _, ej = self.aplicar()
        self.assertEqual([p["estado"] for p in ej["pasos"]], ["omitido", "omitido", "omitido", "ok"])
        self.assertIn(("lanzador", "levantar", "demo-web"), self.llamadas)

    def test_la_salud_que_no_responde_es_un_fallo(self):
        self.aprobar()
        self.salud_ok = False
        _, ej = self.aplicar()
        self.assertEqual(ej["estado"], "fallo")
        self.assertEqual(ej["pasos"][3]["estado"], "fallo")
        self.assertIn("no respondió", ej["pasos"][3]["salida"])

    def test_la_salida_se_limpia_y_se_recorta(self):
        self.aprobar([PASOS[0]])
        largo = "linea\n" * 2000
        with mock.patch.object(panel, "_correr_proceso", lambda *a: (0, panel.limpiar_salida_paso(largo))):
            _, ej = self.aplicar()
        self.assertLessEqual(len(ej["pasos"][0]["salida"]), panel.MAX_SALIDA_PASO + 1)
        self.assertTrue(ej["pasos"][0]["salida"].startswith("…"))

    def test_un_error_inesperado_no_deja_la_ejecucion_colgada(self):
        self.aprobar([PASOS[0]])
        with mock.patch.object(panel, "_correr_proceso", side_effect=RuntimeError("boom")):
            _, ej = self.aplicar()
        self.assertEqual(ej["estado"], "fallo")
        self.assertEqual(ej["pasos"][0]["estado"], "fallo")
        self.assertFalse(panel.candado("aplicar-demo").locked() or panel.candado("demo").locked())

    def test_sin_receta_no_ejecuta(self):
        codigo, r = panel.iniciar_aplicacion("demo")
        self.assertEqual((codigo, r.get("sin_receta")), (409, True))
        self.assertEqual(self.llamadas, [])
        with self.assertRaises(KeyError):
            panel.iniciar_aplicacion("no")

    def test_falta_npm_se_explica(self):
        self.aprobar([PASOS[0]])
        with mock.patch.object(panel, "_buscar_npm", lambda: None):
            _, ej = self.aplicar()
        self.assertEqual(ej["estado"], "fallo")
        self.assertIn("npm no está en el PATH", ej["pasos"][0]["salida"])

    def test_falta_el_venv(self):
        import shutil
        self.aprobar()
        shutil.rmtree(self.dir / ".venv")
        _, ej = self.aplicar()
        self.assertEqual(ej["pasos"][2]["estado"], "fallo")
        self.assertIn("No existe el Python del venv", ej["pasos"][2]["salida"])


class Candado(Entorno):
    def test_no_dos_aplicaciones_a_la_vez(self):
        self.aprobar()
        self.bloqueo = threading.Event()
        codigo, _ = panel.iniciar_aplicacion("demo")
        self.assertEqual(codigo, 202)
        codigo, r = panel.iniciar_aplicacion("demo")
        self.assertEqual(codigo, 409)
        self.assertIn("Ya hay una acción en curso", r["error"])
        # Y tampoco junto con Levantar/Apagar del mismo proyecto.
        codigo, r = panel.ejecutar_accion("demo", "levantar")
        self.assertEqual(codigo, 409)
        self.assertTrue(panel.estado_aplicar("demo")["en_curso"])
        self.bloqueo.set()
        ej = self.terminar()
        self.assertEqual(ej["estado"], "ok")
        self.assertEqual(panel.iniciar_aplicacion("demo")[0], 202)  # ya se liberó
        self.terminar()

    def test_si_hay_una_accion_en_curso_no_arranca(self):
        self.aprobar()
        with panel.candado("demo"):
            codigo, _ = panel.iniciar_aplicacion("demo")
        self.assertEqual(codigo, 409)
        self.assertEqual(self.llamadas, [])
        self.assertFalse(panel.candado("aplicar-demo").locked())

    def test_proyectos_distintos_no_se_bloquean(self):
        self.assertFalse(panel.candado("aplicar-otro").locked())
        with panel.candado("aplicar-demo"):
            self.assertTrue(panel.candado("aplicar-otro").acquire(blocking=False))
            panel.candado("aplicar-otro").release()


class Simulacion(Entorno):
    def test_muestra_los_comandos_y_no_ejecuta_nada(self):
        self.aprobar()
        panel.ESTADO["simular"] = True
        codigo, ej = self.aplicar()
        self.assertEqual(codigo, 202)
        self.assertEqual(ej["estado"], "simulado")
        self.assertTrue(ej["simulacion"])
        self.assertEqual([p["estado"] for p in ej["pasos"]], ["simulado"] * 4)
        self.assertEqual(self.llamadas, [])
        self.assertIn("npm run build", ej["pasos"][1]["comando"])
        self.assertIn("servicios.py apagar demo-web", ej["pasos"][3]["comando"])
        self.assertEqual(panel._huellas_guardadas("demo"), {})   # una simulación no marca nada como aplicado
        self.assertIn("Simulación", ej["resumen"])


class Estado(Entorno):
    def test_sin_receta_ofrece_la_propuesta(self):
        e = panel.estado_aplicar("demo")
        self.assertIsNone(e["receta"])
        self.assertEqual(len(e["propuesta"]["pasos"]), 4)
        self.assertIn("terminal de Claude Code", e["limitaciones"])

    def test_con_receta_calcula_el_aviso(self):
        self.aprobar()
        e = panel.estado_aplicar("demo")
        self.assertEqual(e["pendientes"]["texto"], "Hay cambios sin aplicar: frontend, backend")
        self.assertEqual(e["abrir"]["nombre"], "Demo web")
        self.assertIsNone(e["propuesta"])
        self.assertEqual(len(panel.estado_aplicar("demo", con_propuesta=True)["propuesta"]["pasos"]), 4)

    def test_el_aviso_usa_una_cache_corta(self):
        self.aprobar()
        panel.estado_aplicar("demo")
        escribir(self.dir / "backend" / "api.py", "app = 3  # cambio\n")
        self.assertEqual(panel.estado_aplicar("demo")["pendientes"]["areas"], ["frontend", "backend"])
        panel._plan_cache.clear()
        self.assertTrue(panel.estado_aplicar("demo")["pendientes"]["hay"])

    def test_la_ultima_aplicacion_sobrevive_al_reinicio_del_panel(self):
        self.aprobar()
        self.aplicar()
        panel._aplicaciones.clear()
        e = panel.estado_aplicar("demo")
        self.assertIsNone(e["ejecucion"])
        self.assertEqual(e["ultima"]["estado"], "ok")
        self.assertFalse(e["pendientes"]["hay"])


class Chat(Entorno):
    def i(self, texto, **kw):
        return panel.intencion_aplicar(texto, **kw)

    def coincide(self, texto, **kw):
        r = self.i(texto, alias=kw.pop("alias", {}), **kw)
        self.assertTrue(r["coincide"], texto)
        self.assertEqual(r["proyecto"], "demo", texto)
        return r

    def test_frases_que_coinciden(self):
        for t in ("aplica los cambios del demo", "Aplica los cambios de Demo Tablero", "aplica cambios en demo",
                  "aplicar los cambios al proyecto demo tablero", "aplícame los cambios del demo, por favor",
                  "por favor aplica los cambios en el proyecto Demo", "actualiza el demo", "Actualiza el Demo Tablero",
                  "actualiza demo", "recompila demo", "recompila el demo tablero ya", "reconstruye el demo", "ACTUALIZA EL DEMO!",
                  "actualiza el proyecto demo tablero por favor", "oye actualiza el demo"):
            self.coincide(t)

    def test_por_alias(self):
        self.coincide("actualiza el tablero de ventas", alias={"demo": ["tablero de ventas"]})
        self.assertFalse(self.i("actualiza el tablero de ventas", alias={})["coincide"])

    def test_alias_del_orquestador_en_su_config(self):
        escribir(self.base / "config.json", json.dumps({"alias_proyectos": {"demo": ["mi tablero"]}}))
        with mock.patch.object(panel.rutas, "orquestador_config", lambda: self.base / "config.json"):
            self.assertEqual(panel.intencion_aplicar("recompila mi tablero")["proyecto"], "demo")

    def test_frases_que_no_coinciden_siguen_al_orquestador(self):
        for t in ("actualiza el readme del demo", "¿cómo actualizo el demo?", "explícame qué hace el demo", "aplica los cambios",
                  "actualiza", "aplica los cambios del otro proyecto", "actualiza el proyecto", "recompila", "",
                  "   ", "revisa los cambios del demo", "no actualices el demo ni lo toques", "actualiza la documentación del demo",
                  "x" * 400):
            r = self.i(t, alias={})
            self.assertFalse(r["coincide"], t[:40])

    def test_proyecto_ambiguo_no_coincide(self):
        reg = {"por_id": {"demo": {"nombre": "Demo"}, "demo-dos": {"nombre": "Demo"}}}
        r = self.i("actualiza el demo", reg=reg, alias={})
        self.assertEqual((r["coincide"], r["ambiguo"]), (False, True))
        self.assertEqual({c["proyecto"] for c in r["candidatos"]}, {"demo", "demo-dos"})
        reg = {"por_id": {"uno": {"nombre": "Uno"}, "dos": {"nombre": "Dos"}}}
        r = self.i("actualiza el tablero", reg=reg, alias={"uno": ["tablero"], "dos": ["tablero"]})
        self.assertEqual((r["coincide"], r["ambiguo"]), (False, True))

    def test_un_nombre_que_contiene_a_otro_no_es_ambiguo(self):
        reg = {"por_id": {"demo": {"nombre": "Demo"}, "demo-extra": {"nombre": "Demo Extra"}}}
        self.assertEqual(self.i("actualiza el demo", reg=reg, alias={})["proyecto"], "demo")
        self.assertEqual(self.i("actualiza el demo extra", reg=reg, alias={})["proyecto"], "demo-extra")

    def test_endpoint_del_chat_no_usa_al_orquestador(self):
        with mock.patch.object(panel, "orq_llamar", side_effect=AssertionError("no debe llamar al orquestador")):
            codigo, r = panel.chat_get("/api/chat/intencion", {"texto": ["recompila el demo"]})
        self.assertEqual((codigo, r["coincide"], r["proyecto"], r["nombre"]), (200, True, "demo", "Demo Tablero"))
        codigo, r = panel.chat_get("/api/chat/intencion", {"texto": ["hola, ¿qué tal?"]})
        self.assertEqual((codigo, r["coincide"]), (200, False))
        self.assertEqual(panel.chat_get("/api/chat/intencion", {"texto": [""]})[0], 400)
        self.assertEqual(panel.chat_get("/api/chat/intencion", {"texto": ["x" * 500]})[0], 400)


class Piezas(Entorno):
    def test_limpiar_salida(self):
        crudo = "\x1b[32mok\x1b[0m\r\nprogreso 10%\rprogreso 99%\rlisto\n\n\n\n\x07fin".encode()
        self.assertEqual(panel.limpiar_salida_paso(crudo), "ok\nlisto\n\nfin")
        self.assertNotIn("ghp_", panel.limpiar_salida_paso("token ghp_" + "a" * 36))
        self.assertEqual(len(panel.limpiar_salida_paso("a" * 5000, 100)), 101)

    def test_argv_de_cada_tipo(self):
        argv, cwd = panel._argv_paso(PASOS[0], self.dir)
        self.assertEqual(argv, ["npm", "ci", "--no-audit", "--no-fund"])
        self.assertEqual(Path(cwd), self.dir / "frontend")
        self.assertEqual(panel._argv_paso(PASOS[1], self.dir)[0], ["npm", "run", "build"])
        argv, cwd = panel._argv_paso(PASOS[2], self.dir)
        self.assertEqual(argv[1:4], ["-m", "pip", "install"])
        self.assertEqual(Path(argv[5]), self.dir / "backend" / "requirements.txt")
        with self.assertRaises(panel.ErrorRegistro):
            panel._argv_paso(PASOS[3], self.dir)

    def test_comando_visible_no_expone_rutas_absolutas(self):
        for p in PASOS:
            self.assertNotIn(str(self.dir), panel._comando_paso(p, self.dir))

    def test_esperar_salud_con_reintentos(self):
        s = panel.registro()["por_id"]["demo"]["servicios"][0]
        respuestas = iter([None, 503, 200])
        with mock.patch.object(panel, "sondear_salud", lambda _s: next(respuestas)):
            ok, detalle = ESPERAR_SALUD_REAL(s)
        self.assertTrue(ok)
        self.assertIn("200", detalle)

    def test_esperar_salud_se_rinde_si_no_responde(self):
        s = panel.registro()["por_id"]["demo"]["servicios"][0]
        reloj = iter(range(0, 1000, 20))
        with mock.patch.object(panel, "sondear_salud", lambda _s: None), \
                mock.patch.object(panel.time, "monotonic", lambda: next(reloj)):
            ok, detalle = ESPERAR_SALUD_REAL(s)
        self.assertFalse(ok)
        self.assertIn("no respondió", detalle)

    def test_reiniciar_servicio_apaga_y_levanta_en_orden(self):
        p = panel.registro()["por_id"]["demo"]
        ok, salida = panel._reiniciar_servicio(p, "demo-web")
        self.assertTrue(ok)
        self.assertEqual([x[1:] for x in self.llamadas if x[0] == "lanzador"], [("apagar", "demo-web"), ("levantar", "demo-web")])
        self.llamadas.clear()
        self.fallar = {"apagar"}
        ok, salida = panel._reiniciar_servicio(p, "demo-web")
        self.assertFalse(ok)
        self.assertEqual([x[1] for x in self.llamadas if x[0] == "lanzador"], ["apagar"])
        self.assertFalse(panel._reiniciar_servicio(p, "no-existe")[0])


class ProcesoReal(unittest.TestCase):
    """`_correr_proceso` de verdad, con el propio Python (no instala nada)."""

    def test_corre_y_limpia(self):
        codigo, salida = panel._correr_proceso([sys.executable, "-c", "print('hola')"], os.getcwd(), 30)
        self.assertEqual((codigo, salida), (0, "hola"))
        codigo, salida = panel._correr_proceso([sys.executable, "-c", "import sys; print('mal'); sys.exit(3)"], os.getcwd(), 30)
        self.assertEqual((codigo, salida), (3, "mal"))

    def test_tiempo_agotado(self):
        t0 = time.monotonic()
        codigo, salida = panel._correr_proceso([sys.executable, "-c", "import time; time.sleep(60)"], os.getcwd(), 1)
        self.assertIsNone(codigo)
        self.assertIn("Tiempo agotado", salida)
        self.assertLess(time.monotonic() - t0, 30)

    def test_programa_inexistente(self):
        codigo, salida = panel._correr_proceso(["programa-que-no-existe-xyz"], os.getcwd(), 5)
        self.assertIsNone(codigo)
        self.assertIn("No se pudo ejecutar", salida)


class Servidor(Entorno):
    """El servidor real (con --simular y un registro temporal): rutas, validación de claves y token."""

    def test_endpoints(self):
        datos = self.base / "datos"
        datos.mkdir()
        registro = datos / "proyectos.json"
        registro.write_text(json.dumps(self.datos), encoding="utf-8")
        puerto = puerto_libre()
        env = {**os.environ, "DEVSKILLS_DATOS": str(datos), "PYTHONIOENCODING": "utf-8"}
        base = [sys.executable, str(MOTOR / "panel" / "panel.py")]
        proceso = subprocess.Popen([*base, "servir", "--simular", "--puerto", str(puerto), "--registro", str(registro)], env=env,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: proceso.poll() is None and (proceso.kill(), proceso.wait(timeout=10)))
        url = f"http://127.0.0.1:{puerto}"
        for _ in range(60):
            try:
                urllib.request.urlopen(url + "/api/ping", timeout=1).read()
                break
            except OSError:
                time.sleep(0.25)
        else:
            self.fail("el panel no respondió")
        token = json.loads((datos / "panel" / f".token-{puerto}").read_text(encoding="utf-8"))["token"]

        def llamar(ruta, cuerpo=None, token=token):
            peticion = urllib.request.Request(url + ruta, data=None if cuerpo is None else json.dumps(cuerpo).encode(),
                                              headers={"X-Panel-Token": token, "Content-Type": "application/json"},
                                              method="GET" if cuerpo is None else "POST")
            try:
                with urllib.request.urlopen(peticion, timeout=30) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())

        # Sin receta: la propuesta del panel.
        codigo, r = llamar("/api/proyecto/aplicar?id=demo")
        self.assertEqual(codigo, 200)
        self.assertIsNone(r["receta"])
        self.assertEqual(len(r["propuesta"]["pasos"]), 4)
        self.assertTrue(r["simulacion"])
        self.assertEqual(llamar("/api/proyecto/aplicar?id=no")[0], 404)
        self.assertEqual(llamar("/api/proyecto/aplicar?id=demo&otro=1")[0], 400)
        self.assertEqual(llamar("/api/proyecto/aplicar?id=DEMO!")[0], 400)
        self.assertEqual(llamar("/api/proyecto/aplicar?id=demo", token="malo")[0], 403)
        self.assertEqual(llamar("/api/proyecto/aplicar/ejecutar", {"id": "demo"}, token="malo")[0], 403)
        self.assertEqual(llamar("/api/proyecto/aplicar/receta", {"id": "demo", "pasos": PASOS}, token="")[0], 403)
        self.assertEqual(llamar("/api/chat/intencion?texto=actualiza%20el%20demo", token="malo")[0], 403)
        # Ejecutar sin receta aprobada.
        codigo, r = llamar("/api/proyecto/aplicar/ejecutar", {"id": "demo"})
        self.assertEqual((codigo, r["sin_receta"]), (409, True))
        # Receta: claves exactas y pasos validados.
        self.assertEqual(llamar("/api/proyecto/aplicar/receta", {"id": "demo"})[0], 400)
        self.assertEqual(llamar("/api/proyecto/aplicar/receta", {"id": "demo", "pasos": PASOS, "extra": 1})[0], 400)
        self.assertEqual(llamar("/api/proyecto/aplicar/receta", {"id": "demo", "pasos": "x"})[0], 400)
        self.assertEqual(llamar("/api/proyecto/aplicar/receta", {"id": "no", "pasos": PASOS})[0], 404)
        codigo, r = llamar("/api/proyecto/aplicar/receta", {"id": "demo", "pasos": [{**PASOS[0], "carpeta": "../fuera"}]})
        self.assertEqual(codigo, 400)
        self.assertIn("..", r["error"])
        codigo, r = llamar("/api/proyecto/aplicar/receta", {"id": "demo", "pasos": [{"id": "x", "tipo": "shell", "comando": "ls"}]})
        self.assertEqual(codigo, 400)
        self.assertNotIn("aplicar", json.loads(registro.read_text(encoding="utf-8"))["proyectos"][0])
        codigo, r = llamar("/api/proyecto/aplicar/receta", {"id": "demo", "pasos": PASOS})
        self.assertEqual(codigo, 200)
        self.assertEqual(len(json.loads(registro.read_text(encoding="utf-8"))["proyectos"][0]["aplicar"]["pasos"]), 4)
        codigo, r = llamar("/api/proyecto/aplicar?id=demo")
        self.assertEqual(r["pendientes"]["texto"], "Hay cambios sin aplicar: frontend, backend")
        # Ejecutar (simulación): corre en segundo plano y no ejecuta nada.
        self.assertEqual(llamar("/api/proyecto/aplicar/ejecutar", {"id": "demo", "forzar": "si"})[0], 400)
        self.assertEqual(llamar("/api/proyecto/aplicar/ejecutar", {"id": "demo", "comando": "ls"})[0], 400)
        codigo, r = llamar("/api/proyecto/aplicar/ejecutar", {"id": "demo", "forzar": True})
        self.assertEqual(codigo, 202)
        for _ in range(60):
            e = llamar("/api/proyecto/aplicar?id=demo")[1]
            if e["ejecucion"]["estado"] != "en-curso":
                break
            time.sleep(0.25)
        self.assertEqual(e["ejecucion"]["estado"], "simulado")
        self.assertEqual([p["estado"] for p in e["ejecucion"]["pasos"]], ["simulado"] * 4)
        # Chat: la intención la resuelve el panel.
        codigo, r = llamar("/api/chat/intencion?texto=" + urllib.request.quote("aplica los cambios del demo tablero"))
        self.assertEqual((codigo, r["coincide"], r["proyecto"]), (200, True, "demo"))
        codigo, r = llamar("/api/chat/intencion?texto=" + urllib.request.quote("explícame el demo"))
        self.assertEqual((codigo, r["coincide"]), (200, False))
        subprocess.run([*base, "apagar", "--puerto", str(puerto)], env=env, timeout=20, capture_output=True)


if __name__ == "__main__":
    unittest.main()
