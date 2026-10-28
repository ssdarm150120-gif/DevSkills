"""Pruebas de «Pendientes de git» del panel (Commit y Push por proyecto).

Todo corre con repos git temporales y un remoto bare local; nada toca GitHub ni el registro real.
Correr desde motor/:  python -m unittest discover -s panel/pruebas -v
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
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

GIT = shutil.which("git")
FALSO_GITLEAKS = textwrap.dedent('''\
    import json, pathlib, sys
    args = sys.argv[1:]
    destino = pathlib.Path(args[1])
    informe = args[args.index("--report-path") + 1]
    hallazgos = [{"RuleID": "regla-falsa", "File": str(f), "StartLine": 1}
                 for f in destino.rglob("*") if f.is_file() and "SECRETO-FALSO" in f.read_text(errors="ignore")]
    if hallazgos:
        json.dump(hallazgos, open(informe, "w"))
        sys.exit(1)
    sys.exit(0)
''')


def git(carpeta, *args, entrada=None):
    r = subprocess.run([GIT, "-C", str(carpeta), *args], capture_output=True, input=entrada, timeout=60)
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} -> {r.returncode}: {r.stderr.decode(errors='replace')}")
    return r.stdout.decode("utf-8", errors="replace").strip()


def escribir(ruta, texto="x\n"):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8", newline="\n")


def iniciar_repo(carpeta, rama="main"):
    Path(carpeta).mkdir(parents=True, exist_ok=True)
    git(carpeta, "init", "-q", "-b", rama)
    git(carpeta, "config", "user.name", "Prueba")
    git(carpeta, "config", "user.email", "prueba@example.com")
    git(carpeta, "config", "core.autocrlf", "false")
    git(carpeta, "config", "commit.gpgsign", "false")


def reg_de(pid, carpeta, cuenta="cuenta-a"):
    return {"por_id": {pid: {"id": pid, "carpeta": str(carpeta), "repositorio": {"cuenta": cuenta} if cuenta else None}},
            "cuentas": [{"id": "cuenta-a", "nombre": "A", "tipo": "personal"}, {"id": "cuenta-b", "nombre": "B", "tipo": "personal"}]}


class Entorno(unittest.TestCase):
    """Repo de trabajo con remoto bare local (origin), rama por omisión main y una rama feat/x checada."""

    @classmethod
    def setUpClass(cls):
        if not GIT:
            raise unittest.SkipTest("git no está disponible")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.remoto = base / "remoto.git"
        subprocess.run([GIT, "init", "-q", "--bare", "-b", "main", str(self.remoto)], check=True, capture_output=True)
        self.dir = base / "proyecto con espacios"
        iniciar_repo(self.dir)
        escribir(self.dir / "README.md", "base\n")
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-q", "-m", "chore: base")
        git(self.dir, "remote", "add", "origin", str(self.remoto))
        git(self.dir, "push", "-q", "-u", "origin", "main")
        git(self.dir, "remote", "set-head", "origin", "main")
        git(self.dir, "checkout", "-q", "-b", "feat/x")
        self.pid = "demo"
        patcher = mock.patch.object(panel, "registro", lambda: reg_de(self.pid, self.dir))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._restaurar_simular, panel.ESTADO["simular"])
        panel.ESTADO["simular"] = False
        # Los registros del panel (log) no deben escribirse en el HOME real durante las pruebas.
        p2 = mock.patch.object(panel, "ARCHIVO_LOG", base / "panel.log")
        p2.start()
        self.addCleanup(p2.stop)

    @staticmethod
    def _restaurar_simular(valor):
        panel.ESTADO["simular"] = valor

    def cabeza(self):
        return git(self.dir, "rev-parse", "HEAD")

    def gitleaks_falso(self):
        """PATH con un `gitleaks` falso (y git); sin winget. Devuelve el administrador de contexto."""
        carpeta = Path(self.tmp.name) / "falso"
        carpeta.mkdir(exist_ok=True)
        escribir(carpeta / "falso.py", FALSO_GITLEAKS)
        if os.name == "nt":
            (carpeta / "gitleaks.cmd").write_text(f'@"{sys.executable}" "{carpeta / "falso.py"}" %*\r\n')
        else:
            destino = carpeta / "gitleaks"
            destino.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{carpeta / "falso.py"}" "$@"\n')
            destino.chmod(0o755)
        return self._con_path(str(carpeta))

    def sin_gitleaks(self):
        return self._con_path(None)

    def _con_path(self, extra):
        vacio = Path(self.tmp.name) / "vacio"
        vacio.mkdir(exist_ok=True)
        partes = [p for p in (extra, str(Path(GIT).parent)) if p]
        return mock.patch.dict(os.environ, {"PATH": os.pathsep.join(partes), "LOCALAPPDATA": str(vacio)})


class Propuesta(unittest.TestCase):
    def test_tipo_segun_el_prefijo_de_la_rama(self):
        casos = {"fix/panel": ("fix", None), "feat/panel-git": ("feat", None), "docs/motor": ("docs", None),
                 "en-02": ("wip", "en-02"), "hu-07-lo-que-sea": ("wip", "hu-07"), "EN-12": ("wip", "en-12"),
                 "experimento": ("chore", None), "refactor/x": ("chore", None), None: ("chore", None)}
        for rama, esperado in casos.items():
            self.assertEqual(panel.tipo_de_rama(rama), esperado, rama)

    def test_mensaje_propuesto(self):
        un = [{"ruta": "motor/panel/panel.py", "estado": "M", "original": None}]
        self.assertEqual(panel.proponer_mensaje("fix/algo", un), "fix: actualiza panel.py")
        self.assertEqual(panel.proponer_mensaje("hu-07", un), "wip(hu-07): actualiza panel.py")
        nuevos = [{"ruta": f"a/{n}.py", "estado": "??", "original": None} for n in "abcde"]
        self.assertEqual(panel.proponer_mensaje("feat/x", nuevos), "feat: agrega 5 archivos (a.py, b.py, c.py y 2 más)")
        borrados = [{"ruta": "x.md", "estado": "D", "original": None}, {"ruta": "y.md", "estado": "D", "original": None}]
        self.assertEqual(panel.proponer_mensaje("otra", borrados), "chore: elimina 2 archivos (x.md, y.md)")
        self.assertEqual(panel.proponer_mensaje("feat/x", []), "")

    def test_el_mensaje_propuesto_siempre_valida(self):
        largo = [{"ruta": "d/" + "n" * 200 + ".py", "estado": "M", "original": None}] * 4
        for rama in ("fix/a", "en-02", "otra", None):
            for entradas in (largo, largo[:1]):
                panel.validar_mensaje_commit(panel.proponer_mensaje(rama, entradas))


class ValidacionDelMensaje(unittest.TestCase):
    def test_formatos_validos(self):
        for m in ("feat: agrega algo", "fix(panel): corrige", "wip(en-02): avance", "feat(api)!: cambia el contrato",
                  "docs: nota breve\n\ncuerpo con detalle\nsegunda línea", "revert: deshace lo anterior", "  chore: con espacios  "):
            self.assertTrue(panel.validar_mensaje_commit(m).endswith("\n"), m)

    def test_formatos_invalidos(self):
        malos = ["", "   ", "arregla cosas", "feature: algo", "feat:sin espacio", "feat: ", "feat: ab", "Feat: algo",
                 "feat(): algo", "feat: " + "x" * 120, "feat: algo\ncuerpo sin línea en blanco",
                 "feat: x y z\n\nCo-Authored-By: Alguien <a@b.c>", "feat: x y z\n\nGenerated with Claude Code",
                 "feat: con\x00nulo", None, 5]
        for m in malos:
            with self.assertRaises(ValueError, msg=repr(m)):
                panel.validar_mensaje_commit(m)

    def test_rutas_con_forma_invalida(self):
        for malo in ([], "a.py", [""], [5], ["../x"], ["a/../../x"], ["a\\..\\x"], ["/etc/passwd"], ["C:\\x"],
                     ["C:x"], ["~/x"], ["\\\\srv\\x"], ["a\0b"], ["a\nb"]):
            with self.assertRaises(ValueError, msg=repr(malo)):
                panel.validar_rutas_commit(malo)
        self.assertEqual(panel.validar_rutas_commit(["a/b c.py", "a/b c.py", "ñ/é.md"]), ["a/b c.py", "ñ/é.md"])


class Archivos(Entorno):
    def test_porcelain_con_espacios_acentos_renombres_y_carpetas_nuevas(self):
        escribir(self.dir / "con espacio y acento é.txt")
        escribir(self.dir / "carpeta nueva" / "uno.txt")
        escribir(self.dir / "carpeta nueva" / "dos.txt")
        (self.dir / "README.md").write_text("cambiado\n")
        git(self.dir, "mv", "README.md", "LEEME.md")
        por_ruta = {e["ruta"]: e for e in panel.estado_archivos(str(self.dir))}
        self.assertEqual(set(por_ruta), {"LEEME.md", "con espacio y acento é.txt", "carpeta nueva/uno.txt", "carpeta nueva/dos.txt"})
        self.assertEqual(por_ruta["LEEME.md"]["estado"], "R")
        self.assertEqual(por_ruta["LEEME.md"]["original"], "README.md")
        self.assertEqual(por_ruta["carpeta nueva/uno.txt"]["estado"], "??")

    def test_no_es_repo_o_esta_dentro_de_otro(self):
        sin_git = Path(self.tmp.name) / "sin_git"
        sin_git.mkdir()
        with mock.patch.object(panel, "registro", lambda: reg_de("p", sin_git)):
            r = panel.estado_git("p")
        self.assertFalse(r["es_repo"])
        self.assertFalse(r["commit"]["visible"] or r["push"]["visible"])
        interna = self.dir / "sub"
        interna.mkdir()
        with mock.patch.object(panel, "registro", lambda: reg_de("p", interna)):
            r = panel.estado_git("p")
        self.assertFalse(r["es_repo"])
        self.assertIn("raíz", r["motivo"])
        with self.assertRaises(KeyError):
            panel.estado_git("no-existe")


class Pendientes(Entorno):
    def test_compara_contra_el_remoto_y_no_contra_el_main_local(self):
        base = Path(self.tmp.name)
        # Otro clon avanza origin/main con dos commits; el main local se queda atrás.
        otro = base / "otro"
        subprocess.run([GIT, "clone", "-q", str(self.remoto), str(otro)], check=True, capture_output=True)
        git(otro, "config", "user.name", "Otro")
        git(otro, "config", "user.email", "otro@example.com")
        for n in ("c2", "c3"):
            escribir(otro / f"{n}.txt")
            git(otro, "add", "-A")
            git(otro, "commit", "-q", "-m", f"chore: {n}")
        git(otro, "push", "-q", "origin", "main")
        git(self.dir, "fetch", "-q", "origin")
        # `feat/viejo` ya está integrada en origin/main (apunta a c3); `feat/nueva` sale de origin/main con 1 commit propio.
        git(self.dir, "branch", "feat/viejo", "origin/main")
        git(self.dir, "checkout", "-q", "-b", "feat/nueva", "origin/main")
        escribir(self.dir / "propio.txt")
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-q", "-m", "feat: propio")
        self.assertEqual(git(self.dir, "rev-list", "--count", "main..feat/nueva"), "3")  # contra el main local daría 3
        r = panel.estado_git(self.pid)
        self.assertEqual([x["rama"] for x in r["ramas"]], ["feat/nueva"])
        rama = r["ramas"][0]
        self.assertEqual(rama["total"], 1)
        self.assertEqual(rama["commits"][0]["asunto"], "feat: propio")
        self.assertFalse(rama["remoto"])
        self.assertEqual(rama["sin_subir"], 1)
        self.assertEqual(r["sin_subir"], 1)
        self.assertEqual(r["rama_por_omision"], "main")

    def test_vista_basica_upstream_stashes_y_ultima_consulta(self):
        escribir(self.dir / "a.txt")
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-q", "-m", "feat: a")
        git(self.dir, "push", "-q", "-u", "origin", "feat/x")
        escribir(self.dir / "b.txt")
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-q", "-m", "feat: b")
        escribir(self.dir / "README.md", "otra cosa\n")
        git(self.dir, "stash", "-q")
        escribir(self.dir / "README.md", "sin commit\n")
        r = panel.estado_git(self.pid)
        self.assertEqual((r["rama"], r["upstream"], r["adelante"], r["atras"]), ("feat/x", "origin/feat/x", 1, 0))
        self.assertEqual(r["sin_subir"], 1)
        self.assertEqual(r["stashes"], 1)
        self.assertEqual([(a["ruta"], a["estado"]) for a in r["archivos"]], [("README.md", "M")])
        self.assertTrue(r["commit"]["habilitado"] and r["push"]["habilitado"])
        self.assertEqual(r["mensaje_propuesto"], "feat: actualiza README.md")

    def test_en_main_el_push_no_aparece_y_se_avisa(self):
        git(self.dir, "checkout", "-q", "main")
        escribir(self.dir / "a.txt")
        r = panel.estado_git(self.pid)
        self.assertTrue(r["protegida"])
        self.assertFalse(r["push"]["visible"])
        self.assertIn("bloqueado", r["push"]["motivo"])
        self.assertTrue(r["commit"]["visible"] and r["commit"]["habilitado"])

    def test_sin_commits_sin_subir_el_push_queda_deshabilitado(self):
        r = panel.estado_git(self.pid)  # feat/x recién creada desde main: nada propio
        self.assertTrue(r["push"]["visible"])
        self.assertFalse(r["push"]["habilitado"])

    def test_actualizar_hace_fetch_y_en_simulacion_no(self):
        panel.ESTADO["simular"] = True
        r = panel.estado_git(self.pid, actualizar=True)
        self.assertTrue(r["fetch"]["simulado"])
        panel.ESTADO["simular"] = False
        r = panel.estado_git(self.pid, actualizar=True)
        self.assertTrue(r["fetch"]["hecho"])
        self.assertIsNotNone(r["ultima_consulta"])


class Commit(Entorno):
    def test_solo_se_aceptan_rutas_que_estan_en_porcelain(self):
        escribir(self.dir / "nuevo.txt")
        antes = self.cabeza()
        for ruta in ("README.md", "no-existe.txt", "carpeta/otro.txt", "nuevo.txt/"):  # README.md no tiene cambios
            codigo, r = panel.git_commit(self.pid, [ruta], "feat: algo valido")
            self.assertEqual(codigo, 400, ruta)
            self.assertIn("rechazadas", r)
        for ruta in ("../fuera.txt", "/etc/passwd", "C:\\Windows\\x", "a/../../b"):
            with self.assertRaises(ValueError):
                panel.git_commit(self.pid, [ruta], "feat: algo valido")
        # una mezcla válida + inválida no commitea nada
        codigo, _ = panel.git_commit(self.pid, ["nuevo.txt", "README.md"], "feat: algo valido")
        self.assertEqual(codigo, 400)
        self.assertEqual(self.cabeza(), antes)
        self.assertEqual(git(self.dir, "diff", "--cached", "--name-only"), "")

    def test_mensaje_invalido_no_commitea(self):
        escribir(self.dir / "nuevo.txt")
        with self.assertRaises(ValueError):
            panel.git_commit(self.pid, ["nuevo.txt"], "arreglo rápido")
        self.assertEqual(git(self.dir, "diff", "--cached", "--name-only"), "")

    def test_commit_de_los_elegidos_sin_arrastrar_lo_demas(self):
        escribir(self.dir / "uno con espacio.txt", "uno\n")
        escribir(self.dir / "ñandú.txt", "dos\n")
        escribir(self.dir / "ajeno.txt", "no va\n")
        escribir(self.dir / "preparado.txt", "ya estaba en el índice\n")
        git(self.dir, "add", "preparado.txt")  # otro archivo ya preparado: tampoco debe entrar
        with self.gitleaks_falso():
            codigo, r = panel.git_commit(self.pid, ["uno con espacio.txt", "ñandú.txt"], "feat: dos archivos\n\ncuerpo")
        self.assertEqual(codigo, 200, r)
        self.assertEqual(r["gitleaks"], "limpio")
        nombres = set(git(self.dir, "-c", "core.quotepath=off", "show", "--name-only", "--format=", "HEAD").splitlines())
        self.assertEqual(nombres, {"uno con espacio.txt", "ñandú.txt"})
        pendientes = {a["ruta"] for a in r["pendientes"]["archivos"]}
        self.assertEqual(pendientes, {"ajeno.txt", "preparado.txt"})
        mensaje = git(self.dir, "log", "-1", "--format=%B")
        self.assertTrue(mensaje.startswith("feat: dos archivos"))
        self.assertNotIn("Co-Authored-By", mensaje)

    def test_renombre_y_borrado(self):
        git(self.dir, "mv", "README.md", "LEEME.md")
        with self.gitleaks_falso():
            codigo, r = panel.git_commit(self.pid, ["LEEME.md"], "docs: renombra el readme")
        self.assertEqual(codigo, 200, r)
        self.assertEqual(git(self.dir, "show", "--name-status", "--format=", "-M", "HEAD").split()[0][0], "R")
        self.assertEqual(git(self.dir, "status", "--porcelain"), "")
        (self.dir / "LEEME.md").unlink()
        with self.gitleaks_falso():
            codigo, r = panel.git_commit(self.pid, ["LEEME.md"], "docs: borra el leeme")
        self.assertEqual(codigo, 200, r)
        self.assertEqual(git(self.dir, "status", "--porcelain"), "")

    def test_gitleaks_con_hallazgos_no_commitea(self):
        escribir(self.dir / "config.txt", "clave = SECRETO-FALSO\n")
        escribir(self.dir / "limpio.txt")
        antes = self.cabeza()
        with self.gitleaks_falso():
            codigo, r = panel.git_commit(self.pid, ["config.txt", "limpio.txt"], "feat: con secreto")
        self.assertEqual(codigo, 422)
        self.assertEqual(r["gitleaks"], "hallazgos")
        self.assertEqual(r["hallazgos"][0]["archivo"], "config.txt")
        self.assertNotIn("SECRETO-FALSO", json.dumps(r))
        self.assertEqual(self.cabeza(), antes)
        self.assertEqual(git(self.dir, "diff", "--cached", "--name-only"), "")  # ni siquiera se preparó
        # desmarcando el archivo con el secreto, el commit pasa
        with self.gitleaks_falso():
            codigo, _ = panel.git_commit(self.pid, ["limpio.txt"], "feat: sin secreto")
        self.assertEqual(codigo, 200)

    def test_gitleaks_no_disponible_no_commitea(self):
        escribir(self.dir / "nuevo.txt")
        antes = self.cabeza()
        with self.sin_gitleaks():
            self.assertIsNone(panel.buscar_gitleaks())
            codigo, r = panel.git_commit(self.pid, ["nuevo.txt"], "feat: sin escaner")
        self.assertEqual(codigo, 503)
        self.assertEqual(r["gitleaks"], "no_disponible")
        self.assertIn("NO se hizo el commit", r["error"])
        self.assertEqual(self.cabeza(), antes)
        self.assertEqual(git(self.dir, "diff", "--cached", "--name-only"), "")

    def test_gitleaks_que_falla_con_otro_codigo_tampoco_cuenta_como_bueno(self):
        escribir(self.dir / "nuevo.txt")
        with mock.patch.object(panel, "buscar_gitleaks", lambda: sys.executable), \
                mock.patch.object(panel.subprocess, "run", return_value=subprocess.CompletedProcess([], 126, b"", b"")):
            r = panel.escanear_gitleaks(str(self.dir), ["nuevo.txt"])
        self.assertEqual(r["estado"], "no_disponible")

    def test_simular_no_ejecuta_nada(self):
        escribir(self.dir / "nuevo.txt")
        antes = self.cabeza()
        panel.ESTADO["simular"] = True
        with self.sin_gitleaks():
            codigo, r = panel.git_commit(self.pid, ["nuevo.txt"], "feat: simulado")
        self.assertEqual(codigo, 200)
        self.assertTrue(r["simulado"])
        self.assertFalse(r["cambio"])
        self.assertTrue(any("commit" in c for c in r["comandos"]))
        self.assertEqual(self.cabeza(), antes)
        self.assertEqual(git(self.dir, "diff", "--cached", "--name-only"), "")

    def test_archivos_con_pinta_de_credencial_no_se_commitean(self):
        escribir(self.dir / ".env", "A=1\n")
        escribir(self.dir / ".env.example", "A=\n")
        with self.gitleaks_falso():
            self.assertEqual(panel.git_commit(self.pid, [".env"], "feat: env")[0], 409)
            self.assertEqual(panel.git_commit(self.pid, [".env.example"], "feat: ejemplo de env")[0], 200)

    def test_cabeza_desacoplada_no_commitea(self):
        escribir(self.dir / "nuevo.txt")
        git(self.dir, "checkout", "-q", "--detach")
        self.assertEqual(panel.git_commit(self.pid, ["nuevo.txt"], "feat: algo valido")[0], 409)
        self.assertFalse(panel.estado_git(self.pid)["commit"]["habilitado"])


class Push(Entorno):
    def commit_propio(self, nombre="p.txt"):
        escribir(self.dir / nombre)
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-q", "-m", f"feat: {nombre}")

    def sin_verificar_cuenta(self):
        return mock.patch.object(panel, "verificar_cuenta_push", lambda *a: (None, None))

    def test_bloqueado_en_main_master_y_en_la_rama_por_omision(self):
        git(self.dir, "checkout", "-q", "main")
        self.commit_propio()
        with self.sin_verificar_cuenta():
            codigo, r = panel.git_push(self.pid, "main")
        self.assertEqual(codigo, 409)
        self.assertTrue(r["bloqueada"])
        # rama por omisión del remoto distinta de main/master
        git(self.dir, "checkout", "-q", "-b", "trunk")
        git(self.dir, "push", "-q", "origin", "trunk")
        git(self.dir, "fetch", "-q", "origin")
        git(self.dir, "remote", "set-head", "origin", "trunk")
        self.assertEqual(panel.rama_por_omision(str(self.dir)), "trunk")
        with self.sin_verificar_cuenta():
            codigo, r = panel.git_push(self.pid, "trunk")
        self.assertEqual(codigo, 409)
        self.assertTrue(r["bloqueada"])
        # master
        git(self.dir, "checkout", "-q", "-b", "master")
        with self.sin_verificar_cuenta():
            self.assertEqual(panel.git_push(self.pid, "master")[0], 409)
        self.assertEqual(git(self.dir, "ls-remote", "--heads", "origin", "master"), "")

    def test_sube_solo_la_rama_actual_con_upstream(self):
        self.commit_propio()
        git(self.dir, "branch", "otra")
        with self.sin_verificar_cuenta():
            codigo, r = panel.git_push(self.pid, "otra")  # no es HEAD
            self.assertEqual(codigo, 409)
            self.assertEqual(git(self.dir, "ls-remote", "--heads", "origin", "otra"), "")
            codigo, r = panel.git_push(self.pid, "feat/x")
        self.assertEqual(codigo, 200, r)
        self.assertEqual(r["comandos"], ["git push -u origin feat/x"])
        self.assertEqual(git(self.dir, "rev-parse", "origin/feat/x"), self.cabeza())
        self.assertEqual(git(self.dir, "rev-parse", "--abbrev-ref", "feat/x@{upstream}"), "origin/feat/x")
        self.assertEqual(r["pendientes"]["sin_subir"], 0)
        # con upstream ya no lleva -u
        self.commit_propio("q.txt")
        with self.sin_verificar_cuenta():
            codigo, r = panel.git_push(self.pid, "feat/x")
        self.assertEqual((codigo, r["comandos"]), (200, ["git push origin feat/x"]))

    def test_nunca_se_usa_force(self):
        self.commit_propio()
        capturados = []
        real = panel._git_ejecutar

        def espia(args, carpeta, **kw):
            capturados.append(list(args))
            return real(args, carpeta, **kw)

        with self.sin_verificar_cuenta(), mock.patch.object(panel, "_git_ejecutar", espia):
            panel.git_push(self.pid, "feat/x")
        pushes = [a for a in capturados if a and a[0] == "push"]
        self.assertEqual(len(pushes), 1)
        for a in pushes[0]:
            self.assertFalse(a.startswith("--force") or a == "-f" or a.startswith("+"), a)
        for peligrosa in ("--force", "-f", "--force-with-lease"):
            with self.assertRaises(RuntimeError):
                panel.comando_push(peligrosa, False)
        with self.assertRaises(RuntimeError):
            panel.comando_push("+rama", True)
        with self.assertRaises(ValueError):
            panel.git_push(self.pid, "--force")

    def test_si_el_remoto_diverge_el_push_falla_y_no_pisa(self):
        self.commit_propio()
        otro = Path(self.tmp.name) / "otro"
        subprocess.run([GIT, "clone", "-q", str(self.remoto), str(otro)], check=True, capture_output=True)
        git(otro, "config", "user.name", "Otro")
        git(otro, "config", "user.email", "otro@example.com")
        git(otro, "checkout", "-q", "-b", "feat/x")
        escribir(otro / "ajeno.txt")
        git(otro, "add", "-A")
        git(otro, "commit", "-q", "-m", "feat: ajeno")
        git(otro, "push", "-q", "origin", "feat/x")
        del_otro = git(self.remoto, "rev-parse", "feat/x")
        with self.sin_verificar_cuenta():
            codigo, r = panel.git_push(self.pid, "feat/x")
        self.assertEqual(codigo, 500)
        self.assertFalse(r["ok"])
        self.assertEqual(git(self.remoto, "rev-parse", "feat/x"), del_otro)

    def test_simular_no_sube(self):
        self.commit_propio()
        panel.ESTADO["simular"] = True
        with self.sin_verificar_cuenta():
            codigo, r = panel.git_push(self.pid, "feat/x")
        self.assertEqual(codigo, 200)
        self.assertTrue(r["simulado"])
        self.assertEqual(r["comandos"], ["git push -u origin feat/x"])
        self.assertEqual(git(self.dir, "ls-remote", "--heads", "origin", "feat/x"), "")

    def test_remoto_local_sin_cuenta_verificable_sube_con_advertencia(self):
        """Con un remoto que no es https://github.com la cuenta no se puede comprobar: se advierte, no se bloquea."""
        self.commit_propio()
        codigo, r = panel.git_push(self.pid, "feat/x")
        self.assertEqual(codigo, 200, r)
        self.assertIn("no se pudo comprobar", r["advertencia"])
        self.assertEqual(git(self.dir, "rev-parse", "origin/feat/x"), self.cabeza())


