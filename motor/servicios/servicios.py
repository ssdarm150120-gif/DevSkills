"""Lanzador de servicios locales (multiplataforma) a partir del registro central proyectos.json.

  python servicios.py listar                              Lista proyectos y servicios del registro
  python servicios.py levantar <proyecto|servicio>        Levanta todos los servicios del proyecto, o uno solo
  python servicios.py apagar <proyecto|servicio>          (también: detener) Apaga por puerto o con docker compose stop
  ... --simular                                           Muestra lo que haría, sin ejecutar nada
  ... --registro ARCHIVO                                  Otro proyectos.json (por omisión <datos>/proyectos.json)

Cada servicio corre en su PROPIA ventana (Windows: consola nueva) o proceso en segundo plano (macOS y Linux: con su
log en <datos>/servicios/logs). En ambos casos el pid del envoltorio queda en <datos>/servicios/pids y `apagar` lo cierra
con su árbol, tras verificar que sigue siendo un envoltorio `servicios.py _ejecutar` (no un pid reciclado). Los comandos se arman con campos estructurados del
registro, sin shell y sin texto libre; solo se aceptan estos tipos de arranque (lista blanca):

  dotnet, npm, django-devskills, python-modulo, docker-compose

Validaciones: script de npm, módulo de Python, argumentos y nombres de variables de entorno con patrones estrictos;
las carpetas del arranque son relativas a la del proyecto, sin ``..`` y sin rutas absolutas. Solo biblioteca estándar.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import rutas  # noqa: E402

TIPOS_PERMITIDOS = ("dotnet", "npm", "django-devskills", "python-modulo", "docker-compose")
RE_ENTORNO = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
RE_SCRIPT_NPM = re.compile(r"[A-Za-z0-9:._-]+")
RE_MODULO = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
RE_ARGUMENTO = re.compile(r"[A-Za-z0-9_.:=-]+")
SISTEMAS = ("windows", "macos", "linux")


class ErrorServicios(Exception):
    """Entrada no permitida o registro inválido (el mensaje se muestra tal cual al usuario)."""


# ---------------------------------------------------------------- validaciones

def sistema() -> str:
    if os.name == "nt":
        return "windows"
    return "macos" if sys.platform == "darwin" else "linux"


def validar(valor, patron: re.Pattern, que: str) -> str:
    """El valor completo debe cumplir el patrón (se rechazan saltos de línea y NUL)."""
    if not isinstance(valor, str) or not patron.fullmatch(valor):
        raise ErrorServicios(f"Valor no permitido en el registro ({que}): {valor}")
    return valor


def ruta_segura(base, relativa) -> Path:
    """Une `base` con una carpeta RELATIVA del registro. Rechaza '..', rutas absolutas, unidades y UNC."""
    base = Path(base)
    if relativa is None or str(relativa).strip() in ("", "."):
        return base
    texto = str(relativa)
    normal = texto.replace("\\", "/")
    if ("\x00" in texto or ".." in normal or normal.startswith("/") or re.match(r"^[A-Za-z]:", normal)
            or Path(normal).is_absolute()):
        raise ErrorServicios(f"Carpeta relativa no permitida: {texto}")
    return base.joinpath(*[p for p in normal.split("/") if p not in ("", ".")])


def _expandir(carpeta) -> str:
    if isinstance(carpeta, str) and (carpeta == "~" or carpeta.startswith(("~/", "~\\"))):
        return os.path.expanduser(carpeta)
    return carpeta


def cargar_registro(archivo: Path) -> dict:
    try:
        datos = json.loads(Path(archivo).read_text(encoding="utf-8-sig"))
    except OSError:
        raise ErrorServicios(f"No encontré el registro {archivo}. Crea uno con `devskills motor iniciar`.")
    except ValueError as e:
        raise ErrorServicios(f"El registro {archivo} no es un JSON válido: {e}")
    if not isinstance(datos, dict) or not isinstance(datos.get("proyectos"), list):
        raise ErrorServicios("El registro debe tener una lista 'proyectos'.")
    return datos


def _servicios(p: dict) -> list:
    return [s for s in (p.get("servicios") or []) if s]


def resolver_objetivo(datos: dict, objetivo: str):
    """Resuelve el objetivo contra la lista blanca del registro (id de proyecto o de servicio).
    Devuelve (lista de (proyecto, servicio), proyecto_sin_servicios_o_None)."""
    pares, sin_servicios = [], None
    for p in datos["proyectos"]:
        if not isinstance(p, dict):
            continue
        if p.get("id") == objetivo:
            lista = _servicios(p)
            if not lista:
                sin_servicios = p
            pares += [(p, s) for s in lista]
        else:
            pares += [(p, s) for s in _servicios(p) if s.get("id") == objetivo]
    return pares, sin_servicios


def _carpeta_proyecto(p: dict) -> Path:
    carpeta = _expandir(p.get("carpeta"))
    if not isinstance(carpeta, str) or not carpeta or not Path(carpeta).is_absolute():
        raise ErrorServicios(f"El proyecto {p.get('id')} necesita una 'carpeta' absoluta (o '~/...').")
    return Path(carpeta)


def _puertos(s: dict) -> list:
    try:
        return [int(x) for x in (s.get("puertos") or [])]
    except (TypeError, ValueError):
        raise ErrorServicios(f"Puertos inválidos en {s.get('id')}")


# ---------------------------------------------------------------- plan de arranque

def _programa(nombre: str) -> str:
    """Ruta del ejecutable si está en el PATH (en Windows npm es npm.cmd); si no, el nombre tal cual."""
    return shutil.which(nombre) or nombre


def _entorno_del_servicio(a: dict) -> dict:
    env = {}
    for nombre, valor in (a.get("entorno") or {}).items():
        validar(nombre, RE_ENTORNO, "variable de entorno")
        valor = str(valor)
        if "\x00" in valor:
            raise ErrorServicios(f"Valor no permitido en el registro (variable {nombre})")
        env[nombre] = valor
    return env


def _python_de_venv(venv: Path, so: str) -> Path:
    return venv / ("Scripts/python.exe" if so == "windows" else "bin/python")


def plan_arranque(p: dict, s: dict, so: str | None = None) -> dict | None:
    """Plan estructurado de arranque: {"cwd", "env", "pasos": [{"argv": [...]} | {"django": {...}}], "venv"}.
    Devuelve None si falta algo previo (se avisa con `aviso`). Lanza ErrorServicios ante cualquier valor no permitido."""
    so = so or sistema()
    a = s.get("arranque") or {}
    tipo = str(a.get("tipo"))
    if tipo not in TIPOS_PERMITIDOS:
        raise ErrorServicios(f"Tipo de arranque no permitido: {tipo}")
    directorio = ruta_segura(_carpeta_proyecto(p), a.get("carpeta"))
    env = _entorno_del_servicio(a)
    plan = {"cwd": str(directorio), "env": env, "pasos": [], "tipo": tipo, "aviso": None}
    venv = None
    if a.get("venv"):
        venv = ruta_segura(_carpeta_proyecto(p), a.get("venv"))
        carpeta_bin = venv / ("Scripts" if so == "windows" else "bin")
        env["VIRTUAL_ENV"] = str(venv)
        env["PATH_ANTEPUESTO"] = str(carpeta_bin)  # el ejecutor lo antepone al PATH real
    if tipo == "dotnet":
        plan["pasos"].append({"argv": [_programa("dotnet"), "run"]})
    elif tipo == "npm":
        script = validar(a.get("script"), RE_SCRIPT_NPM, "script de npm")
        if a.get("instalar_si_falta"):
            marca = ruta_segura(directorio, a["instalar_si_falta"])
            if not marca.exists():
                plan["pasos"].append({"argv": [_programa("npm"), "ci"]})
        plan["pasos"].append({"argv": [_programa("npm"), "run", script]})
    elif tipo == "django-devskills":
        puertos = _puertos(s)
        if not puertos:
            raise ErrorServicios(f"El servicio {s.get('id')} no tiene puertos")
        plan["pasos"].append({"django": {"codigo": str(directorio), "puerto": puertos[0]}})
    elif tipo == "python-modulo":
        modulo = validar(a.get("modulo"), RE_MODULO, "módulo de Python")
        argumentos = [validar(str(x), RE_ARGUMENTO, "argumento") for x in (a.get("argumentos") or []) if x]
        python = str(_python_de_venv(venv, so)) if venv else ("python" if so == "windows" else "python3")
        plan["pasos"].append({"argv": [python if venv else _programa(python), "-m", modulo, *argumentos]})
    elif tipo == "docker-compose":
        if a.get("requiere_archivo") and not ruta_segura(directorio, a["requiere_archivo"]).exists():
            plan["aviso"] = (f"Falta {a['requiere_archivo']} en {directorio}. Créalo a partir de la plantilla del "
                             "proyecto antes de levantarlo.")
            return plan
        argv = [_programa("docker"), "compose", "up", "-d"] + (["--build"] if a.get("construir") else [])
        plan["pasos"].append({"argv": argv})
    return plan


def describir(plan: dict) -> str:
    partes = [f"cd {plan['cwd']}"]
    for k, v in plan["env"].items():
        if k == "PATH_ANTEPUESTO":
            partes.append(f"PATH={v}{os.pathsep}$PATH")
        else:
            partes.append(f"{k}={v}")
    for paso in plan["pasos"]:
        if "argv" in paso:
            partes.append(" ".join(paso["argv"]))
        else:
            d = paso["django"]
            partes.append(f"django-devskills (venv, PostgreSQL embebido, migrate, runserver 127.0.0.1:{d['puerto']})")
    return "; ".join(partes)


# ---------------------------------------------------------------- puertos y procesos

def puerto_ocupado(puerto: int) -> bool:
    """Intenta conectar a loopback (IPv4 e IPv6): sin netstat ni lsof, igual en los tres sistemas."""
    for familia, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(familia, socket.SOCK_STREAM) as c:
                c.settimeout(0.3)
                c.connect((host, puerto))
                return True
        except OSError:
            continue
    return False


def _ejecutar_texto(argv: list, timeout: float = 10) -> str:
    try:
        r = subprocess.run(argv, capture_output=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.decode("utf-8", errors="replace")


def pids_en_puerto(puerto: int, so: str | None = None, ejecutar=_ejecutar_texto) -> list[int]:
    """PIDs que escuchan en el puerto TCP. Sin shell: netstat -ano (Windows), lsof (macOS y Linux) o ss (Linux)."""
    so = so or sistema()
    pids: set[int] = set()
    if so == "windows":
        for linea in ejecutar(["netstat", "-ano", "-p", "TCP"]).splitlines():
            c = linea.split()
            # TCP  <local>  <remota 0.0.0.0:0 | [::]:0>  <estado>  <pid>: el estado cambia con el idioma
            if len(c) >= 5 and c[0].upper() == "TCP" and c[2] in ("0.0.0.0:0", "[::]:0"):
                if c[1].rsplit(":", 1)[-1] == str(puerto) and c[-1].isdigit():
                    pids.add(int(c[-1]))
    else:
        salida = ejecutar(["lsof", "-nP", f"-iTCP:{int(puerto)}", "-sTCP:LISTEN", "-t"]) if shutil.which("lsof") else ""
        pids.update(int(x) for x in salida.split() if x.isdigit())
        if not pids and so == "linux" and shutil.which("ss"):
            for linea in ejecutar(["ss", "-H", "-ltnp", f"sport = :{int(puerto)}"]).splitlines():
                pids.update(int(m) for m in re.findall(r"pid=(\d+)", linea))
    return sorted(pids)


def _matar(pid: int, so: str) -> None:
    if pid <= 1 or pid == os.getpid():
        return
    if so == "windows":
        subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    for _ in range(20):
        time.sleep(0.1)
        try:
            os.kill(pid, 0)
        except OSError:
            return
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _nombre_archivo(servicio_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", servicio_id)


def _archivo_pid(servicio_id: str) -> Path:
    return rutas.servicios_pids() / f"{_nombre_archivo(servicio_id)}.pid"


def _archivo_apagado(servicio_id: str) -> Path:
    """Marcador de apagado intencional: lo crea `apagar` y lo consume el envoltorio al terminar el servicio."""
    return rutas.servicios_pids() / f"{_nombre_archivo(servicio_id)}.apagado"


def _borrar(archivo: Path) -> None:
    try:
        archivo.unlink()
    except OSError:
        pass


def marcar_apagado(servicio_id: str) -> None:
    try:
        rutas.servicios_pids().mkdir(parents=True, exist_ok=True)
        _archivo_apagado(servicio_id).write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass


def apagado_intencional(servicio_id: str) -> bool:
    """True si `apagar` marcó este servicio; el marcador se consume (se borra) al consultarlo."""
    archivo = _archivo_apagado(servicio_id)
    existe = archivo.exists()
    _borrar(archivo)
    return existe


def _linea_de_comandos(pid: int, so: str, ejecutar=_ejecutar_texto) -> str:
    """Línea de comandos del proceso (vacía si no existe o no se pudo leer). Sin shell: PowerShell/CIM en
    Windows (wmic ya no viene en Windows 11) y `ps` en macOS y Linux."""
    if so == "windows":
        return ejecutar(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                         f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"]).strip()
    return ejecutar(["ps", "-o", "args=", "-p", str(int(pid))]).strip()


def es_envoltorio(pid: int, so: str, ejecutar=_ejecutar_texto) -> bool:
    """True solo si el pid sigue siendo un envoltorio `servicios.py _ejecutar <plan>` del lanzador. Protege contra un
    pid reciclado por otro programa: si no se puede comprobar, se considera ajeno y NO se mata."""
    linea = _linea_de_comandos(pid, so, ejecutar).lower()
    return "servicios.py" in linea and re.search(r"\b_ejecutar\b", linea) is not None


def _cerrar_envoltorio_registrado(servicio_id: str, so: str, ejecutar=_ejecutar_texto, matar=None, matar_grupo=None) -> bool:
    """Cierra el envoltorio de la ventana del arranque anterior junto con todo su árbol (el servicio incluido) y
    borra el pid registrado. Windows: `taskkill /T /F`. macOS y Linux: el envoltorio se lanzó con start_new_session,
    así que su pid es el de un grupo entero (envoltorio, npm, node...) y se apaga el grupo. True si lo cerró."""
    archivo = _archivo_pid(servicio_id)
    try:
        pid = int(archivo.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        _borrar(archivo)
        return False
    _borrar(archivo)
    if pid <= 1 or pid == os.getpid() or not es_envoltorio(pid, so, ejecutar):
        return False
    if so == "windows":
        (matar or _matar)(pid, so)
        return True
    try:
        (matar_grupo or os.killpg)(pid, signal.SIGTERM)
    except OSError:
        return False
    return True


# ---------------------------------------------------------------- ejecución

def _entorno_real(env: dict) -> dict:
    e = dict(os.environ)
    e.update({k: v for k, v in env.items() if k != "PATH_ANTEPUESTO"})
    if "PATH_ANTEPUESTO" in env:
        e["PATH"] = env["PATH_ANTEPUESTO"] + os.pathsep + e.get("PATH", "")
    return e


def _titulo(texto: str) -> None:
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(texto)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    else:
        print(f"== {texto} ==", flush=True)


def correr_django(codigo: Path, puerto: int) -> int:
    """Proyecto DevSkills (Django) sin Docker: venv junto a codigo/, PostgreSQL embebido, migraciones y runserver.
    Porta la lógica de django.ps1."""
    so = sistema()
    venv = codigo.parent / ".venv"
    python = _python_de_venv(venv, so)
    if not python.exists():
        print("Primera vez: creando el entorno virtual e instalando dependencias...", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(venv)], cwd=str(codigo), check=True)
        subprocess.run([str(python), "-m", "pip", "install", "-r", "requirements-dev.txt"], cwd=str(codigo), check=True)
    env = _entorno_real({"VIRTUAL_ENV": str(venv), "PATH_ANTEPUESTO": str(python.parent)})
    print("Arrancando PostgreSQL embebido...", flush=True)
    r = subprocess.run([str(python), "-m", "herramientas.base_local"], cwd=str(codigo), env=env,
                       capture_output=True, text=True)
    lineas = [x.strip() for x in r.stdout.splitlines() if x.strip()]
    url = lineas[-1] if lineas else ""
    if r.returncode != 0 or not url.startswith("postgres"):
        print(r.stderr.strip())
        print(f"base_local no devolvió una DATABASE_URL: {url}")
        return 1
    env["DATABASE_URL"] = url
    subprocess.run([str(python), "manage.py", "migrate"], cwd=str(codigo), env=env, check=True)
    return subprocess.run([str(python), "manage.py", "runserver", f"127.0.0.1:{int(puerto)}"],
                          cwd=str(codigo), env=env).returncode


def ejecutar_plan(archivo_plan: Path) -> int:
    """Corre un plan guardado (lo usa el propio lanzador dentro de la ventana o el proceso del servicio)."""
    plan = json.loads(Path(archivo_plan).read_text(encoding="utf-8"))
    try:
        Path(archivo_plan).unlink()
    except OSError:
        pass
    _titulo(plan.get("titulo", "servicio"))
    env = _entorno_real(plan["env"])
    codigo = 0
    for paso in plan["pasos"]:
        if "django" in paso:
            codigo = correr_django(Path(paso["django"]["codigo"]), paso["django"]["puerto"])
        else:
            try:
                codigo = subprocess.run(paso["argv"], cwd=plan["cwd"], env=env).returncode
            except OSError as e:
                print(f"No pude ejecutar {paso['argv'][0]}: {e}")
                codigo = 127
        if codigo != 0:
            break
    sid = plan.get("servicio_id")
    intencional = apagado_intencional(sid) if sid else False  # lo apagó `apagar`: no hay nada que leer
    if sid:
        _limpiar_pid_propio(sid)
    if sistema() == "windows" and not intencional:  # se cayó solo: la consola se queda para leer el error
        try:
            input("\nEl servicio terminó. Presiona Enter para cerrar esta ventana...")
        except (EOFError, RuntimeError, OSError):  # sin consola (pythonw) o sin entrada: no hay a quién esperar
            pass
    return codigo


def _limpiar_pid_propio(servicio_id: str) -> None:
    """Al terminar por su cuenta, el envoltorio borra su pid registrado (si todavía es el suyo)."""
    try:
        pid = int(_archivo_pid(servicio_id).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return
    if pid in (os.getpid(), os.getppid()):  # getppid: en Windows el lanzador del venv es el padre del intérprete real
        _borrar(_archivo_pid(servicio_id))


def _python_del_envoltorio(so: str) -> str:
    """Intérprete del envoltorio. En Windows el panel corre con pythonw.exe (sin consola): el envoltorio necesita
    python.exe para tener su ventana y poder esperar el Enter."""
    exe = Path(sys.executable)
    if so == "windows" and exe.name.lower() == "pythonw.exe" and exe.with_name("python.exe").exists():
        return str(exe.with_name("python.exe"))
    return str(exe)


def lanzar(plan: dict, servicio_id: str, titulo: str, so: str | None = None) -> int:
    """Abre el servicio en su propia ventana (Windows) o como proceso en segundo plano (macOS y Linux). Devuelve el
    pid del envoltorio, que queda registrado en la carpeta de pids para que `apagar` lo cierre con su árbol."""
    so = so or sistema()
    carpeta_planes = rutas.servicios_dir() / "planes"
    carpeta_planes.mkdir(parents=True, exist_ok=True)
    rutas.servicios_pids().mkdir(parents=True, exist_ok=True)
    _borrar(_archivo_apagado(servicio_id))  # un marcador viejo no debe silenciar la pausa de este arranque
    archivo = carpeta_planes / f"{uuid.uuid4().hex}.json"
    archivo.write_text(json.dumps({**plan, "titulo": titulo, "servicio_id": servicio_id}), encoding="utf-8")
    rutas.restringir(archivo)
    argv = [_python_del_envoltorio(so), str(Path(__file__).resolve()), "_ejecutar", str(archivo)]
    if so == "windows":
        proceso = subprocess.Popen(argv, cwd=plan["cwd"] if Path(plan["cwd"]).is_dir() else None,
                                   creationflags=subprocess.CREATE_NEW_CONSOLE, close_fds=True)  # type: ignore[attr-defined]
    else:
        rutas.servicios_logs().mkdir(parents=True, exist_ok=True)
        log = open(rutas.servicios_logs() / f"{_nombre_archivo(servicio_id)}.log", "ab")
        try:
            proceso = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True, close_fds=True)
        finally:
            log.close()
    _archivo_pid(servicio_id).write_text(str(proceso.pid), encoding="utf-8")
    return proceso.pid


# ---------------------------------------------------------------- acciones

def listar(datos: dict) -> None:
    print("Proyectos y servicios del registro:")
    for p in datos["proyectos"]:
        print(f"  {p.get('id', ''):<20} {p.get('nombre', '')}")
        for s in _servicios(p):
            puertos = ", :".join(str(x) for x in (s.get("puertos") or []))
            print(f"      {s.get('id', ''):<24} :{puertos}  {s.get('url', '')}")
    print("Uso: levantar <proyecto|servicio>   apagar <proyecto|servicio>")


def levantar(datos: dict, objetivo: str, simular: bool, so: str | None = None) -> int:
    so = so or sistema()
    pares, sin_servicios = resolver_objetivo(datos, objetivo)
    if sin_servicios:
        print(f"{sin_servicios.get('nombre', objetivo)} no tiene servicios que levantar "
              "(se registra solo para ver sus agentes).")
        return 0
    if not pares:
        return _no_existe(datos, objetivo)
    for p, s in pares:
        puertos = _puertos(s)
        sid = str(s.get("id"))
        ocupados = [x for x in puertos if puerto_ocupado(x)] if not simular else []
        if ocupados:
            print(f"{sid} ya parece estar corriendo o hay otro proceso en sus puertos "
                  f"({', '.join(map(str, ocupados))}). Usa: apagar {sid}")
            continue
        plan = plan_arranque(p, s, so)
        if plan["aviso"]:
            print(plan["aviso"])
            continue
        titulo = f"{p.get('id')} · {s.get('nombre', sid)} :{','.join(map(str, puertos))}"
        if plan["tipo"] == "docker-compose":
            if simular:
                print(f"Simulación (docker compose): {describir(plan)}")
                continue
            print(f"Levantando {sid} con docker compose...")
            codigo = subprocess.run(plan["pasos"][0]["argv"], cwd=plan["cwd"], env=_entorno_real(plan["env"])).returncode
            if codigo != 0:
                return codigo
            continue
        if simular:
            donde = "ventana nueva" if so == "windows" else "proceso en segundo plano"
            print(f"Simulación ({donde}): {describir(plan)}")
            continue
        pid = lanzar(plan, sid, titulo, so)
        extra = "en una ventana nueva" if so == "windows" else f"en segundo plano (pid {pid}, log en {rutas.servicios_logs()})"
        print(f"Levantando {sid} {extra}. Abre {s.get('url', '')} cuando termine de arrancar.")
    return 0


def apagar(datos: dict, objetivo: str, simular: bool, so: str | None = None) -> int:
    so = so or sistema()
    pares, sin_servicios = resolver_objetivo(datos, objetivo)
    if sin_servicios:
        print(f"{sin_servicios.get('nombre', objetivo)} no tiene servicios que levantar "
              "(se registra solo para ver sus agentes).")
        return 0
    if not pares:
        return _no_existe(datos, objetivo)
    for p, s in pares:
        puertos = _puertos(s)
        sid = str(s.get("id"))
        tipo = str((s.get("arranque") or {}).get("tipo"))
        if tipo not in TIPOS_PERMITIDOS:
            raise ErrorServicios(f"Tipo de arranque no permitido: {tipo}")
        if simular:
            print(f"Simulación: apagaría {sid} (puertos {', '.join(map(str, puertos))}, tipo {tipo})")
            continue
        directorio = ruta_segura(_carpeta_proyecto(p), (s.get("arranque") or {}).get("carpeta"))
        if tipo == "docker-compose":
            subprocess.run([_programa("docker"), "compose", "stop"], cwd=str(directorio))
        else:
            marcar_apagado(sid)  # antes de matar: un envoltorio que sobreviva sabrá que el apagado fue intencional
            if _cerrar_envoltorio_registrado(sid, so):
                _borrar(_archivo_apagado(sid))  # el envoltorio ya no existe: nadie consumirá el marcador
                print(f"Cerrada la ventana del arranque anterior de {sid}")
            for pt in puertos:
                for pid in pids_en_puerto(pt, so):
                    _matar(pid, so)
                    print(f"Detenido el proceso {pid} (puerto {pt})")
            if tipo == "django-devskills":
                py = _python_de_venv(directorio.parent / ".venv", so)
                if py.exists():
                    subprocess.run([str(py), "-m", "herramientas.base_local", "--detener"], cwd=str(directorio))
        print(f"{sid} detenido.")
    return 0


def _no_existe(datos: dict, objetivo: str) -> int:
    ids = []
    for p in datos["proyectos"]:
        ids.append(str(p.get("id")))
        ids += [str(s.get("id")) for s in _servicios(p)]
    print(f"No existe '{objetivo}' en el registro. Opciones: {', '.join(ids)}", file=sys.stderr)
    return 2


def _opcion(argv: list, nombre: str):
    if nombre in argv:
        i = argv.index(nombre)
        if i + 1 >= len(argv):
            raise ErrorServicios(f"Falta el valor de {nombre}")
        valor = argv[i + 1]
        del argv[i:i + 2]
        return valor
    return None


def main(argv: list[str]) -> int:
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    argv = list(argv)
    if argv[:1] == ["_ejecutar"] and len(argv) == 2:  # interno: lo invoca lanzar()
        return ejecutar_plan(Path(argv[1]))
    try:
        registro = _opcion(argv, "--registro")
        so = _opcion(argv, "--so")
        simular = "--simular" in argv
        argv = [a for a in argv if a != "--simular"]
        if so and (so not in SISTEMAS or not simular):
            raise ErrorServicios("--so solo acepta windows, macos o linux y solo junto con --simular.")
        accion = argv[0] if argv and argv[0] in ("listar", "levantar", "apagar", "detener") else "levantar"
        resto = argv[1:] if argv and argv[0] == accion else argv
        if accion == "levantar" and len(resto) == 2 and resto[1] in ("apagar", "detener"):
            accion, resto = "apagar", resto[:1]  # compatibilidad: `levantar <x> apagar`
        if len(resto) > 1 or (resto and resto[0].startswith("-")):
            raise ErrorServicios(f"Argumentos no reconocidos: {' '.join(resto)}")
        objetivo = resto[0] if resto else None
        datos = cargar_registro(Path(registro) if registro else rutas.registro())
        if accion == "listar" or not objetivo:
            if accion in ("apagar", "detener"):
                raise ErrorServicios("Indica qué apagar: apagar <proyecto|servicio>")
            listar(datos)
            return 0
        if accion == "levantar":
            return levantar(datos, objetivo, simular, so)
        return apagar(datos, objetivo, simular, so)
    except ErrorServicios as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
