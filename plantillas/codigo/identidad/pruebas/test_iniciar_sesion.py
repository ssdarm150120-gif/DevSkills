"""`IniciarSesion`: pruebas del caso de uso contra puertos falsos."""

import dataclasses
from datetime import timedelta

import pytest

from identidad.aplicacion.iniciar_sesion import IniciarSesion
from identidad.aplicacion.puertos import VerificadorSegundoFactor
from identidad.dominio.acceso import (
    DURACION_BLOQUEO,
    AccionDeCuenta,
    Etapa,
    Motivo,
    Resultado,
)
from identidad.pruebas.falsos import (
    AccesosEnMemoria,
    ContrasenasFalsas,
    CuentasEnMemoria,
    RelojFalso,
    VerificadorEnMemoria,
    cuenta,
)

CORRECTA = "caballo-grapa-9Lunar"
CORREO = "ana@empresa.example"


class Entorno:
    def __init__(self) -> None:
        self.cuentas = CuentasEnMemoria()
        self.accesos = AccesosEnMemoria()
        self.contrasenas = ContrasenasFalsas()
        self.reloj = RelojFalso()

    def ingresar(
        self,
        correo: str = CORREO,
        contrasena: str = CORRECTA,
        verificador: VerificadorSegundoFactor | None = None,
        ip: str = "10.0.0.7",
    ) -> Etapa:
        caso = IniciarSesion(self.cuentas, self.accesos, self.contrasenas, self.reloj, verificador)
        return caso(correo, contrasena, ip=ip).etapa

    def conteo(self) -> int:
        actual = self.cuentas.por_id("u-1")
        assert actual is not None
        return actual.fallos_contrasena

    def bloqueada_hasta(self) -> object:
        actual = self.cuentas.por_id("u-1")
        assert actual is not None
        return actual.bloqueada_hasta


@pytest.fixture
def entorno() -> Entorno:
    e = Entorno()
    e.cuentas.agregar(cuenta())
    return e


def test_ingreso_correcto_abre_sesion_y_queda_registrado(entorno: Entorno) -> None:
    assert entorno.ingresar() is Etapa.SESION_COMPLETA
    assert entorno.accesos.intentos == [
        {
            "usuario_id": "u-1",
            "resultado": Resultado.CORRECTO,
            "motivo": Motivo.CORRECTO,
            "ip": "10.0.0.7",
        }
    ]


def test_el_correo_no_distingue_mayusculas_ni_espacios(entorno: Entorno) -> None:
    assert entorno.ingresar(correo="  ANA@Empresa.Example ") is Etapa.SESION_COMPLETA


def test_contrasena_incorrecta_es_fallo_y_suma(entorno: Entorno) -> None:
    assert entorno.ingresar(contrasena="mala") is Etapa.FALLO
    assert entorno.conteo() == 1
    assert entorno.accesos.intentos[0]["motivo"] is Motivo.CONTRASENA_INCORRECTA


def test_correo_inexistente_es_fallo_registrado_y_gasta_el_mismo_tiempo(entorno: Entorno) -> None:
    assert entorno.ingresar(correo="nadie@empresa.example") is Etapa.FALLO
    assert entorno.contrasenas.ficticias == 1
    assert entorno.accesos.intentos == [
        {
            "usuario_id": None,
            "resultado": Resultado.FALLIDO,
            "motivo": Motivo.CORREO_INEXISTENTE,
            "ip": "10.0.0.7",
        }
    ]


def test_usuario_desactivado_es_fallo_aunque_la_contrasena_sea_correcta() -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta(activo=False))
    assert e.ingresar() is Etapa.FALLO
    assert e.accesos.intentos[0]["motivo"] is Motivo.USUARIO_DESACTIVADO
    assert e.contrasenas.verificaciones == 1  # el hash se calcula siempre


def test_cinco_fallos_bloquean_quince_minutos_y_queda_en_el_registro(entorno: Entorno) -> None:
    for _ in range(5):
        assert entorno.ingresar(contrasena="mala") is Etapa.FALLO
    assert entorno.bloqueada_hasta() == entorno.reloj.ahora() + DURACION_BLOQUEO
    assert entorno.accesos.acciones == [
        {"accion": AccionDeCuenta.BLOQUEO, "objetivo": "u-1", "hecha_por": None}
    ]


