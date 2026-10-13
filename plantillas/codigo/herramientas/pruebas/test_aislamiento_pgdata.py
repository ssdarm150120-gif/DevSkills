"""`pytest` no apaga el PostgreSQL de desarrollo.

Causa: `conftest.py` pedia el servidor embebido sobre `.pgdata/` con `cleanup_mode="stop"` y lo
detenia al terminar, pero ese mismo directorio es el que `herramientas.base_local` deja corriendo
para dev. Correccion: las pruebas usan su propio directorio (`.pgdata_pruebas/`).
"""

import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import psutil

from herramientas.base_local import DIRECTORIO_PGDATA, DIRECTORIO_PGDATA_PRUEBAS

RAIZ_REPOSITORIO = Path(__file__).resolve().parents[3]


def _acepta_conexiones(url: str) -> bool:
    import psycopg

    try:
        with psycopg.connect(url, connect_timeout=5) as conexion:
            return conexion.execute("SELECT 1").fetchone() == (1,)
    except psycopg.OperationalError:
        return False


def test_las_pruebas_y_dev_usan_directorios_distintos() -> None:
    assert DIRECTORIO_PGDATA.name == ".pgdata"
    assert DIRECTORIO_PGDATA_PRUEBAS.name == ".pgdata_pruebas"
    assert DIRECTORIO_PGDATA_PRUEBAS != DIRECTORIO_PGDATA
    assert DIRECTORIO_PGDATA_PRUEBAS.parent == DIRECTORIO_PGDATA.parent


def test_el_directorio_de_pruebas_esta_en_gitignore() -> None:
    lineas = (RAIZ_REPOSITORIO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".pgdata_pruebas/" in (linea.strip() for linea in lineas)


def test_conftest_apunta_al_directorio_de_pruebas_y_no_al_de_dev() -> None:
    fuente = (Path(__file__).resolve().parents[2] / "conftest.py").read_text(encoding="utf-8")
    assert "DIRECTORIO_PGDATA_PRUEBAS" in fuente
    assert "get_server(DIRECTORIO_PGDATA," not in fuente


@pytest.mark.skipif(
    "DATABASE_URL" in os.environ, reason="con DATABASE_URL (CI) no se usa el servidor embebido"
)
def test_el_servidor_de_esta_sesion_corre_sobre_el_directorio_de_pruebas(
    url_base_de_datos: str,
) -> None:
    import psycopg

    with psycopg.connect(url_base_de_datos, connect_timeout=10) as conexion:
        fila = conexion.execute("SHOW data_directory").fetchone()
    assert fila is not None
    assert Path(fila[0]).resolve() == (DIRECTORIO_PGDATA_PRUEBAS / "").resolve()


def _levantar_dev_en_otro_proceso(pgdata: Path) -> str:
    """Como `herramientas.base_local`: otro proceso lo levanta, sale y lo deja corriendo."""
    resultado = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, pgserver; "
            "print(pgserver.get_server(sys.argv[1], cleanup_mode=None).get_uri())",
            str(pgdata),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )
    return resultado.stdout.strip()


def _procesos_postgres_de(pgdata: Path) -> list["psutil.Process"]:
    """Procesos de PostgreSQL que corren sobre `pgdata`: el postmaster, sus hijos y los sueltos."""
    import psutil

    encontrados: dict[int, psutil.Process] = {}
    archivo_pid = pgdata / "postmaster.pid"
    if archivo_pid.exists():
        try:
            principal = psutil.Process(int(archivo_pid.read_text().splitlines()[0]))
            for proceso in [principal, *principal.children(recursive=True)]:
                encontrados[proceso.pid] = proceso
        except (psutil.NoSuchProcess, ValueError, IndexError):
            pass  # el postmaster ya no existe o el archivo esta a medias
    ruta = str(pgdata.resolve())
    for proceso in psutil.process_iter(["name", "cmdline"]):
        nombre = (proceso.info["name"] or "").lower()
        if nombre.startswith("postgres") and ruta in " ".join(proceso.info["cmdline"] or []):
            encontrados[proceso.pid] = proceso
    return list(encontrados.values())