class CuentaDelPush(Entorno):
    URL = "https://github.com/dueno/repo.git"
    GH_B_ACTIVA = {"disponible": True, "activa": "cuenta-b", "error": None,
                   "cuentas": [{"id": "cuenta-a", "activa": False, "ok": True}, {"id": "cuenta-b", "activa": True, "ok": True}]}

    def verificar(self, url=URL, usuario_repo=None, modo="gcm", gh=None, cuenta="cuenta-a"):
        p = {"repositorio": {"cuenta": cuenta} if cuenta else None}
        cred = {"usuario": usuario_repo, "modo": modo}
        gh = gh or {"disponible": True, "cuentas": [], "activa": None, "error": None}
        with mock.patch.object(panel, "_url_remoto", lambda raiz: url), \
                mock.patch.object(panel, "credencial_repo", lambda pid: cred), \
                mock.patch.object(panel, "estado_gh", lambda forzar=False: gh):
            return panel.verificar_cuenta_push(self.pid, p, str(self.dir))

    def test_analiza_la_url_sin_conservar_claves(self):
        self.assertEqual(panel.analizar_url_remoto("https://ssdarm@github.com/o/r.git"), ("ssdarm", "github.com"))
        self.assertEqual(panel.analizar_url_remoto("https://usr:clave@github.com/o/r.git"), ("usr", "github.com"))
        self.assertEqual(panel.analizar_url_remoto("https://github.com/o/r.git"), (None, "github.com"))
        self.assertEqual(panel.analizar_url_remoto("git@github.com:o/r.git"), (None, None))
        self.assertEqual(panel.analizar_url_remoto(None), (None, None))

    def test_modo_del_helper(self):
        self.assertEqual(panel.modo_helper(["manager"]), "gcm")
        self.assertEqual(panel.modo_helper([panel.HELPER_GH]), "gh")

    def test_sin_cuenta_asignada_o_remoto_no_github_solo_advierte(self):
        fallo, adv = self.verificar(cuenta=None)
        self.assertIsNone(fallo)
        self.assertIn("no tiene cuenta", adv)
        for url in ("git@github.com:o/r.git", "https://gitlab.com/o/r.git", str(self.remoto), None):
            fallo, adv = self.verificar(url=url, usuario_repo="cuenta-a")
            self.assertIsNone(fallo, url)
            self.assertIn("no se pudo comprobar", adv)

    # ---- modo GCM (Git Credential Manager): la cuenta activa de gh NO decide
    def test_gcm_ignora_la_cuenta_activa_de_gh(self):
        # gh activa = cuenta-b, pero con GCM y la URL con usuario cuenta-a el push sale con cuenta-a: no se bloquea.
        self.assertEqual(self.verificar(url="https://cuenta-a@github.com/o/r.git", modo="gcm", gh=self.GH_B_ACTIVA), (None, None))
        self.assertEqual(self.verificar(modo="gcm", usuario_repo="Cuenta-A", gh=self.GH_B_ACTIVA), (None, None))

    def test_gcm_sin_usuario_conocido_advierte_y_no_bloquea(self):
        fallo, adv = self.verificar(modo="gcm", usuario_repo=None, gh=self.GH_B_ACTIVA)
        self.assertIsNone(fallo)
        self.assertIn("No se pudo determinar", adv)
        self.assertIn("cuenta-a", adv)
        self.assertNotIn("github.com/", adv)

    def test_gcm_con_usuario_conocido_distinto_si_bloquea(self):
        fallo, adv = self.verificar(modo="gcm", usuario_repo="cuenta-b")
        self.assertEqual(fallo[0], 409)
        self.assertTrue(fallo[1]["requiere_cuenta_repo"])
        self.assertEqual(fallo[1]["accion"], {"ruta": "/api/proyecto/credencial", "cuerpo": {"proyecto": self.pid, "cuenta": "cuenta-a"}})
        fallo, _ = self.verificar(url="https://cuenta-b@github.com/o/r.git", modo="gcm", usuario_repo="cuenta-a")
        self.assertEqual(fallo[0], 409)
        self.assertNotIn("accion", fallo[1])
        self.assertNotIn("github.com", fallo[1]["error"])  # nunca se muestra la URL

    # ---- modo gh: manda la cuenta activa de gh y se exige el login
    def test_gh_con_cuenta_activa_distinta_pide_cambiarla(self):
        fallo, _ = self.verificar(modo="gh", usuario_repo=None, gh=self.GH_B_ACTIVA)
        self.assertEqual(fallo[0], 409)
        self.assertTrue(fallo[1]["requiere_cambio_cuenta"])
        self.assertEqual(fallo[1]["accion"], {"ruta": "/api/github/cuenta", "cuerpo": {"cuenta": "cuenta-a"}})

    def test_gh_sin_login_requiere_login(self):
        gh = {"disponible": True, "activa": "cuenta-b", "error": None, "cuentas": [{"id": "cuenta-b", "activa": True, "ok": True}]}
        fallo, _ = self.verificar(modo="gh", usuario_repo="cuenta-a", gh=gh)
        self.assertEqual(fallo[0], 409)
        self.assertTrue(fallo[1]["requiere_login"])
        self.assertEqual(fallo[1]["instruccion"], panel.INSTRUCCION_LOGIN)

    def test_gh_coincide_o_sin_gh_disponible(self):
        gh = {"disponible": True, "activa": "cuenta-a", "error": None, "cuentas": [{"id": "cuenta-a", "activa": True, "ok": True}]}
        self.assertEqual(self.verificar(modo="gh", usuario_repo=None, gh=gh), (None, None))
        self.assertEqual(self.verificar(modo="gh", usuario_repo="cuenta-a", gh=gh), (None, None))
        sin_gh = {"disponible": False, "cuentas": [], "activa": None, "error": "No hay gh"}
        self.assertEqual(self.verificar(modo="gh", usuario_repo=None, gh=sin_gh)[0][0], 503)

    def test_cuenta_que_no_coincide_impide_el_push_real_y_no_cambia_nada(self):
        escribir(self.dir / "p.txt")
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-q", "-m", "feat: p")
        git(self.dir, "remote", "set-url", "origin", self.URL)
        git(self.dir, "config", "--local", panel.CLAVE_USUARIO, "cuenta-b")
        gh = {"disponible": True, "cuentas": [], "activa": None, "error": None}
        with mock.patch.object(panel, "estado_gh", lambda forzar=False: gh):
            codigo, r = panel.git_push(self.pid, "feat/x")
            vista = panel.estado_git(self.pid)
        self.assertEqual(codigo, 409)
        self.assertTrue(r["requiere_cuenta_repo"])
        self.assertEqual(git(self.dir, "config", "--local", panel.CLAVE_USUARIO), "cuenta-b")  # no se cambió en silencio
        self.assertEqual(vista["push"]["cuenta"]["estado"], "bloqueada")
        self.assertIn("accion", vista["push"]["cuenta"])

    def test_la_vista_lleva_la_advertencia_para_el_modal(self):
        escribir(self.dir / "p.txt")
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-q", "-m", "feat: p")
        git(self.dir, "remote", "set-url", "origin", self.URL)
        with mock.patch.object(panel, "estado_gh", lambda forzar=False: self.GH_B_ACTIVA), \
                mock.patch.object(panel, "modo_helper", lambda v: "gcm"):
            vista = panel.estado_git(self.pid)
        self.assertEqual(vista["push"]["cuenta"]["estado"], "advertencia")
        self.assertIn("No se pudo determinar", vista["push"]["cuenta"]["mensaje"])


