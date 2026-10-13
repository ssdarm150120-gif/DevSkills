"""`DefinirContrasena` y `CrearAdministrador` (escenarios 6, 7 y 8, D.3.10), contra
falsos."""

from typing import Any

import pytest

from identidad.aplicacion.crear_administrador import AltaInvalida, CrearAdministrador
from identidad.aplicacion.definir_contrasena import (
    ContrasenaActualIncorrecta,
    ContrasenaInvalida,
    CuentaNoDisponible,
    DefinirContrasena,
    EtapaInvalida,
    RequiereSegundoFactor,
    ResultadoDefinicion,
)
from identidad.aplicacion.iniciar_sesion import IniciarSesion
from identidad.dominio.acceso import AccionDeCuenta, Etapa, Intencion, Motivo
from identidad.pruebas.falsos import (
    AccesosEnMemoria,
    ContrasenasFalsas,
    CuentasEnMemoria,
    RelojFalso,
    VerificadorEnMemoria,
    cuenta,
)

ACTUAL = "caballo-grapa-9Lunar"
NUEVA = "otra-frase-larga-77Sol"


class Entorno:
    def __init__(self) -> None:
        self.cuentas = CuentasEnMemoria()
        self.accesos = AccesosEnMemoria()
        self.contrasenas = ContrasenasFalsas()
        self.reloj = RelojFalso()

    def definir(
        self,
        usuario_id: str = "u-1",
        nueva: str = NUEVA,
        actual: str | None = None,
        intencion: Intencion = Intencion.CAMBIO_PROPIO,
        sello: str | None = None,
        verificador: object = None,
    ) -> ResultadoDefinicion:
        return DefinirContrasena(
            self.cuentas,
            self.accesos,
            self.contrasenas,
            self.reloj,
            verificador,  # type: ignore[arg-type]
        )(
            usuario_id,
            nueva,
            intencion=intencion,
            contrasena_actual=actual,
            sello_esperado=sello,
            ip="10.0.0.7",
        )

    def definir_obligatorio(
        self, nueva: str = NUEVA, sello: str | None = "sello-0", verificador: object = None
    ) -> ResultadoDefinicion:
        return self.definir(
            nueva=nueva,
            intencion=Intencion.CAMBIO_OBLIGATORIO,
            sello=sello,
            verificador=verificador,
        )

    def ingresar(self, contrasena: str) -> Etapa:
        caso = IniciarSesion(self.cuentas, self.accesos, self.contrasenas, self.reloj)
        return caso("ana@empresa.example", contrasena, ip="10.0.0.7").etapa


@pytest.fixture
def entorno() -> Entorno:
    e = Entorno()
    e.cuentas.agregar(cuenta())
    return e


# --- Escenario "Cambiar mi propia contrasena" -------------------------------------------------


def test_cambiar_la_propia_pide_la_actual_y_cambia_el_hash(entorno: Entorno) -> None:
    entorno.definir(actual=ACTUAL)
    assert entorno.ingresar(ACTUAL) is Etapa.FALLO
    assert entorno.ingresar(NUEVA) is Etapa.SESION_COMPLETA


def test_el_cambio_cambia_el_sello_de_sesion_y_queda_registrado(entorno: Entorno) -> None:
    entorno.definir(actual=ACTUAL)
    assert entorno.cuentas.sellos["u-1"] == 1
    assert entorno.accesos.acciones == [
        {"accion": AccionDeCuenta.CAMBIO_DE_CONTRASENA, "objetivo": "u-1", "hecha_por": "u-1"}
    ]


def test_sin_la_actual_o_con_una_incorrecta_no_cambia(entorno: Entorno) -> None:
    with pytest.raises(ContrasenaActualIncorrecta):
        entorno.definir(actual=None)
    with pytest.raises(ContrasenaActualIncorrecta):
        entorno.definir(actual="mala")
    assert entorno.ingresar(ACTUAL) is Etapa.SESION_COMPLETA
    assert entorno.accesos.intentos[0]["motivo"] is Motivo.CAMBIO_DE_CONTRASENA_INCORRECTA


def test_cinco_actuales_incorrectas_bloquean_la_cuenta(entorno: Entorno) -> None:
    for _ in range(5):
        with pytest.raises(ContrasenaActualIncorrecta):
            entorno.definir(actual="mala")
    assert entorno.ingresar(ACTUAL) is Etapa.FALLO  # bloqueada
    with pytest.raises(ContrasenaActualIncorrecta):
        entorno.definir(actual=ACTUAL)  # ni siquiera con la correcta mientras dura el bloqueo