def test_bloqueada_ni_la_contrasena_correcta_entra_sin_importar_el_origen(
    entorno: Entorno,
) -> None:
    for _ in range(5):
        entorno.ingresar(contrasena="mala", ip="10.0.0.7")
    assert entorno.ingresar(ip="10.9.9.9") is Etapa.FALLO
    assert entorno.accesos.intentos[-1]["motivo"] is Motivo.CUENTA_BLOQUEADA


def test_pasados_quince_minutos_la_cuenta_vuelve_a_entrar(entorno: Entorno) -> None:
    for _ in range(5):
        entorno.ingresar(contrasena="mala")
    entorno.reloj.avanzar(minutes=15, seconds=1)
    assert entorno.ingresar() is Etapa.SESION_COMPLETA


def test_un_ingreso_correcto_pone_el_conteo_en_cero(entorno: Entorno) -> None:
    for _ in range(4):
        entorno.ingresar(contrasena="mala")
    assert entorno.ingresar() is Etapa.SESION_COMPLETA
    assert entorno.conteo() == 0
    for _ in range(4):
        entorno.ingresar(contrasena="mala")
    assert entorno.ingresar() is Etapa.SESION_COMPLETA  # cuatro fallos nuevos no bloquean


def test_la_cuenta_bloqueada_no_extiende_el_bloqueo_con_mas_fallos(entorno: Entorno) -> None:
    for _ in range(5):
        entorno.ingresar(contrasena="mala")
    antes = entorno.bloqueada_hasta()
    entorno.reloj.avanzar(minutes=5)
    entorno.ingresar(contrasena="mala")
    assert entorno.bloqueada_hasta() == antes
    restante = antes - entorno.reloj.ahora()  # type: ignore[operator]
    assert restante == DURACION_BLOQUEO - timedelta(minutes=5)


# --- Falla cerrado para roles con segundo factor ---------------------------------------------


@pytest.mark.parametrize("rol", ["administrador", "auditor", "auditor", "auditor"])
def test_rol_sensible_sin_adaptador_no_entra_con_solo_la_contrasena(rol: str) -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta(roles=frozenset({rol}), exige_segundo_factor=True))
    assert e.ingresar() is Etapa.RECHAZADO_POR_SEGUNDO_FACTOR
    assert e.accesos.intentos[-1]["motivo"] is Motivo.REQUIERE_SEGUNDO_FACTOR


def test_rol_sensible_con_adaptador_no_disponible_tambien_se_rechaza() -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta(roles=frozenset({"auditor"}), exige_segundo_factor=True))
    assert (
        e.ingresar(verificador=VerificadorEnMemoria(disponible=False))
        is Etapa.RECHAZADO_POR_SEGUNDO_FACTOR
    )
    assert e.accesos.intentos[-1]["motivo"] is Motivo.REQUIERE_SEGUNDO_FACTOR


def test_rol_sensible_con_adaptador_disponible_y_ya_enrolado_pide_el_codigo() -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta(roles=frozenset({"auditor"}), exige_segundo_factor=True))
    verificador = VerificadorEnMemoria(enrolados=frozenset({"u-1"}))
    caso = IniciarSesion(e.cuentas, e.accesos, e.contrasenas, e.reloj, verificador)
    resultado = caso(CORREO, CORRECTA, ip="10.0.0.7")
    assert (resultado.etapa, resultado.usuario_id) == (Etapa.CODIGO_PENDIENTE, "u-1")
    assert resultado.sello_sesion == "sello-0"  # la etapa guarda el sello para revalidar
    assert e.accesos.intentos[-1]["motivo"] is Motivo.CORRECTO  # la contrasena fue correcta


def test_rol_sensible_sin_segundo_factor_pasa_al_enrolamiento() -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta(roles=frozenset({"auditor"}), exige_segundo_factor=True))
    assert e.ingresar(verificador=VerificadorEnMemoria()) is Etapa.ENROLAMIENTO_PENDIENTE


def test_rol_no_sensible_no_pide_codigo_aunque_haya_adaptador() -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta(roles=frozenset({"usuario"})))
    assert e.ingresar(verificador=VerificadorEnMemoria()) is Etapa.SESION_COMPLETA


