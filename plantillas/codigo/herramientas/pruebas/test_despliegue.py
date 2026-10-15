"""Los artefactos de despliegue cumplen D.6.1 a D.6.3: Dockerfile, nginx, Compose y entorno.

Las comprobaciones estaticas leen los archivos; las de Compose le piden a `docker compose config` el
resultado YA resuelto (anclas, variables y superposicion de archivos), asi que se omiten si no hay
Docker en la maquina (en el CI de GitHub si lo hay).
"""

import functools
import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path
from typing import Any, NoReturn

import pytest
import yaml
from django.core.exceptions import ImproperlyConfigured

from configuracion import entorno

CODIGO = Path(__file__).resolve().parents[2]
RAIZ = CODIGO.parent
DESPLIEGUE = CODIGO / "despliegue"
NGINX = DESPLIEGUE / "nginx" / "templates" / "default.conf.template"
DOCKERFILE = DESPLIEGUE / "Dockerfile"
ENV_EJEMPLO = DESPLIEGUE / ".env.ejemplo"
CI = RAIZ / ".github" / "workflows" / "ci.yml"
DESPLEGAR = RAIZ / ".github" / "workflows" / "desplegar-pruebas.yml"
COMPOSE_PRUEBAS = DESPLIEGUE / "docker-compose.pruebas.yml"
GENERAR_CERTIFICADO = DESPLIEGUE / "nginx" / "generar_certificado.sh"

SECRETOS_DE_EJEMPLO = (
    "SECRET_KEY",
    "APP_LLAVE_HUELLA",
    "APP_LLAVE_SEGUNDO_FACTOR",
    "POSTGRES_ADMIN_PASSWORD",
    "APP_MIGRACIONES_PASSWORD",
    "APP_WEB_PASSWORD",
    "REDIS_PASSWORD",
)


def _directivas_de_nginx() -> list[str]:
    """Las lineas de la plantilla sin comentarios ni espacios sobrantes."""
    lineas = (
        line.split("#", 1)[0].strip() for line in NGINX.read_text(encoding="utf-8").splitlines()
    )
    return [" ".join(linea.split()) for linea in lineas if linea]


def _variables(ruta: Path) -> dict[str, str]:
    """`CLAVE=valor` de un archivo de entorno (ignora comentarios y lineas vacias)."""
    resultado: dict[str, str] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if linea.strip() and not linea.lstrip().startswith("#"):
            clave, _, valor = linea.partition("=")
            resultado[clave.strip()] = valor.strip()
    return resultado


# --- nginx (D.6.1): TLS, proxy y UN solo responsable de CSP y HSTS -----------------------------


def test_nginx_no_agrega_csp_ni_hsts_porque_los_emite_django() -> None:
    directivas = _directivas_de_nginx()
    agregados = [d for d in directivas if d.startswith(("add_header", "more_set_headers"))]
    assert agregados == [], "nginx no debe emitir encabezados de seguridad: los emite Django"
    texto = " ".join(directivas).lower()
    assert "content-security-policy" not in texto
    assert "strict-transport-security" not in texto


def test_nginx_fija_x_forwarded_proto_y_no_reenvia_el_del_cliente() -> None:
    directivas = _directivas_de_nginx()
    assert "proxy_set_header X-Forwarded-Proto https;" in directivas
    assert not any("$http_x_forwarded" in d for d in directivas)
    assert not any("$proxy_add_x_forwarded_for" in d for d in directivas)
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in directivas  # sobrescribe


def test_nginx_reenvia_el_host_con_puerto_para_que_django_verifique_el_origen_csrf() -> None:
    # Con `$host` (sin puerto) el `Origin` https://localhost:8443 nunca coincide con el host de la
    # peticion y Django rechaza con 403 todo POST en un puerto distinto de 443.
    directivas = _directivas_de_nginx()
    assert "proxy_set_header Host $http_host;" in directivas
    assert "proxy_set_header Host $host;" not in directivas


def test_nginx_termina_tls_moderno_y_limita_la_carga_a_10_mb() -> None:
    directivas = _directivas_de_nginx()
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in directivas
    assert "client_max_body_size 10m;" in directivas
    assert "server_tokens off;" in directivas
    assert any(d.startswith("listen 8443 ssl") for d in directivas)


def test_nginx_solo_admite_cifrados_ecdhe_con_aead_en_tls_12() -> None:
    """perfil Mozilla intermediate: solo ECDHE con GCM o CHACHA20 (sin CBC, RSA ni DHE)."""
    cifrados = [d for d in _directivas_de_nginx() if d.startswith("ssl_ciphers ")]
    assert len(cifrados) == 1
    lista = cifrados[0].removeprefix("ssl_ciphers ").removesuffix(";").split(":")
    assert lista, cifrados
    for cifrado in lista:
        assert cifrado.startswith("ECDHE-"), cifrado
        assert re.search(r"-(AES(128|256)-GCM-SHA(256|384)|CHACHA20-POLY1305)$", cifrado), cifrado
    assert not any(re.search(r"CBC|-SHA$|^DHE|^AES|^RSA", c) for c in lista)
    # A nivel `http` (fuera de los `server`) para que lo herede tambien el `server` por defecto.
    texto = NGINX.read_text(encoding="utf-8")
    assert texto.index("ssl_ciphers") < texto.index("server {")


def test_nginx_redirige_http_a_un_destino_fijo_y_corta_los_host_desconocidos() -> None:
    texto = "\n".join(_directivas_de_nginx())
    assert (
        "return 301 https://${NGINX_NOMBRE_PUBLICO}${NGINX_SUFIJO_PUERTO_HTTPS}$request_uri;"
        in texto
    )
    assert "https://$host" not in texto  # el destino nunca sale del Host de la peticion
    assert "return 444;" in texto
    assert "default_server" in texto


def test_nginx_solo_sustituye_variables_propias_de_la_plantilla() -> None:
    usadas = set(re.findall(r"\$\{(\w+)\}", NGINX.read_text(encoding="utf-8")))
    compose = (DESPLIEGUE / "docker-compose.yml").read_text(encoding="utf-8")
    assert usadas == {
        "NGINX_NOMBRE_PUBLICO",
        "NGINX_SUFIJO_PUERTO_HTTPS",
        "NGINX_LIMITE_INGRESO",
        "NGINX_RAFAGA_INGRESO",
    }
    for variable in usadas:
        assert f"{variable}:" in compose  # el Compose las define
    assert "NGINX_ENVSUBST_FILTER: ^NGINX_" in compose  # y no toca $host ni $remote_addr