class Rutas(Entorno):
    """El servidor real (con --simular y un registro temporal): rutas, validación de claves y token."""

    def test_endpoints(self):
        datos = Path(self.tmp.name) / "datos"
        datos.mkdir()
        registro = datos / "proyectos.json"
        registro.write_text(json.dumps({"version": 1, "cuentas": [{"id": "cuenta-a", "nombre": "A", "tipo": "personal"}],
                                        "proyectos": [{"id": "demo", "nombre": "Demo", "descripcion": "x", "carpeta": str(self.dir),
                                                       "repositorio": {"cuenta": "cuenta-a"}, "servicios": []}]}), encoding="utf-8")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            puerto = s.getsockname()[1]
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
                with urllib.request.urlopen(peticion, timeout=20) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())

        escribir(self.dir / "nuevo.txt")
        codigo, r = llamar("/api/proyecto/git?id=demo")
        self.assertEqual(codigo, 200)
        self.assertEqual([a["ruta"] for a in r["archivos"]], ["nuevo.txt"])
        self.assertTrue(r["simulacion"])
        self.assertEqual(r["mensaje_propuesto"], "feat: agrega nuevo.txt")
        self.assertEqual(llamar("/api/proyecto/git?id=no")[0], 404)
        self.assertEqual(llamar("/api/proyecto/git?id=demo&otro=1")[0], 400)
        self.assertEqual(llamar("/api/proyecto/git?id=demo", token="malo")[0], 403)
        codigo, r = llamar("/api/proyecto/git/commit", {"id": "demo", "archivos": ["nuevo.txt"], "mensaje": "feat: nuevo"})
        self.assertEqual((codigo, r["simulado"]), (200, True))
        self.assertEqual(llamar("/api/proyecto/git/commit", {"id": "demo", "archivos": ["../x"], "mensaje": "feat: nuevo"})[0], 400)
        self.assertEqual(llamar("/api/proyecto/git/commit", {"id": "demo", "archivos": ["nuevo.txt"], "mensaje": "malo"})[0], 400)
        self.assertEqual(llamar("/api/proyecto/git/commit", {"id": "demo", "archivos": ["nuevo.txt"], "mensaje": "feat: x y", "extra": 1})[0], 400)
        self.assertEqual(llamar("/api/proyecto/git/commit", {"id": "no", "archivos": ["nuevo.txt"], "mensaje": "feat: nuevo"})[0], 404)
        self.assertEqual(llamar("/api/proyecto/git/push", {"id": "demo", "rama": "feat/x", "force": True})[0], 400)
        codigo, r = llamar("/api/proyecto/git/push", {"id": "demo", "rama": "main"})
        self.assertEqual(codigo, 409)  # feat/x es HEAD
        self.assertEqual(git(self.dir, "status", "--porcelain"), "?? nuevo.txt")
        subprocess.run([*base, "apagar", "--puerto", str(puerto)], env=env, timeout=20, capture_output=True)


@unittest.skipUnless(GIT and panel.buscar_gitleaks(), "requiere gitleaks real")
class ConGitleaksReal(Entorno):
    def test_detecta_un_token_de_github_y_acepta_un_archivo_limpio(self):
        token = "ghp_" + "a1B2c3D4e5F6g7H8i9J0" + "k1L2m3N4o5P6q7R8"  # armado en dos partes: el repo se escanea a sí mismo
        escribir(self.dir / "malo.txt", f"token = {token}\n")
        escribir(self.dir / "bueno.txt", "hola\n")
        self.assertEqual(panel.escanear_gitleaks(str(self.dir), ["bueno.txt"])["estado"], "limpio")
        r = panel.escanear_gitleaks(str(self.dir), ["malo.txt"])
        self.assertEqual(r["estado"], "hallazgos")
        self.assertNotIn(token, json.dumps(r))


if __name__ == "__main__":
    unittest.main()