def test_el_falla_cerrado_se_evalua_antes_que_el_cambio_de_contrasena_temporal() -> None:
    e = Entorno()
    e.cuentas.agregar(
        cuenta(
            roles=frozenset({"auditor"}),
            exige_segundo_factor=True,
            debe_cambiar_contrasena=True,
        )
    )
    assert e.ingresar() is Etapa.RECHAZADO_POR_SEGUNDO_FACTOR


def test_el_orden_con_temporal_y_adaptador_es_cambio_obligatorio_y_despues_el_segundo_factor() -> (
    None
):
    """D.3.10: contrasena, cambio obligatorio, enrolamiento y codigo. Con el adaptador conectado,
    el cambio obligatorio va PRIMERO (el falla cerrado solo aplica sin adaptador)."""
    e = Entorno()
    e.cuentas.agregar(
        cuenta(
            roles=frozenset({"auditor"}),
            exige_segundo_factor=True,
            debe_cambiar_contrasena=True,
        )
    )
    caso = IniciarSesion(e.cuentas, e.accesos, e.contrasenas, e.reloj, VerificadorEnMemoria())
    resultado = caso(CORREO, CORRECTA, ip="10.0.0.7")
    assert (resultado.etapa, resultado.sello_sesion) == (Etapa.CAMBIO_OBLIGATORIO, "sello-0")


def test_con_contrasena_mala_un_rol_sensible_es_un_fallo_comun_sin_revelar_el_rol() -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta(roles=frozenset({"auditor"}), exige_segundo_factor=True))
    assert e.ingresar(contrasena="mala") is Etapa.FALLO


# --- Contrasena temporal ------------------------------------------------------------------------


def test_con_contrasena_temporal_solo_se_puede_cambiarla() -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta(debe_cambiar_contrasena=True))
    assert e.ingresar() is Etapa.CAMBIO_OBLIGATORIO


# --- Correos imposibles y rehash de Argon2 -----------------------------------


@pytest.mark.parametrize(
    "correo",
    ["a\x00b@empresa.example", "a\nb@empresa.example", "a" * 300 + "@empresa.example", ""],
)
def test_un_correo_imposible_es_un_fallo_comun_registrado_y_con_el_mismo_trabajo(
    entorno: Entorno, correo: str
) -> None:
    assert entorno.ingresar(correo=correo) is Etapa.FALLO
    assert entorno.contrasenas.ficticias == 1  # el mismo hash de siempre
    assert entorno.accesos.intentos[-1]["motivo"] is Motivo.CORREO_INEXISTENTE
    assert entorno.accesos.intentos[-1]["usuario_id"] is None


def test_un_correo_largo_no_se_trunca_para_coincidir_con_otro() -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta(correo="a" * 254))
    assert e.ingresar(correo="a" * 254 + "b") is Etapa.FALLO


def test_con_hash_de_parametros_viejos_se_actualiza_al_ingresar_sin_cambiar_el_sello() -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta(contrasena="x"))
    e.cuentas.cuentas["u-1"] = dataclasses.replace(
        e.cuentas.cuentas["u-1"], hash_contrasena="viejo$hash$caballo-grapa-9Lunar"
    )
    e.contrasenas.verificar = lambda c, h: True  # type: ignore[method-assign,assignment]
    assert e.ingresar() is Etapa.SESION_COMPLETA
    assert e.cuentas.por_id("u-1").hash_contrasena == "hash$caballo-grapa-9Lunar"  # type: ignore[union-attr]
    assert e.cuentas.sellos["u-1"] == 0  # el sello no cambio: las sesiones siguen vivas
    assert e.cuentas.por_id("u-1").sello_sesion == "sello-0"  # type: ignore[union-attr]


def test_con_contrasena_incorrecta_no_se_actualiza_el_hash() -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta(contrasena="x"))
    e.cuentas.cuentas["u-1"] = dataclasses.replace(
        e.cuentas.cuentas["u-1"], hash_contrasena="viejo$hash$otra"
    )
    assert e.ingresar() is Etapa.FALLO
    assert e.cuentas.por_id("u-1").hash_contrasena == "viejo$hash$otra"  # type: ignore[union-attr]


def test_el_resultado_de_la_etapa_obligatoria_lleva_el_sello() -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta(debe_cambiar_contrasena=True))
    caso = IniciarSesion(e.cuentas, e.accesos, e.contrasenas, e.reloj)
    assert caso(CORREO, CORRECTA, ip="10.0.0.7").sello_sesion == "sello-0"