# --- Escenario "Contrasena robusta" -----------------------------------------------------------


def test_una_contrasena_corta_se_rechaza_con_su_motivo(entorno: Entorno) -> None:
    with pytest.raises(ContrasenaInvalida) as error:
        entorno.definir(nueva="corta", actual=ACTUAL)
    assert "al menos 12 caracteres" in error.value.errores[0]


def test_una_contrasena_filtrada_se_rechaza(entorno: Entorno) -> None:
    with pytest.raises(ContrasenaInvalida) as error:
        entorno.definir(nueva="contrasena1234", actual=ACTUAL)
    assert any("filtradas" in e for e in error.value.errores)


def test_la_nueva_no_puede_ser_igual_a_la_actual(entorno: Entorno) -> None:
    with pytest.raises(ContrasenaInvalida):
        entorno.definir(nueva=ACTUAL, actual=ACTUAL)


def test_una_contrasena_rechazada_no_cambia_nada(entorno: Entorno) -> None:
    with pytest.raises(ContrasenaInvalida):
        entorno.definir(nueva="corta", actual=ACTUAL)
    assert entorno.cuentas.sellos["u-1"] == 0
    assert entorno.accesos.acciones == []


# --- Escenario "Contrasena temporal en el primer ingreso" -------------------------------------


def test_con_temporal_no_pide_la_actual_y_la_temporal_deja_de_servir() -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta(debe_cambiar_contrasena=True))
    assert e.ingresar(ACTUAL) is Etapa.CAMBIO_OBLIGATORIO
    e.definir_obligatorio()
    assert e.ingresar(ACTUAL) is Etapa.FALLO  # la temporal ya no sirve
    assert e.ingresar(NUEVA) is Etapa.SESION_COMPLETA  # y ya no hay cambio obligatorio


def test_la_nueva_debe_cumplir_la_politica_tambien_en_el_primer_ingreso() -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta(debe_cambiar_contrasena=True))
    with pytest.raises(ContrasenaInvalida):
        e.definir_obligatorio(nueva="corta")
    assert e.ingresar(ACTUAL) is Etapa.CAMBIO_OBLIGATORIO  # sigue pendiente


def test_una_cuenta_inexistente_o_desactivada_no_puede_definir() -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta(activo=False))
    with pytest.raises(CuentaNoDisponible):
        e.definir()
    with pytest.raises(CuentaNoDisponible):
        e.definir(usuario_id="no-existe")


# --- Alta del primer Administrador ------------------------------------------------------------


def _alta(e: Entorno) -> CrearAdministrador:
    return CrearAdministrador(e.cuentas, e.accesos, e.contrasenas, e.reloj)


def test_crear_administrador_da_contrasena_temporal_y_lo_registra() -> None:
    e = Entorno()
    usuario_id, temporal = _alta(e)("  Root@Empresa.Example ")
    creada = e.cuentas.por_id(usuario_id)
    assert creada is not None
    assert (creada.correo, creada.roles, creada.debe_cambiar_contrasena) == (
        "root@empresa.example",
        frozenset({"administrador"}),
        True,
    )
    assert creada.hash_contrasena == e.contrasenas.hashear(temporal)
    assert e.accesos.acciones == [
        {
            "accion": AccionDeCuenta.ALTA,
            "objetivo": usuario_id,
            "hecha_por": None,
            "detalle": {"roles": ["administrador"]},
        }
    ]


@pytest.mark.parametrize("correo", ["", "sin-arroba", "a@b", "a b@c.d"])
def test_crear_administrador_rechaza_un_correo_invalido(correo: str) -> None:
    with pytest.raises(AltaInvalida):
        _alta(Entorno())(correo)


def test_crear_administrador_rechaza_un_correo_repetido_sin_distinguir_mayusculas() -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta())
    with pytest.raises(AltaInvalida):
        _alta(e)("ANA@empresa.example")


# --- Intencion explicita y revalidacion de la etapa pendiente ---------------------


def _con_temporal(**cambios: Any) -> Entorno:
    e = Entorno()
    e.cuentas.agregar(cuenta(debe_cambiar_contrasena=True, **cambios))
    return e


def test_el_cambio_propio_siempre_pide_la_actual_aunque_la_cuenta_tenga_temporal() -> None:
    e = _con_temporal()
    with pytest.raises(ContrasenaActualIncorrecta):
        e.definir(intencion=Intencion.CAMBIO_PROPIO, actual=None)
    assert e.cuentas.por_id("u-1").debe_cambiar_contrasena  # type: ignore[union-attr]