def _matar_huerfanos(pgdata: Path) -> None:
    """Termina (y si hace falta mata) todo PostgreSQL que siga vivo sobre `pgdata`."""
    import psutil

    vivos = _procesos_postgres_de(pgdata)
    for proceso in vivos:
        with suppress(psutil.NoSuchProcess):
            proceso.terminate()
    _, sobrevivientes = psutil.wait_procs(vivos, timeout=10)
    for proceso in sobrevivientes:
        with suppress(psutil.NoSuchProcess):
            proceso.kill()
    psutil.wait_procs(sobrevivientes, timeout=10)


@contextmanager
def _sin_postgres_huerfanos(*directorios: Path) -> Iterator[None]:
    """Al salir (con o sin error) detiene los servidores de `directorios` y no deja ninguno vivo.

    Si una asercion falla antes del `cleanup()` de la prueba, el servidor quedaba corriendo y
    retenia el directorio temporal (en Windows, impedia borrarlo) y memoria.
    """
    pgserver = pytest.importorskip("pgserver")
    try:
        yield
    finally:
        for directorio in directorios:
            try:
                if (directorio / "PG_VERSION").exists():
                    pgserver.get_server(directorio, cleanup_mode="stop").cleanup()
            finally:
                _matar_huerfanos(directorio)
        huerfanos = [p.pid for d in directorios for p in _procesos_postgres_de(d)]
        assert not huerfanos, f"quedaron procesos postgres huerfanos: {huerfanos}"


@pytest.mark.lento
def test_detener_el_servidor_de_pruebas_no_apaga_al_de_desarrollo(
    tmp_path: Path, url_base_de_datos: str
) -> None:
    """Misma secuencia que `base_local` (dev, otro proceso) y `conftest` (pruebas, `stop`).

    `url_base_de_datos` solo garantiza que las zonas horarias de pgserver (Windows) existan.
    """
    pgserver = pytest.importorskip("pgserver")
    pgdata_dev = tmp_path / "pgdata"
    pgdata_pruebas = tmp_path / "pgdata_pruebas"
    with _sin_postgres_huerfanos(pgdata_dev, pgdata_pruebas):
        uri_dev = _levantar_dev_en_otro_proceso(pgdata_dev)
        pruebas = pgserver.get_server(pgdata_pruebas, cleanup_mode="stop")
        assert _acepta_conexiones(uri_dev)
        assert _acepta_conexiones(pruebas.get_uri())
        uri_pruebas = pruebas.get_uri()
        pruebas.cleanup()  # lo que hace `conftest.py` al terminar la sesion
        assert not _acepta_conexiones(uri_pruebas)
        assert _acepta_conexiones(uri_dev), "pytest apago el PostgreSQL de desarrollo"


@pytest.mark.lento
def test_con_el_mismo_directorio_el_servidor_de_pruebas_si_apagaba_el_de_dev(
    tmp_path: Path, url_base_de_datos: str
) -> None:
    """Contraprueba: reproduce el defecto original (mismo `pgdata` para dev y pruebas)."""
    pgserver = pytest.importorskip("pgserver")
    compartido = tmp_path / "pgdata"
    with _sin_postgres_huerfanos(compartido):
        uri_dev = _levantar_dev_en_otro_proceso(compartido)
        assert _acepta_conexiones(uri_dev)
        pgserver.get_server(compartido, cleanup_mode="stop").cleanup()
        assert not _acepta_conexiones(uri_dev), (
            "con un directorio compartido la parada afecta a dev"
        )


@pytest.mark.lento
def test_el_barrido_de_huerfanos_mata_un_postgres_que_nadie_apago(
    tmp_path: Path, url_base_de_datos: str
) -> None:
    """si una prueba falla antes de apagar su servidor, el `finally` no lo deja vivo."""
    pytest.importorskip("pgserver")
    pgdata = tmp_path / "pgdata"
    with _sin_postgres_huerfanos(pgdata):
        _levantar_dev_en_otro_proceso(pgdata)  # queda corriendo, sin dueno que lo detenga
        assert _procesos_postgres_de(pgdata), "el servidor de la prueba deberia estar vivo"
        _matar_huerfanos(pgdata)
        assert not _procesos_postgres_de(pgdata)


def test_el_proceso_de_base_local_no_toca_el_directorio_de_pruebas() -> None:
    resultado = subprocess.run(
        [
            sys.executable,
            "-c",
            "import herramientas.base_local as b; print(b.DIRECTORIO_PGDATA_PRUEBAS.name)",
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert resultado.stdout.strip() == ".pgdata_pruebas"
