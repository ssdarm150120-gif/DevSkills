"""Pruebas de ``devskills motor enganchar`` (comun/enganchar.py) y de los hooks que trae el plugin.

Todo ocurre en carpetas temporales (--config): nunca se toca el settings.json real de Claude Code.

Correr desde motor/:  python -m unittest discover -s comun/pruebas -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MOTOR = Path(__file__).resolve().parents[2]
RAIZ = MOTOR.parent
sys.path.insert(0, str(MOTOR))

from comun import enganchar  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.cfg = Path(self._t.name) / "cfg"
        self.cfg.mkdir()
        self.settings = self.cfg / "settings.json"

    def escribir(self, datos):
        self.settings.write_text(json.dumps(datos), encoding="utf-8")

    def leer(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def respaldos(self):
        return sorted(p.name for p in self.cfg.glob("settings.json.bak-*"))

    def correr(self, *args):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
        return subprocess.run([sys.executable, str(MOTOR / "comun" / "enganchar.py"), "--config", str(self.cfg), *args],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", env=env,
                              timeout=60)


class StatusLine(Base):
    def test_crea_el_archivo_con_la_ruta_de_este_equipo(self):
        r = self.correr("--si")
        self.assertEqual(r.returncode, 0, r.stderr)
        sl = self.leer()["statusLine"]
        self.assertEqual(sl["type"], "command")
        self.assertEqual(sl["refreshInterval"], 60)
        self.assertIn((MOTOR / "panel" / "statusline_limites.py").as_posix(), sl["command"])
        self.assertTrue(sl["command"].startswith(enganchar.comillas(enganchar.interprete())))
        self.assertEqual(self.respaldos(), [], "no había archivo: no hay nada que respaldar")

    def test_mezcla_sin_perder_otras_claves_y_respalda(self):
        original = {"theme": "dark", "permissions": {"allow": ["Bash(ls)"]}, "env": {"A": "1"}}
        self.escribir(original)
        self.assertEqual(self.correr("--si").returncode, 0)
        datos = self.leer()
        for clave, valor in original.items():
            self.assertEqual(datos[clave], valor)
        self.assertIn("statusLine", datos)
        copias = self.respaldos()
        self.assertEqual(len(copias), 1)
        self.assertEqual(json.loads((self.cfg / copias[0]).read_text(encoding="utf-8")), original)

    def test_es_idempotente(self):
        self.escribir({"theme": "dark"})
        self.correr("--si")
        despues = self.settings.read_bytes()
        r = self.correr("--si")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Sin cambios", r.stdout)
        self.assertEqual(self.settings.read_bytes(), despues)
        self.assertEqual(len(self.respaldos()), 1, "la segunda corrida no debe crear otro respaldo")

    def test_actualiza_la_ruta_de_una_instalacion_vieja(self):
        self.escribir({"statusLine": {"type": "command",
                                      "command": "python C:/viejo/DevSkills/motor/panel/statusline_limites.py",
                                      "refreshInterval": 30}})
        self.assertEqual(self.correr("--si").returncode, 0)
        sl = self.leer()["statusLine"]
        self.assertNotIn("viejo", sl["command"])
        self.assertEqual(sl["refreshInterval"], 30, "respeta el refresco que ya elegiste")

    def test_muestra_el_diff_y_sin_terminal_exige_si(self):
        self.escribir({"theme": "dark"})
        r = self.correr()
        self.assertEqual(r.returncode, 1)
        self.assertIn('+  "statusLine"', r.stdout)
        self.assertIn("--si", r.stderr)
        self.assertEqual(self.leer(), {"theme": "dark"})
        self.assertEqual(self.respaldos(), [])

    def test_no_pisa_una_status_line_ajena(self):
        ajena = {"statusLine": {"type": "command", "command": "mi-linea --x"}}
        self.escribir(ajena)
        r = self.correr("--si")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--envolver", r.stderr)
        self.assertEqual(self.leer(), ajena)
        self.assertEqual(self.respaldos(), [])

    def test_envolver_conserva_la_ajena_y_es_idempotente(self):
        self.escribir({"statusLine": {"type": "command", "command": "mi-linea --x", "padding": 2}})
        self.assertEqual(self.correr("--si", "--envolver", "mi-linea --x").returncode, 0)
        sl = self.leer()["statusLine"]
        self.assertEqual(sl["padding"], 2)
        self.assertEqual(enganchar.envuelto_de(sl), "mi-linea --x")
        self.assertIn("Sin cambios", self.correr("--si").stdout)

    def test_envolver_con_comillas_ida_y_vuelta(self):
        raro = "echo 'hola mundo' \"x\""
        cmd = enganchar.comando_statusline(raro)
        self.assertEqual(enganchar.envuelto_de({"command": cmd}), raro)

    def test_quitar_solo_quita_la_propia(self):
        self.escribir({"theme": "dark"})
        self.correr("--si")
        self.assertEqual(self.correr("--si", "--quitar").returncode, 0)
        self.assertEqual(self.leer(), {"theme": "dark"})

    def test_quitar_devuelve_la_ajena_envuelta(self):
        ajena = {"type": "command", "command": "mi-linea --x"}
        self.escribir({"statusLine": ajena})
        self.correr("--si", "--envolver", "mi-linea --x")
        self.assertEqual(self.correr("--si", "--quitar").returncode, 0)
        self.assertEqual(self.leer()["statusLine"], ajena)

    def test_quitar_no_toca_una_status_line_ajena(self):
        ajena = {"statusLine": {"type": "command", "command": "mi-linea"}}
        self.escribir(ajena)
        r = self.correr("--si", "--quitar")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.leer(), ajena)
        self.assertEqual(self.respaldos(), [])

    def test_json_invalido_no_se_toca(self):
        self.settings.write_text("{ no es json", encoding="utf-8")
        r = self.correr("--si")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{ no es json")
        self.assertEqual(self.respaldos(), [])

    def test_respeta_claude_config_dir(self):
        env = {**os.environ, "CLAUDE_CONFIG_DIR": str(self.cfg)}
        r = subprocess.run([sys.executable, str(MOTOR / "comun" / "enganchar.py"), "--si"], capture_output=True,
                           text=True, encoding="utf-8", env=env, stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("statusLine", self.leer())


class HooksViejos(Base):
    VIEJOS = {
        "SessionStart": [{"hooks": [{"type": "command", "command": "python C:/viejo/DevSkills/motor/graphify/sesion_inicio.py"}]}],
        "PreToolUse": [
            {"matcher": "Bash|Grep", "hooks": [
                {"type": "command", "command": "python C:\\viejo\\DevSkills\\motor\\graphify\\hook_guard.py search"},
                {"type": "command", "command": "mi-otro-hook"}]},
            {"matcher": "Read|Glob", "hooks": [{"type": "command", "command": "python /viejo/motor/graphify/hook_guard.py read"}]},
        ],
    }

    def test_con_el_plugin_los_viejos_se_quitan_y_los_ajenos_se_quedan(self):
        self.escribir({"enabledPlugins": {"devskills@marketplace": True}, "hooks": self.VIEJOS})
        r = self.correr("--si")
        self.assertEqual(r.returncode, 0, r.stderr)
        hooks = self.leer()["hooks"]
        self.assertEqual(list(hooks), ["PreToolUse"])
        self.assertEqual(hooks["PreToolUse"],
                         [{"matcher": "Bash|Grep", "hooks": [{"type": "command", "command": "mi-otro-hook"}]}])
        self.assertEqual(len(self.respaldos()), 1)

    def test_sin_el_plugin_solo_avisa(self):
        self.escribir({"hooks": self.VIEJOS})
        r = self.correr("--si")
        self.assertIn("pegados a mano", r.stdout)
        self.assertEqual(self.leer()["hooks"], self.VIEJOS)

    def test_limpiar_hooks_fuerza_la_limpieza_sin_plugin(self):
        self.escribir({"hooks": self.VIEJOS})
        self.correr("--si", "--limpiar-hooks")
        self.assertEqual(enganchar.hooks_encontrados(self.leer()), [])

    def test_plugin_deshabilitado_no_cuenta(self):
        self.escribir({"enabledPlugins": {"devskills@marketplace": False}, "hooks": self.VIEJOS})
        self.correr("--si")
        self.assertEqual(self.leer()["hooks"], self.VIEJOS)

    def test_plugin_detectado_por_plugins_instalados(self):
        (self.cfg / "plugins").mkdir()
        (self.cfg / "plugins" / "installed_plugins.json").write_text(
            json.dumps({"version": 2, "plugins": {"devskills@mercado": [{}]}}), encoding="utf-8")
        self.escribir({"hooks": self.VIEJOS})
        self.correr("--si")
        self.assertEqual(enganchar.hooks_encontrados(self.leer()), [])


class HooksGestionados(Base):
    def test_hooks_reemplaza_los_viejos_con_forma_sin_shell(self):
        self.escribir({"hooks": HooksViejos.VIEJOS})
        r = self.correr("--si", "--hooks")
        self.assertEqual(r.returncode, 0, r.stderr)
        hallados = enganchar.hooks_encontrados(self.leer())
        self.assertEqual(len(hallados), 3)
        for _, m in hallados:
            self.assertEqual(m["command"], enganchar.interprete())
            self.assertIsInstance(m["args"], list)
            self.assertNotIn("viejo", " ".join(m["args"]))
            self.assertTrue(Path(m["args"][0]).is_file(), m["args"][0])
        self.assertIn("mi-otro-hook", json.dumps(self.leer()))

    def test_hooks_es_idempotente(self):
        self.correr("--si", "--hooks")
        despues = self.settings.read_bytes()
        r = self.correr("--si", "--hooks")
        self.assertIn("Sin cambios", r.stdout)
        self.assertEqual(self.settings.read_bytes(), despues)

    def test_hooks_con_el_plugin_se_rechaza_por_duplicado(self):
        self.escribir({"enabledPlugins": {"devskills@m": True}})
        r = self.correr("--si", "--hooks")
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("hooks", self.leer())

    def test_quitar_saca_los_gestionados_pero_no_los_pegados_a_mano(self):
        self.correr("--si", "--hooks")
        datos = self.leer()
        datos["hooks"].setdefault("SessionStart", []).append(HooksViejos.VIEJOS["SessionStart"][0])
        self.escribir(datos)
        self.correr("--si", "--quitar")
        restantes = enganchar.hooks_encontrados(self.leer())
        self.assertEqual(len(restantes), 1)
        self.assertNotIn("args", restantes[0][1])


@unittest.skipUnless(shutil.which("bash"), "hace falta bash para correr el comando de los hooks")
class HooksDelPlugin(unittest.TestCase):
    """Los comandos de hooks/hooks.json deben ser inocuos sin grafo, desactivables y no fallar sin Python."""

    @classmethod
    def setUpClass(cls):
        cls.hooks = json.loads((RAIZ / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        pre = cls.hooks["PreToolUse"]
        cls.comandos = {
            "sesion": cls.hooks["SessionStart"][0]["hooks"][0]["command"],
            "buscar": next(g for g in pre if g.get("matcher") == "Bash|Grep")["hooks"][0]["command"],
            "leer": next(g for g in pre if g.get("matcher") == "Read|Glob")["hooks"][0]["command"],
        }

    def correr(self, nombre, proyecto, **extra):
        comando = self.comandos[nombre].replace("${CLAUDE_PLUGIN_ROOT}", RAIZ.as_posix())
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(proyecto), **extra}
        return subprocess.run(["bash", "-c", comando], input="{}", capture_output=True, text=True,
                              encoding="utf-8", env=env, timeout=60)

    @staticmethod
    def con_grafo(carpeta):
        salida = Path(carpeta) / "graphify-out"
        salida.mkdir()
        (salida / "GRAPH_REPORT.md").write_text("## Summary\n- 10 nodes\n", encoding="utf-8")
        (salida / "graph.json").write_text("{}", encoding="utf-8")

    def test_sin_grafo_no_hace_nada_y_sale_con_cero(self):
        with tempfile.TemporaryDirectory() as t:
            for nombre in self.comandos:
                r = self.correr(nombre, t)
                self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""), nombre)

    def test_con_grafo_la_sesion_inyecta_contexto_y_se_puede_desactivar(self):
        with tempfile.TemporaryDirectory() as t:
            self.con_grafo(t)
            r = self.correr("sesion", t)
            self.assertEqual(r.returncode, 0)
            self.assertIn("additionalContext", r.stdout)
            self.assertEqual(self.correr("sesion", t, GRAPHIFY_SESION="0").stdout, "")
            for nombre in ("buscar", "leer"):
                self.assertEqual(self.correr(nombre, t, GRAPHIFY_GUARDIA="0").returncode, 0)

    def test_sin_interprete_de_python_sale_con_cero(self):
        with tempfile.TemporaryDirectory() as t:
            self.con_grafo(t)
            vacio = Path(t) / "vacio"
            vacio.mkdir()
            for nombre, comando in self.comandos.items():
                comando = comando.replace("${CLAUDE_PLUGIN_ROOT}", RAIZ.as_posix())
                r = subprocess.run([shutil.which("bash"), "-c", comando], input="{}", capture_output=True,
                                   text=True, env={"PATH": str(vacio), "CLAUDE_PROJECT_DIR": t}, timeout=60)
                self.assertEqual(r.returncode, 0, nombre)

    def test_los_comandos_no_dependen_de_rutas_personales(self):
        texto = json.dumps(self.hooks)
        for personal in ("Users", "Documents", "Proyectos", "/home/"):
            self.assertNotIn(personal, texto)


if __name__ == "__main__":
    unittest.main()