def test_el_cambio_obligatorio_solo_vale_si_la_cuenta_tiene_temporal() -> None:
    e = Entorno()
    e.cuentas.agregar(cuenta())  # contrasena normal
    with pytest.raises(EtapaInvalida):
        e.definir_obligatorio(sello="sello-0")
    assert e.cuentas.sellos["u-1"] == 0


def test_el_cambio_obligatorio_exige_el_sello_con_el_que_se_abrio_la_etapa() -> None:
    e = _con_temporal()
    with pytest.raises(EtapaInvalida):
        e.definir_obligatorio(sello=None)
    with pytest.raises(EtapaInvalida):
        e.definir_obligatorio(sello="otro")


def test_si_reinician_la_temporal_con_la_etapa_abierta_no_se_completa() -> None:
    e = _con_temporal()
    # El Administrador reinicia la temporal: el sello cambia.
    e.cuentas.guardar_contrasena("u-1", "hash$otra-temporal", temporal=True, ahora=e.reloj.ahora())
    with pytest.raises(EtapaInvalida):
        e.definir_obligatorio(sello="sello-0")
    assert e.cuentas.por_id("u-1").hash_contrasena == "hash$otra-temporal"  # type: ignore[union-attr]


def test_si_con_la_etapa_abierta_el_usuario_pasa_a_un_rol_sensible_no_se_completa() -> None:
    e = _con_temporal(exige_segundo_factor=True)  # roles de AHORA: ya exige segundo factor
    with pytest.raises(RequiereSegundoFactor):
        e.definir_obligatorio()
    assert e.cuentas.por_id("u-1").debe_cambiar_contrasena  # type: ignore[union-attr]
    assert e.accesos.acciones == []  # no cambio nada


def test_la_etapa_de_un_rol_sensible_se_completa_si_el_segundo_factor_esta_disponible() -> None:
    e = _con_temporal(exige_segundo_factor=True)
    e.definir_obligatorio(verificador=VerificadorEnMemoria())
    assert not e.cuentas.por_id("u-1").debe_cambiar_contrasena  # type: ignore[union-attr]


def test_despues_del_cambio_obligatorio_un_rol_sensible_sigue_con_el_enrolamiento() -> None:
    """D.3.10: contrasena, cambio obligatorio, ENROLAMIENTO (si no tiene segundo factor), codigo."""
    e = _con_temporal(exige_segundo_factor=True)
    resultado = e.definir_obligatorio(verificador=VerificadorEnMemoria())
    assert resultado.etapa is Etapa.ENROLAMIENTO_PENDIENTE
    # Lleva el sello NUEVO (la contrasena lo cambio): la etapa siguiente lo guarda y lo compara.
    assert resultado.sello_sesion == e.cuentas.por_id("u-1").sello_sesion  # type: ignore[union-attr]
    assert resultado.sello_sesion != "sello-0"


def test_despues_del_cambio_obligatorio_un_rol_sensible_ya_enrolado_pide_el_codigo() -> None:
    e = _con_temporal(exige_segundo_factor=True)
    resultado = e.definir_obligatorio(
        verificador=VerificadorEnMemoria(enrolados=frozenset({"u-1"}))
    )
    assert resultado.etapa is Etapa.CODIGO_PENDIENTE


def test_despues_del_cambio_obligatorio_un_rol_comun_entra() -> None:
    e = _con_temporal()
    resultado = e.definir_obligatorio(verificador=VerificadorEnMemoria())
    assert (resultado.etapa, resultado.sello_sesion) == (Etapa.SESION_COMPLETA, None)


def test_el_cambio_propio_siempre_termina_en_sesion_completa(entorno: Entorno) -> None:
    resultado = entorno.definir(actual=ACTUAL)
    assert resultado.etapa is Etapa.SESION_COMPLETA


def test_el_cambio_obligatorio_de_una_cuenta_desactivada_no_se_completa() -> None:
    e = _con_temporal(activo=False)
    with pytest.raises(CuentaNoDisponible):
        e.definir_obligatorio()


# --- Alta del Administrador: correo ---------------------------------------------------


@pytest.mark.parametrize("correo", ["a" * 250 + "@x.co", "ro\x00ot@empresa.example"])
def test_crear_administrador_rechaza_un_correo_largo_o_con_control(correo: str) -> None:
    with pytest.raises(AltaInvalida, match="correo"):
        _alta(Entorno())(correo)