# --- Dockerfile (D.6.1) ------------------------------------------------------------------------


def test_el_dockerfile_es_multi_stage_python_312_slim_y_fija_el_digest() -> None:
    lineas = [
        linea
        for linea in DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if linea.startswith("FROM ")
    ]
    assert len(lineas) >= 2
    for linea in lineas:
        assert re.match(r"FROM python:3\.12-slim-\w+@sha256:[0-9a-f]{64} AS \w+$", linea), linea


def test_el_dockerfile_corre_como_usuario_sin_privilegios() -> None:
    texto = DOCKERFILE.read_text(encoding="utf-8")
    usuarios = re.findall(r"^USER (\S+)$", texto, re.MULTILINE)
    assert usuarios, "falta USER"
    ultimo = usuarios[-1].split(":")[0]
    assert ultimo.isdigit() and int(ultimo) > 0, "la imagen no debe correr como root"


def test_el_dockerfile_tiene_healthcheck_contra_salud() -> None:
    texto = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(
        r"^HEALTHCHECK .*\\\n\s+CMD \[.*herramientas\.sonda_salud", texto, re.MULTILINE
    )
    sonda = (CODIGO / "herramientas" / "sonda_salud.py").read_text(encoding="utf-8")
    assert '"/salud"' in sonda


def test_el_dockerfile_no_lleva_secretos() -> None:
    declaraciones = re.findall(
        r"^(?:ENV|ARG)\s+(.+?)(?:\n(?!\w+=)|$)",
        DOCKERFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    nombres = " ".join(re.findall(r"([A-Z_]+)=", " ".join(declaraciones)))
    assert not re.search(r"SECRET|PASSWORD|TOKEN|CLAVE|KEY", nombres), nombres


def test_dockerignore_deja_fuera_secretos_pruebas_y_el_propio_despliegue() -> None:
    reglas = (CODIGO / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for regla in (
        ".env",
        ".env.*",
        "**/pruebas/",
        "conftest.py",
        "requirements-dev.txt",
        "despliegue/",
    ):
        assert regla in reglas


# --- Entorno y secretos ------------------------------------------------------------------------


def test_env_ejemplo_trae_valores_ficticios_que_no_se_pueden_usar() -> None:
    variables = _variables(ENV_EJEMPLO)
    for nombre in SECRETOS_DE_EJEMPLO:
        assert "CAMBIAR" in variables[nombre], f"{nombre} debe llevar un valor ficticio"
        with pytest.raises(ImproperlyConfigured):
            entorno.sin_marcador_de_ejemplo(nombre, variables[nombre])
    with pytest.raises(ImproperlyConfigured):  # y prod no arranca con la clave de ejemplo
        entorno.secret_key_de_produccion(variables["SECRET_KEY"])


def test_env_ejemplo_define_todas_las_variables_que_exige_el_compose() -> None:
    compose = (DESPLIEGUE / "docker-compose.yml").read_text(encoding="utf-8")
    obligatorias = set(re.findall(r"\$\{(\w+):\?", compose))
    assert obligatorias, "el Compose deberia exigir sus secretos con ${VAR:?}"
    assert obligatorias <= set(_variables(ENV_EJEMPLO))


def test_env_ejemplo_usa_hosts_propios_y_no_comodines_de_sufijo_publico() -> None:
    hosts = _variables(ENV_EJEMPLO)["ALLOWED_HOSTS"]
    assert entorno.hosts_permitidos_de_produccion(hosts) == ["localhost"]
    contenido = ENV_EJEMPLO.read_text(encoding="utf-8")
    assert ".empresa.example" in contenido  # la regla documentada: comodin de un dominio PROPIO
    assert "NUNCA `*`" in contenido


def test_env_ejemplo_trae_un_hsts_corto_solo_para_desarrollo() -> None:
    variables = _variables(ENV_EJEMPLO)
    assert 0 < int(variables["HSTS_SEGUNDOS"]) <= 3600
    assert variables["HSTS_SUBDOMINIOS"] == "false"
    assert variables["HSTS_PRELOAD"] == "false"
    assert variables["CONFIAR_EN_PROXY_TLS"] == "true"


def test_los_archivos_de_entorno_reales_no_se_versionan() -> None:
    lineas = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {".env", ".env.*", "!.env.ejemplo"} <= set(lineas)
    assert lineas.index(".env.*") < lineas.index("!.env.ejemplo")  # la excepcion va despues


@pytest.mark.skipif(shutil.which("git") is None, reason="git no esta instalado")
def test_no_hay_certificados_ni_archivos_de_entorno_versionados() -> None:
    resultado = subprocess.run(
        ["git", "ls-files", "--", "codigo/despliegue"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode != 0:
        pytest.skip("no es un repositorio git")
    versionados = resultado.stdout.split()
    prohibidos = [
        r for r in versionados if re.search(r"\.(crt|key|pem|p12)$|/\.env(\.(?!ejemplo$)\w+)?$", r)
    ]
    assert prohibidos == []


def test_los_scripts_y_la_plantilla_tienen_fin_de_linea_lf() -> None:
    """Un `.sh` con CRLF no arranca en el contenedor (`/bin/sh^M: bad interpreter`)."""
    for ruta in (NGINX, DESPLIEGUE / "nginx" / "generar_certificado.sh", DOCKERFILE, ENV_EJEMPLO):
        assert b"\r" not in ruta.read_bytes(), f"{ruta.name} tiene CRLF"
    atributos = (RAIZ / ".gitattributes").read_text(encoding="utf-8")
    assert "* text=auto eol=lf" in atributos
    for patron in ("*.sh", "*.py", "*.yml", "*.sql", ".importlinter"):
        assert re.search(rf"^{re.escape(patron)}\s+text eol=lf$", atributos, re.MULTILINE), patron
    for binario in ("*.docx", "*.pptx", "*.png", "*.parquet"):
        assert re.search(rf"^{re.escape(binario)}\s+binary$", atributos, re.MULTILINE), binario


# --- CI (D.6.2): construccion, trivy y hadolint ------------------------------------------------


def test_el_ci_construye_la_imagen_y_la_escanea_con_trivy_y_hadolint() -> None:
    ci = CI.read_text(encoding="utf-8")
    assert "docker build" in ci
    assert re.search(r"aquasec/trivy:\d+\.\d+\.\d+@sha256:[0-9a-f]{64}", ci)
    assert "--exit-code 1" in ci
    assert "--severity CRITICAL,HIGH" in ci
    assert "--ignore-unfixed" in ci
    assert re.search(r"hadolint/hadolint:v\d+\.\d+\.\d+@sha256:[0-9a-f]{64}", ci)


def test_el_ci_exige_docker_para_las_pruebas_que_lo_necesitan() -> None:
    # En una maquina sin Docker esas pruebas se omiten; en el CI no deben omitirse nunca.
    assert re.search(r'^\s+REQUIERE_DOCKER: "1"\s*$', CI.read_text(encoding="utf-8"), re.MULTILINE)


# --- Compose resuelto --------------------------------------------------------------------------

# SIN_DOCKER=1 simula una maquina sin Docker (el CI del plugin lo usa para probar ese camino).
DOCKER = None if os.environ.get("SIN_DOCKER") == "1" else shutil.which("docker")
# Docker es OPCIONAL para desarrollar y probar: sin el, estas pruebas se omiten con el motivo a la
# vista. En el CI de GitHub (REQUIERE_DOCKER=1) NO se omiten en silencio: sin Docker, fallan.
REQUIERE_DOCKER = os.environ.get("REQUIERE_DOCKER") == "1"


def _sin_docker(motivo: str) -> NoReturn:
    if REQUIERE_DOCKER:
        pytest.fail(f"{motivo} (REQUIERE_DOCKER=1: en el CI no se omiten en silencio)")
    pytest.skip(f"{motivo}. Docker es opcional para desarrollar; estas pruebas corren en el CI.")


@functools.cache
def _servicio_de_docker_responde() -> bool:
    """El cliente existe Y el servicio contesta (Docker Desktop apagado cuenta como sin Docker)."""
    if DOCKER is None:
        return False
    try:
        resultado = subprocess.run(
            [DOCKER, "info"],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return resultado.returncode == 0


def _compose(tmp_path: Path, *archivos: str, extra: dict[str, str] | None = None) -> dict[str, Any]:
    variables = _variables(ENV_EJEMPLO)
    for nombre in SECRETOS_DE_EJEMPLO:
        variables[nombre] = secrets.token_hex(32)
    variables.update(extra or {})
    env = tmp_path / "entorno.env"
    env.write_text("\n".join(f"{k}={v}" for k, v in variables.items()) + "\n", encoding="utf-8")
    comando = ["docker", "compose", "--env-file", str(env)]
    for archivo in archivos:
        comando += ["-f", archivo]
    resultado = subprocess.run(
        [*comando, "config", "--format", "json"],
        cwd=DESPLIEGUE,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr
    configuracion: dict[str, Any] = json.loads(resultado.stdout)
    return configuracion


@pytest.fixture
def desarrollo(tmp_path: Path) -> dict[str, Any]:
    if DOCKER is None:
        _sin_docker("Docker no esta instalado")
    return _compose(tmp_path, "docker-compose.yml")


@pytest.mark.lento
def test_compose_solo_nginx_publica_puertos_y_solo_en_loopback(desarrollo: dict[str, Any]) -> None:
    servicios = desarrollo["services"]
    con_puertos = {n for n, s in servicios.items() if s.get("ports")}
    assert con_puertos == {"nginx"}
    for puerto in servicios["nginx"]["ports"]:
        assert puerto["host_ip"] == "127.0.0.1"
    assert not any("5432" in str(p) for s in servicios.values() for p in s.get("ports", []))


@pytest.mark.lento
def test_compose_incluye_los_contenedores_de_esta_etapa_y_ninguno_de_otros_elementos(
    desarrollo: dict[str, Any],
) -> None:
    servicios = set(desarrollo["services"])
    assert {
        "nginx",
        "web",
        "worker",
        "worker-outbox",
        "beat",
        "postgres",
        "redis",
        "migrar",
        "certificado",
    } == servicios
    # Pertenecen a (minio, antivirus), y.
    assert not servicios & {"minio", "antivirus", "respaldos"}


@pytest.mark.lento
def test_compose_la_aplicacion_no_recibe_las_credenciales_del_rol_dueno(
    desarrollo: dict[str, Any],
) -> None:
    prohibidas = {
        "DATABASE_MIGRACIONES_URL",
        "DATABASE_ADMIN_URL",
        "POSTGRES_ADMIN_PASSWORD",
        "APP_MIGRACIONES_PASSWORD",
    }
    for nombre in ("web", "worker", "worker-outbox", "beat"):
        variables = desarrollo["services"][nombre]["environment"]
        assert not prohibidas & set(variables), nombre
        assert variables["DATABASE_URL"].startswith("postgres://app_web:")
        assert variables["DJANGO_SETTINGS_MODULE"] == "configuracion.settings.prod"
    migrar = desarrollo["services"]["migrar"]["environment"]
    assert migrar["DJANGO_SETTINGS_MODULE"] == "configuracion.settings.migraciones"
    assert migrar["DATABASE_MIGRACIONES_URL"].startswith("postgres://app_migraciones:")
    assert "DATABASE_URL" not in migrar


@pytest.mark.lento
def test_compose_la_aplicacion_arranca_despues_de_las_migraciones(
    desarrollo: dict[str, Any],
) -> None:
    for nombre in ("web", "worker", "worker-outbox", "beat"):
        dependencias = desarrollo["services"][nombre]["depends_on"]
        assert dependencias["migrar"]["condition"] == "service_completed_successfully"
    assert desarrollo["services"]["nginx"]["depends_on"]["web"]["condition"] == "service_healthy"


@pytest.mark.lento
def test_compose_endurece_los_contenedores_y_aisla_la_red_de_datos(
    desarrollo: dict[str, Any],
) -> None:
    for nombre in ("web", "worker", "worker-outbox", "beat", "migrar"):
        servicio = desarrollo["services"][nombre]
        assert servicio["read_only"] is True
        assert servicio["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in servicio["security_opt"]
    assert desarrollo["networks"]["datos"]["internal"] is True
    assert set(desarrollo["services"]["postgres"]["networks"]) == {"datos"}
    assert set(desarrollo["services"]["redis"]["networks"]) == {"datos"}
    assert set(desarrollo["services"]["nginx"]["networks"]) == {"borde", "aplicacion"}


def test_compose_no_lleva_secretos_escritos_sino_variables() -> None:
    lineas = (DESPLIEGUE / "docker-compose.yml").read_text(encoding="utf-8").splitlines()
    for linea in (linea.strip() for linea in lineas if not linea.strip().startswith("#")):
        clave, _, valor = linea.partition(":")
        valor = valor.strip()
        if re.search(r"PASSWORD|SECRET", clave):
            assert valor.startswith("${"), linea
        if clave.endswith("_URL"):
            assert re.search(r"://\w*:\$\{\w+[:}]", valor), linea  # la clave sale de una variable
    codigo = [linea for linea in lineas if not linea.strip().startswith("#")]
    assert not any("localhost:5432" in linea for linea in codigo)


ARCHIVOS_PRUEBAS = ("docker-compose.yml", "docker-compose.pruebas.yml")


def _slug_del_proyecto() -> str:
    """El prefijo del proyecto (`<slug>`), tomado del nombre del Compose de desarrollo
    (`name: <slug>-dev`). Asi las pruebas no llevan el nombre del proyecto escrito."""
    compose = (DESPLIEGUE / "docker-compose.yml").read_text(encoding="utf-8")
    nombre = re.search(r"^name: (\S+)-dev$", compose, re.MULTILINE)
    assert nombre, "el Compose de desarrollo debe llamarse <slug>-dev"
    return nombre.group(1)


SLUG = _slug_del_proyecto()
IMAGEN_LOCAL_DE_PRUEBAS = f"{SLUG}:pruebas"


@pytest.mark.lento
def test_compose_pruebas_funciona_en_localhost_con_una_imagen_construida_localmente(
    tmp_path: Path,
) -> None:
    """sin registro ni variables extra, usa la imagen local y no la descarga."""
    if DOCKER is None:
        _sin_docker("Docker no esta instalado")
    pruebas = _compose(tmp_path, *ARCHIVOS_PRUEBAS)
    assert pruebas["name"] == f"{SLUG}-pruebas"
    for nombre in ("web", "worker", "worker-outbox", "beat", "migrar"):
        servicio = pruebas["services"][nombre]
        assert servicio["image"] == IMAGEN_LOCAL_DE_PRUEBAS
        assert "build" not in servicio
        assert servicio["pull_policy"] == "missing"  # solo descarga si la imagen no existe


@pytest.mark.lento
def test_compose_pruebas_admite_una_imagen_de_registro_que_se_descarga_siempre(
    tmp_path: Path,
) -> None:
    if DOCKER is None:
        _sin_docker("Docker no esta instalado")
    imagen = f"ghcr.io/ejemplo/{SLUG}:abc123"
    pruebas = _compose(
        tmp_path,
        *ARCHIVOS_PRUEBAS,
        extra={"APP_IMAGEN": imagen, "APP_PULL_POLICY": "always"},
    )
    for nombre in ("web", "worker", "worker-outbox", "beat", "migrar"):
        servicio = pruebas["services"][nombre]
        assert servicio["image"] == imagen
        assert "build" not in servicio
        assert servicio["pull_policy"] == "always"


@pytest.mark.lento
def test_compose_pruebas_resuelto_revierte_los_adaptadores_falsos_en_la_aplicacion(
    tmp_path: Path,
) -> None:
    """H2: el Compose de desarrollo admite los falsos; con el de pruebas encima quedan fuera.

    Se lee el resultado YA resuelto por `docker compose config` (anclas, herencia y superposición),
    no el YAML crudo: es lo que de verdad recibirán `web` y `worker` en staging.
    """
    if DOCKER is None:
        _sin_docker("Docker no esta instalado")
    base = _compose(tmp_path, "docker-compose.yml")
    pruebas = _compose(tmp_path, *ARCHIVOS_PRUEBAS)
    for nombre in ("web", "worker", "worker-outbox", "beat"):
        # El punto de partida SI trae los falsos: si no, la prueba pasaría sin revertir nada.
        entorno_base = base["services"][nombre]["environment"]
        assert entorno_base["APP_PERMITIR_ADAPTADORES_FALSOS"] == "true"

        entorno = pruebas["services"][nombre]["environment"]
        assert entorno["APP_PERMITIR_ADAPTADORES_FALSOS"] == "false", nombre
        # Ningun puerto elegible (`APP_ADAPTADOR_<PUERTO>`) queda con su falso en staging.
        for variable, valor in entorno.items():
            if variable.startswith("APP_ADAPTADOR_"):
                assert str(valor).strip().lower() != "falso", f"{nombre}: {variable}"


def test_compose_pruebas_documenta_la_imagen_local_y_no_repite_el_reinicio_del_base() -> None:
    texto = COMPOSE_PRUEBAS.read_text(encoding="utf-8")
    assert "pull_policy: ${APP_PULL_POLICY:-missing}" in texto
    assert f"${{APP_IMAGEN:-{IMAGEN_LOCAL_DE_PRUEBAS}}}" in texto
    assert "Reinicio automatico" not in texto  # `restart: unless-stopped` ya esta en el base
    assert "restart: unless-stopped" in (DESPLIEGUE / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    readme = (CODIGO / "README.md").read_text(encoding="utf-8")
    assert f"docker build -f despliegue/Dockerfile -t {IMAGEN_LOCAL_DE_PRUEBAS} ." in readme
    assert "la imagen del CI" not in readme  # el CI nunca la publica


def test_compose_pruebas_pone_el_reset_de_build_en_cada_servicio_y_no_en_el_ancla() -> None:
    """Compose 2.38 (runner de GitHub) pierde `!reset` si llega por la fusion `<<:` de un ancla."""
    lineas = COMPOSE_PRUEBAS.read_text(encoding="utf-8").splitlines()
    ancla = lineas.index("x-imagen-ya-construida: &imagen-ya-construida")
    cuerpo_ancla = []
    for linea in lineas[ancla + 1 :]:
        if linea and not linea.startswith(" "):
            break
        cuerpo_ancla.append(linea)
    assert not any("!reset" in linea for linea in cuerpo_ancla)
    servicios = ("migrar", "web", "worker", "worker-outbox", "beat")
    inicio = lineas.index("services:")
    for nombre in servicios:
        posicion = lineas.index(f"  {nombre}:", inicio)
        assert "    build: !reset null" in lineas[posicion + 1 : posicion + 4]


# --- Endurecimiento de los contenedores y healthcheck de nginx -------------


@pytest.mark.lento
def test_compose_redis_corre_sin_root_con_sistema_de_solo_lectura_y_sin_capacidades(
    desarrollo: dict[str, Any],
) -> None:
    redis = desarrollo["services"]["redis"]
    assert redis["user"] == "redis"
    assert redis["read_only"] is True
    assert redis["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in redis["security_opt"]
    assert "/tmp" in redis["tmpfs"]  # noqa: S108
    assert "cap_add" not in redis


@pytest.mark.lento
def test_compose_certificado_solo_conserva_chown(desarrollo: dict[str, Any]) -> None:
    certificado = desarrollo["services"]["certificado"]
    assert certificado["cap_drop"] == ["ALL"]
    assert certificado["cap_add"] == ["CHOWN"]
    assert certificado["read_only"] is True
    assert "no-new-privileges:true" in certificado["security_opt"]
    assert certificado["network_mode"] == "none"


@pytest.mark.lento
def test_compose_postgres_descarta_todo_salvo_lo_minimo_para_bajar_de_usuario(
    desarrollo: dict[str, Any],
) -> None:
    postgres = desarrollo["services"]["postgres"]
    assert postgres["cap_drop"] == ["ALL"]
    assert set(postgres["cap_add"]) == {"CHOWN", "SETUID", "SETGID", "FOWNER", "DAC_OVERRIDE"}
    assert "no-new-privileges:true" in postgres["security_opt"]


@pytest.mark.lento
def test_compose_nginx_es_de_solo_lectura_con_tmpfs_y_tiene_healthcheck(
    desarrollo: dict[str, Any],
) -> None:
    nginx = desarrollo["services"]["nginx"]
    assert nginx["read_only"] is True
    destinos = {t.split(":")[0] for t in nginx["tmpfs"]}
    # /etc/nginx/conf.d: el arranque genera ahi `default.conf`; sin escritura corre SIN config.
    assert {"/tmp", "/var/cache/nginx", "/run", "/etc/nginx/conf.d"} <= destinos  # noqa: S108
    conf_d = next(t for t in nginx["tmpfs"] if t.startswith("/etc/nginx/conf.d"))
    assert "uid=101" in conf_d  # el usuario de nginx-unprivileged debe poder escribir
    sonda = " ".join(nginx["healthcheck"]["test"])
    assert "127.0.0.1 8080" in sonda  # contra el puerto HTTP del propio contenedor
    assert "' 301 '" in sonda  # espera la redireccion, no un 200
    assert "NGINX_NOMBRE_PUBLICO" in sonda  # con el Host correcto: otro recibiria un 444
    assert nginx["depends_on"]["web"]["condition"] == "service_healthy"


@pytest.mark.lento
def test_compose_los_procesos_de_la_aplicacion_tienen_limites_de_memoria_y_de_procesos(
    desarrollo: dict[str, Any],
) -> None:
    for nombre in ("web", "worker", "worker-outbox", "beat"):
        servicio = desarrollo["services"][nombre]
        memoria = int(servicio["mem_limit"])
        assert 128 * 1024**2 <= memoria <= 2 * 1024**3, nombre
        assert 32 <= servicio["pids_limit"] <= 1024, nombre
    compose = (DESPLIEGUE / "docker-compose.yml").read_text(encoding="utf-8")
    assert compose.count("mem_limit:") == 4  # web, worker, worker-outbox y beat
    assert "# Limites:" in compose  # cada limite explica de donde sale


# --- Certificado: nombre publico validado ----------------------------------------------


# El script se ejecuta DENTRO de la imagen `alpine/openssl` fijada por digest en el Compose (la
# misma del servicio `certificado`), no con el `sh` de la maquina que corre las pruebas.
# Motivo: en Windows el `sh` es el de Git for Windows (MSYS2), y su arranque
# consulta al controlador de dominio (Netlogon, `nsswitch.conf` con `passwd: files db`, sin
# /etc/passwd). En un equipo unido a un dominio, esa consulta se queda colgada por minutos de forma
# periodica y sin relacion con el script (incluso `sh -c true`): la prueba pasaba o vencia por azar.
# El contenedor ademas prueba el interprete (busybox) y el `openssl` reales, no unos equivalentes.

_SAN_ESPERADO_DE_LOCALHOST = ["DNS:localhost", "IP Address:127.0.0.1", "IP Address:0:0:0:0:0:0:0:1"]


def _docker() -> str:
    if not _servicio_de_docker_responde():
        _sin_docker(
            "Estas pruebas ejecutan generar_certificado.sh en la imagen `alpine/openssl` del "
            "Compose y necesitan Docker instalado y con el servicio en marcha"
        )
    assert DOCKER is not None
    return DOCKER


@pytest.fixture(scope="session")
def imagen_openssl() -> str:
    """La imagen del servicio `certificado` (con su digest), descargada si hace falta."""
    compose = yaml.safe_load((DESPLIEGUE / "docker-compose.yml").read_text(encoding="utf-8"))
    imagen = str(compose["services"]["certificado"]["image"])
    docker = _docker()
    presente = subprocess.run(
        [docker, "image", "inspect", imagen],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=60,
        check=False,
    )
    if presente.returncode != 0:
        bajada = subprocess.run(
            [docker, "pull", imagen],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=600,
            check=False,
        )
        assert bajada.returncode == 0, f"no se pudo bajar {imagen}: {bajada.stderr}"
    return imagen


def _generar_certificado(
    nombre: str, imagen: str, *, despues: str = ""
) -> subprocess.CompletedProcess[str]:
    """Corre el script en la imagen; `despues` es un comando de shell que sigue si el script sale 0.

    Con `despues` vacio el destino (`/no-existe`) no existe: un nombre valido pasa la validacion y
    falla DESPUES, en `openssl`. Con `despues`, el destino es un tmpfs y el certificado se genera.
    """
    comando = "/bin/sh /generar_certificado.sh" + (f" && {despues}" if despues else "")
    destino = "/certs" if despues else "/no-existe"
    argumentos = [
        _docker(),
        "run",
        "--rm",
        "--network=none",
        "--cap-drop=ALL",
        "--cap-add=CHOWN",  # lo unico que pide el script (chown a nginx), como en el Compose
        "--tmpfs=/certs",
        f"--mount=type=bind,src={GENERAR_CERTIFICADO},dst=/generar_certificado.sh,readonly",
        "--env=APP_NOMBRE_PUBLICO",  # sin valor: lo hereda del entorno de este proceso (admite \n)
        f"--env=DESTINO={destino}",
        "--entrypoint=/bin/sh",
        imagen,
        "-c",
        comando,
    ]
    return subprocess.run(
        argumentos,
        env={**os.environ, "APP_NOMBRE_PUBLICO": nombre},
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
        timeout=120,
        check=False,
    )


def _san_de(nombre: str, imagen: str) -> list[str]:
    """Las entradas del subjectAltName del certificado que genera el script para `nombre`."""
    resultado = _generar_certificado(
        nombre, imagen, despues="openssl x509 -in /certs/tls.crt -noout -ext subjectAltName"
    )
    assert resultado.returncode == 0, resultado.stderr
    ultima_linea = resultado.stdout.strip().splitlines()[-1]
    return [entrada.strip() for entrada in ultima_linea.split(",")]


@pytest.mark.parametrize(
    "nombre",
    [
        "app,empresa.example",
        "a b",
        "a/b",
        "a=b",
        "-localhost",
        "localhost-",
        ".x",
        "x.",
        "a;b",
        "a\nb",
    ],
)
def test_generar_certificado_rechaza_un_nombre_publico_invalido(
    nombre: str, imagen_openssl: str
) -> None:
    resultado = _generar_certificado(nombre, imagen_openssl)
    assert resultado.returncode == 1
    assert "APP_NOMBRE_PUBLICO invalido" in resultado.stderr


@pytest.mark.parametrize(
    "nombre", ["localhost", "app.empresa.example", "pruebas.empresa.example", "a"]
)
def test_generar_certificado_no_rechaza_un_nombre_publico_valido(
    nombre: str, imagen_openssl: str
) -> None:
    resultado = _generar_certificado(nombre, imagen_openssl)
    assert "APP_NOMBRE_PUBLICO invalido" not in resultado.stderr


@pytest.mark.parametrize("nombre", ["localhost", "LocalHost"])
def test_generar_certificado_no_repite_localhost_en_el_san(
    nombre: str, imagen_openssl: str
) -> None:
    san = _san_de(nombre, imagen_openssl)
    assert san == [f"DNS:{nombre}", "IP Address:127.0.0.1", "IP Address:0:0:0:0:0:0:0:1"]
    assert [e.lower() for e in san].count("dns:localhost") == 1


def test_generar_certificado_agrega_localhost_al_san_de_otro_nombre(imagen_openssl: str) -> None:
    san = _san_de("app.empresa.example", imagen_openssl)
    assert san == ["DNS:app.empresa.example", *_SAN_ESPERADO_DE_LOCALHOST]


def test_generar_certificado_valida_el_nombre_al_inicio_y_busca_con_grep_fijo() -> None:
    texto = GENERAR_CERTIFICADO.read_text(encoding="utf-8")
    assert "^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$" in texto
    assert texto.index("^[A-Za-z0-9]") < texto.index("openssl x509")  # antes de usarlo
    assert texto.index("^[A-Za-z0-9]") < texto.index("openssl req")
    assert re.search(r'grep -Fq "DNS:\$NOMBRE,"', texto)  # texto fijo, no expresion regular
    assert 'grep -q "DNS:' not in texto


# --- CI y flujo de despliegue -----------------------------------------


def _flujo(ruta: Path) -> dict[str, Any]:
    # PyYAML interpreta la clave `on` como el booleano True (YAML 1.1): no se usa aqui.
    flujo: dict[str, Any] = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    return flujo


def _pasos_de_despliegue() -> list[dict[str, Any]]:
    pasos: list[dict[str, Any]] = _flujo(DESPLEGAR)["jobs"]["desplegar"]["steps"]
    return pasos


def test_desplegar_pruebas_solo_corre_desde_main_como_primer_paso() -> None:
    primero = _pasos_de_despliegue()[0]
    assert primero["if"] == "github.ref != 'refs/heads/main'"
    assert "exit 1" in primero["run"]
    cabecera = DESPLEGAR.read_text(encoding="utf-8").split("name: Desplegar en pruebas")[0]
    assert "Required reviewers" in cabecera
    assert "Deployment branches" in cabecera
    assert "`main`" in cabecera
    assert "una persona" in cabecera  # es configuracion de GitHub, no del repositorio


def test_desplegar_pruebas_pasa_el_propietario_a_minusculas_y_lo_exporta() -> None:
    flujo = _flujo(DESPLEGAR)
    assert "IMAGEN" not in flujo["jobs"]["desplegar"].get("env", {})  # ya no sale de `${{ }}`
    paso = next(p for p in _pasos_de_despliegue() if "GITHUB_ENV" in p.get("run", ""))
    assert "${GITHUB_REPOSITORY_OWNER,,}" in paso["run"]
    imagen = "IMAGEN=ghcr.io/${GITHUB_REPOSITORY_OWNER,,}/" + SLUG + ":${GITHUB_SHA}"
    assert imagen in paso["run"]
    assert '>> "$GITHUB_ENV"' in paso["run"]
    nombres = [p.get("name", p.get("uses", "")) for p in _pasos_de_despliegue()]
    exportar = _pasos_de_despliegue().index(paso)
    construir = nombres.index("Construccion de la imagen")
    assert exportar < construir  # antes de construir, etiquetar o publicar
    assert "${{ github.repository_owner }}" not in DESPLEGAR.read_text(encoding="utf-8")


def test_desplegar_pruebas_da_packages_write_solo_al_job_y_borra_la_llave_al_salir() -> None:
    flujo = _flujo(DESPLEGAR)
    assert flujo["permissions"] == {"contents": "read"}  # el flujo, sin permisos de escritura
    assert flujo["jobs"]["desplegar"]["permissions"] == {"contents": "read", "packages": "write"}
    paso = next(p for p in _pasos_de_despliegue() if "id_pruebas" in p.get("run", ""))
    lineas = paso["run"].splitlines()
    assert lineas[0] == "trap 'rm -f ~/.ssh/id_pruebas' EXIT"  # antes de escribir la llave
    assert paso["run"].index("trap ") < paso["run"].index("> ~/.ssh/id_pruebas")


def test_desplegar_pruebas_fija_la_descarga_del_registro_en_el_servidor() -> None:
    paso = next(p for p in _pasos_de_despliegue() if "id_pruebas" in p.get("run", ""))
    assert "APP_PULL_POLICY=always" in paso["run"]


def test_ci_valida_el_compose_de_pruebas_local_y_de_registro_sin_espacios_sueltos() -> None:
    pasos = [
        paso
        for job in _flujo(CI)["jobs"].values()
        for paso in job["steps"]
        if paso.get("name", "").startswith("Compose valido")
    ]
    assert len(pasos) == 1
    comandos = pasos[0]["run"]
    # ninguna linea lleva 3 o mas espacios EN MEDIO (solo la sangria del inicio es valida).
    assert not [linea for linea in comandos.splitlines() if re.search(r"\S {3,}\S", linea)]
    assert comandos.count("docker-compose.pruebas.yml config --quiet") == 2
    assert f"APP_IMAGEN=ghcr.io/ejemplo/{SLUG}:ci" in comandos  # el de registro


# --- Dependencias declaradas (PSL empaquetada) -----------------------------------------


def test_requirements_declaran_psutil_y_la_lista_de_sufijos_con_versiones_acotadas() -> None:
    desarrollo = (CODIGO / "requirements-dev.txt").read_text(encoding="utf-8")
    ejecucion = (CODIGO / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^psutil>=\d+(\.\d+)*,<\d+", desarrollo, re.MULTILINE)
    assert re.search(
        r"^pyyaml>=\d+(\.\d+)*,<\d+", desarrollo, re.MULTILINE
    )  # lo usan estas pruebas
    assert re.search(r"^publicsuffixlist>=\d+(\.\d+)*,<\d+", ejecucion, re.MULTILINE)
    paquetes = [ln for ln in ejecucion.splitlines() if ln and not ln.startswith("#")]
    assert not [p for p in paquetes if "tldextract" in p]  # descargaria la lista por defecto


def test_la_plantilla_de_nginx_cita_el_archivo_de_pruebas_que_existe() -> None:
    texto = NGINX.read_text(encoding="utf-8")
    assert "test_nginx.py" not in texto  # ese archivo no existe
    citados = set(re.findall(r"test_\w+\.py", texto))
    assert citados == {"test_despliegue.py"}
    assert (CODIGO / "herramientas" / "pruebas" / "test_despliegue.py").is_file()


# --- nginx vuelve a resolver `web` --------------------------------------------------


def test_nginx_resuelve_web_de_nuevo_con_el_dns_de_docker() -> None:
    directivas = _directivas_de_nginx()
    assert "resolver 127.0.0.11 valid=10s;" in directivas
    assert not any(d.startswith("upstream ") for d in directivas), "un upstream fijaria la IP"
    # `proxy_pass` con variable: sin ella nginx resuelve `web` solo al arrancar (502 al recrearlo).
    assert "set $app_web web:8000;" in directivas
    assert "proxy_pass http://$app_web;" in directivas
    assert not any(d.startswith("proxy_pass http://web") for d in directivas)


def test_el_cambio_de_resolucion_no_quita_las_protecciones_de_la_plantilla() -> None:
    directivas = _directivas_de_nginx()
    assert "proxy_set_header Host $http_host;" in directivas
    assert "proxy_set_header X-Forwarded-Proto https;" in directivas
    assert "return 444;" in directivas  # host desconocido
    assert any(d.startswith("ssl_protocols TLSv1.2 TLSv1.3") for d in directivas)
    assert "client_max_body_size 10m;" in directivas
    assert not any("$http_x_forwarded_proto" in d for d in directivas)


# --- Limite de peticiones en el ingreso (DISENO D.5.4) -------------------------------------


def test_nginx_limita_las_peticiones_por_ip_solo_en_el_ingreso() -> None:
    directivas = _directivas_de_nginx()
    # La clave del limite es la IP SOLO para `/ingresar` y sus etapas; para lo demas queda vacia y
    # nginx no la cuenta (/salud, los estilos y la aplicacion con sesion no se limitan).
    assert "map $uri $app_clave_limite_ingreso {" in directivas
    assert 'default "";' in directivas
    assert "~^/ingresar(/|$) $binary_remote_addr;" in directivas
    # ... y ademas SOLO para POST (los GET no se cuentan; una VPN o un NAT comparten IP).
    assert "map $request_method $app_clave_limite_ingreso_post {" in directivas
    assert "POST $app_clave_limite_ingreso;" in directivas
    assert (
        "limit_req_zone $app_clave_limite_ingreso_post zone=app_ingreso:10m "
        "rate=${NGINX_LIMITE_INGRESO};" in directivas
    )
    assert "limit_req zone=app_ingreso burst=${NGINX_RAFAGA_INGRESO} nodelay;" in directivas


def test_el_limite_del_ingreso_contesta_429_con_un_mensaje_claro() -> None:
    texto = NGINX.read_text(encoding="utf-8")
    directivas = _directivas_de_nginx()
    assert "limit_req_status 429;" in directivas
    assert "error_page 429 = @app_demasiadas_peticiones;" in directivas
    assert "location @app_demasiadas_peticiones {" in directivas
    assert any(d.startswith("return 429 ") for d in directivas)
    assert "Espera un minuto" in texto
    assert "text/plain" in texto


def test_el_limite_va_en_el_server_https_y_cubre_el_proxy_a_la_aplicacion() -> None:
    texto = NGINX.read_text(encoding="utf-8")
    https = texto[texto.index("listen 8443 ssl;") :]
    assert "limit_req zone=app_ingreso" in https
    # El limite esta en el mismo `location` que hace el proxy: no hay otra ruta hacia `web`.
    ubicacion = https[https.index("location / {") :]
    assert ubicacion.index("limit_req zone=app_ingreso") < ubicacion.index("proxy_pass")
    assert [d for d in _directivas_de_nginx() if d.startswith("proxy_pass ")] == [
        "proxy_pass http://$app_web;"
    ]


def test_el_compose_define_el_limite_del_ingreso_con_valores_por_defecto() -> None:
    compose = (DESPLIEGUE / "docker-compose.yml").read_text(encoding="utf-8")
    assert "NGINX_LIMITE_INGRESO: ${APP_LIMITE_INGRESO:-180r/m}" in compose
    assert "NGINX_RAFAGA_INGRESO: ${APP_RAFAGA_INGRESO:-40}" in compose
    # Opcionales: el Compose valida con `.env.ejemplo` y no deben ser obligatorias.
    assert "APP_LIMITE_INGRESO:?" not in compose
    assert "APP_RAFAGA_INGRESO:?" not in compose


def test_el_ritmo_por_defecto_del_ingreso_tiene_el_formato_que_acepta_nginx() -> None:
    compose = (DESPLIEGUE / "docker-compose.yml").read_text(encoding="utf-8")
    ritmo = re.search(r"APP_LIMITE_INGRESO:-(\S+)\}", compose)
    rafaga = re.search(r"APP_RAFAGA_INGRESO:-(\S+)\}", compose)
    assert ritmo and rafaga
    assert re.fullmatch(r"[1-9]\d*r/[sm]", ritmo.group(1))
    assert rafaga.group(1).isdigit()


def test_el_limite_del_ingreso_esta_documentado_en_el_readme_y_el_env_ejemplo() -> None:
    readme = (CODIGO / "README.md").read_text(encoding="utf-8")
    assert "Limite de peticiones en el ingreso" in readme
    assert "429" in readme
    assert "APP_LIMITE_INGRESO" in readme
    ejemplo = ENV_EJEMPLO.read_text(encoding="utf-8")
    assert "APP_LIMITE_INGRESO" in ejemplo
    assert "APP_RAFAGA_INGRESO" in ejemplo


# --- Llave del segundo factor ----------------------------------------------------


def test_el_compose_pasa_el_nombre_de_la_aplicacion_que_sirve_de_emisor_del_segundo_factor() -> (
    None
):
    compose = (DESPLIEGUE / "docker-compose.yml").read_text(encoding="utf-8")
    assert re.search(r'APP_NOMBRE_APLICACION: "?\$\{APP_NOMBRE_APLICACION:-[^}]+\}"?', compose)
    assert "APP_NOMBRE_APLICACION:?" not in compose  # opcional


def test_el_compose_pasa_el_idioma_y_la_exigencia_de_tls_a_la_aplicacion() -> None:
    compose = yaml.safe_load((DESPLIEGUE / "docker-compose.yml").read_text(encoding="utf-8"))
    entorno_app = compose["x-entorno-app"]
    assert entorno_app["APP_IDIOMA"] == "${APP_IDIOMA:-}"  # vacia: el idioma del proyecto
    assert entorno_app["APP_EXIGIR_TLS_DATOS"] == "${APP_EXIGIR_TLS_DATOS:-false}"


def test_migrar_recibe_la_clave_de_redis_solo_para_validarla() -> None:
    compose = yaml.safe_load((DESPLIEGUE / "docker-compose.yml").read_text(encoding="utf-8"))
    entorno_migrar = compose["services"]["migrar"]["environment"]
    assert "REDIS_PASSWORD:?" in entorno_migrar["REDIS_PASSWORD"]


def test_el_compose_pasa_la_zona_horaria_a_la_aplicacion() -> None:
    """Sin esto el README prometeria una variable que el contenedor nunca recibe."""
    compose = yaml.safe_load((DESPLIEGUE / "docker-compose.yml").read_text(encoding="utf-8"))
    entorno_app = compose["x-entorno-app"]
    # Vacia: la aplicacion usa UTC.
    assert entorno_app["APP_ZONA_HORARIA"] == "${APP_ZONA_HORARIA:-}"
    assert "APP_ZONA_HORARIA:?" not in str(entorno_app)  # opcional
    # Los servicios de la aplicacion (web, worker...) usan ese bloque: lo heredan todos.
    servicios_con_entorno = [
        nombre
        for nombre, servicio in compose["services"].items()
        if servicio.get("environment") is entorno_app
    ]
    assert {"web", "worker"} <= set(servicios_con_entorno)


def test_el_compose_exige_y_pasa_la_llave_del_segundo_factor() -> None:
    compose = (DESPLIEGUE / "docker-compose.yml").read_text(encoding="utf-8")
    assert "APP_LLAVE_SEGUNDO_FACTOR: ${APP_LLAVE_SEGUNDO_FACTOR:?" in compose
    assert "APP_LLAVE_SEGUNDO_FACTOR" in _variables(ENV_EJEMPLO)


def test_la_llave_de_ejemplo_del_segundo_factor_no_sirve_en_produccion() -> None:
    valor = _variables(ENV_EJEMPLO)["APP_LLAVE_SEGUNDO_FACTOR"]
    assert "CAMBIAR" in valor
    with pytest.raises(ImproperlyConfigured):
        entorno.llave_segundo_factor_de_produccion(valor)


def test_el_ci_pasa_la_llave_del_segundo_factor_a_check_deploy() -> None:
    ci = CI.read_text(encoding="utf-8")
    llaves = re.findall(
        r"^\s+(SECRET_KEY|APP_LLAVE_HUELLA|APP_LLAVE_SEGUNDO_FACTOR): (\S+)$", ci, re.M
    )
    valores = dict(llaves)
    assert set(valores) == {"SECRET_KEY", "APP_LLAVE_HUELLA", "APP_LLAVE_SEGUNDO_FACTOR"}
    assert len(set(valores.values())) == 3  # las tres distintas
    entorno.llave_segundo_factor_de_produccion(valores["APP_LLAVE_SEGUNDO_FACTOR"])


def test_el_readme_documenta_la_llave_y_el_segundo_factor() -> None:
    readme = (CODIGO / "README.md").read_text(encoding="utf-8")
    assert "`APP_LLAVE_SEGUNDO_FACTOR`" in readme
    assert "distinta de `SECRET_KEY` y de `APP_LLAVE_HUELLA`" in readme
    assert "## Segundo factor" in readme


def test_las_dependencias_del_segundo_factor_llevan_version_acotada() -> None:
    ejecucion = (CODIGO / "requirements.txt").read_text(encoding="utf-8")
    for paquete in ("django-otp", "cryptography", "segno"):
        assert re.search(rf"^{paquete}>=\d+(\.\d+)*,<\d+", ejecucion, re.MULTILINE), paquete


@pytest.mark.lento
def test_compose_el_outbox_tiene_su_cola_propia_y_un_solo_beat(desarrollo: dict[str, Any]) -> None:
    """(D.6.1): `worker-outbox` atiende solo la cola `outbox`; `worker` no la toca;
    `beat` es uno y apaga limpio."""
    servicios = desarrollo["services"]
    assert servicios["worker-outbox"]["command"][-4:] == ["-Q", "outbox", "-n", "outbox@%h"]
    assert servicios["worker"]["command"][-2:] == ["-Q", "celery"]
    assert "beat" in servicios["beat"]["command"]
    assert "deploy" not in servicios["beat"]  # nunca mas de una replica
    for nombre in ("worker-outbox", "beat"):
        assert servicios[nombre]["stop_grace_period"] in (
            "30s",
            "15s",
            "30000000000",
            "15000000000",
        )
        assert servicios[nombre]["restart"] == "unless-stopped"
        assert servicios[nombre]["healthcheck"]["test"]
        assert "ports" not in servicios[nombre]
