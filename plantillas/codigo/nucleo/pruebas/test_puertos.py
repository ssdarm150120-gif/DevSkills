"""Puertos compartidos de `nucleo.puertos` y su registro (y D.1.4)."""

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol, runtime_checkable

import pytest

from herramientas.contratos_importlinter import IMPORTS_PERMITIDOS_EN_DOMINIO
from nucleo import puertos
from nucleo.pruebas.aislamiento import Aislamiento
from nucleo.puertos import (
    ErrorDeIntegracion,
    ErrorTemporalDeIntegracion,
    LimiteDeSolicitudes,
    SolicitudRechazada,
    registro,
)

CODIGO = Path(__file__).resolve().parents[2]
CARPETA_PUERTOS = CODIGO / "nucleo" / "puertos"


# --- Python puro ----------------------------------------------------------------------------------


def test_los_puertos_solo_importan_stdlib_pura_y_nucleo() -> None:
    permitidos = IMPORTS_PERMITIDOS_EN_DOMINIO | {"nucleo"}
    ajenos: list[str] = []
    for ruta in sorted(CARPETA_PUERTOS.glob("*.py")):
        for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Import):
                nombres = [alias.name for alias in nodo.names]
            elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0:
                nombres = [nodo.module or ""]
            else:
                continue
            ajenos += [
                f"{ruta.name}:{nodo.lineno}: {nombre}"
                for nombre in nombres
                if nombre.split(".")[0] not in permitidos
            ]
    assert not ajenos, f"nucleo/puertos es Python puro (DISENO 1.7): {ajenos}"


def test_todo_lo_exportado_existe() -> None:
    assert all(hasattr(puertos, nombre) for nombre in puertos.__all__)


# --- Errores de integración -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "reintentable"),
    [
        (ErrorTemporalDeIntegracion, True),
        (LimiteDeSolicitudes, True),
        (SolicitudRechazada, False),
        (ErrorDeIntegracion, False),
    ],
)
def test_los_errores_cuelgan_de_una_base_y_dicen_si_se_reintentan(
    error: type[ErrorDeIntegracion], reintentable: bool
) -> None:
    assert issubclass(error, ErrorDeIntegracion)
    assert error("x").reintentable is reintentable


@pytest.mark.parametrize("segundos", [0, 1, 60, 86_400])
def test_el_limite_acepta_de_0_a_86400_segundos_y_none(segundos: int) -> None:
    limite = LimiteDeSolicitudes("cuota", reintentar_en_segundos=segundos)
    assert limite.reintentar_en_segundos == segundos
    assert LimiteDeSolicitudes("cuota", reintentar_en_segundos=None).reintentar_en_segundos is None


@pytest.mark.parametrize("segundos", [-1, 86_401, 10**9, True, False, 1.5, 60.0, "60"])
def test_el_limite_rechaza_lo_que_no_es_un_entero_entre_0_y_86400(segundos: object) -> None:
    with pytest.raises(ValueError, match="reintentar_en_segundos"):
        LimiteDeSolicitudes("cuota", reintentar_en_segundos=segundos)  # type: ignore[arg-type]


# --- Registro -------------------------------------------------------------------------------------


@runtime_checkable
class PuertoDeEjemplo(Protocol):
    """Un puerto cualquiera, solo para probar el registro."""

    def consultar(self, clave: str) -> bool: ...


class _AdaptadorCualquiera:
    def consultar(self, clave: str) -> bool:
        return True


class _NoCumple:
    def otra_cosa(self) -> None:
        return None


@pytest.fixture
def registro_limpio() -> Iterator[None]:
    with Aislamiento():
        yield


def test_el_registro_devuelve_lo_que_se_conecto(registro_limpio: None) -> None:
    adaptador = _AdaptadorCualquiera()
    registro.conectar(PuertoDeEjemplo, adaptador)
    assert registro.obtener(PuertoDeEjemplo) is adaptador


def test_pedir_un_puerto_sin_adaptador_falla_con_un_mensaje_claro(registro_limpio: None) -> None:
    with pytest.raises(registro.PuertoSinAdaptador, match="PuertoDeEjemplo"):
        registro.obtener(PuertoDeEjemplo)


def test_conectar_dos_veces_el_mismo_puerto_falla_y_conserva_el_primero(
    registro_limpio: None,
) -> None:
    primero, segundo = _AdaptadorCualquiera(), _AdaptadorCualquiera()
    registro.conectar(PuertoDeEjemplo, primero)
    with pytest.raises(registro.PuertoYaConectado, match="PuertoDeEjemplo"):
        registro.conectar(PuertoDeEjemplo, segundo)
    assert registro.obtener(PuertoDeEjemplo) is primero


def test_el_aislamiento_es_el_camino_para_reemplazar_un_adaptador(registro_limpio: None) -> None:
    primero, segundo = _AdaptadorCualquiera(), _AdaptadorCualquiera()
    registro.conectar(PuertoDeEjemplo, primero)
    with Aislamiento():
        with pytest.raises(registro.PuertoSinAdaptador):
            registro.obtener(PuertoDeEjemplo)  # entra vacío
        registro.conectar(PuertoDeEjemplo, segundo)
        assert registro.obtener(PuertoDeEjemplo) is segundo
    assert registro.obtener(PuertoDeEjemplo) is primero  # al salir restaura lo que había


def test_el_aislamiento_restaura_aunque_la_prueba_falle(registro_limpio: None) -> None:
    adaptador = _AdaptadorCualquiera()
    registro.conectar(PuertoDeEjemplo, adaptador)
    with pytest.raises(RuntimeError, match="boom"), Aislamiento():
        raise RuntimeError("boom")
    assert registro.obtener(PuertoDeEjemplo) is adaptador


def test_pedir_un_puerto_sin_adaptador_no_es_un_lookup_error(registro_limpio: None) -> None:
    """Un `except LookupError` de quien consume el puerto no debe tragarse el error."""
    assert issubclass(registro.PuertoSinAdaptador, RuntimeError)
    assert not issubclass(registro.PuertoSinAdaptador, LookupError)
    with pytest.raises(registro.PuertoSinAdaptador):
        try:
            registro.obtener(PuertoDeEjemplo)
        except LookupError:  # pragma: no cover - no debe entrar aquí
            pytest.fail("PuertoSinAdaptador no debe heredar de LookupError")


def test_el_registro_de_produccion_no_ofrece_aislamiento() -> None:
    """`Aislamiento` es de pruebas y no vive en el paquete de producción."""
    assert not hasattr(registro, "Aislamiento")


def test_el_registro_rechaza_un_objeto_que_no_cumple_el_puerto(registro_limpio: None) -> None:
    with pytest.raises(TypeError, match="PuertoDeEjemplo"):
        registro.conectar(PuertoDeEjemplo, _NoCumple())
