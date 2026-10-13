"""`ConfirmarCodigo`, `IniciarEnrolamiento` y `ReiniciarSegundoFactor`, contra falsos."""

from datetime import timedelta
from typing import Any

import pytest

from identidad.aplicacion.confirmar_codigo import ConfirmarCodigo, ResultadoConfirmacion
from identidad.aplicacion.errores import (
    CuentaBloqueada,
    CuentaNoDisponible,
    EtapaInvalida,
    RequiereSegundoFactor,
)
from identidad.aplicacion.iniciar_enrolamiento import IniciarEnrolamiento
from identidad.aplicacion.puertos import Cuenta, Enrolamiento, VerificadorSegundoFactor
from identidad.aplicacion.reiniciar_segundo_factor import PermisoDenegado, ReiniciarSegundoFactor
from identidad.dominio.acceso import DURACION_BLOQUEO, AccionDeCuenta, Factor, Motivo, Resultado
from identidad.pruebas.falsos import (
    AccesosEnMemoria,
    ContrasenasFalsas,
    CuentasEnMemoria,
    RelojFalso,
    VerificadorEnMemoria,
    cuenta,
)
from nucleo.actor import Actor

BUENO = VerificadorEnMemoria.CODIGO_BUENO
MALO = "000000"


class Entorno:
    def __init__(self, *, enrolado: bool = True, **cambios: Any) -> None:
        self.cuentas = CuentasEnMemoria()
        self.accesos = AccesosEnMemoria()
        self.contrasenas = ContrasenasFalsas()
        self.reloj = RelojFalso()
        self.verificador = VerificadorEnMemoria(
            enrolados=frozenset({"u-1"}) if enrolado else frozenset()
        )
        base: dict[str, Any] = {"roles": frozenset({"auditor"}), "exige_segundo_factor": True}
        self.cuentas.agregar(cuenta(**{**base, **cambios}))

    def confirmar(
        self,
        codigo: str = BUENO,
        *,
        sello: str | None = "sello-0",
        enrolando: bool = False,
        verificador: str | VerificadorSegundoFactor | None = "propio",
    ) -> ResultadoConfirmacion:
        usado = self.verificador if verificador == "propio" else verificador
        caso = ConfirmarCodigo(self.cuentas, self.accesos, self.reloj, usado)  # type: ignore[arg-type]
        return caso("u-1", codigo, sello_esperado=sello, enrolando=enrolando, ip="10.0.0.7")

    @property
    def actual(self) -> Cuenta:
        cuenta_actual = self.cuentas.por_id("u-1")
        assert cuenta_actual is not None
        return cuenta_actual


# --- Codigo correcto ---------------------------------------------------------------------------


def test_un_codigo_correcto_se_acepta_y_queda_registrado() -> None:
    e = Entorno()
    assert e.confirmar() is ResultadoConfirmacion.ACEPTADO
    assert e.accesos.intentos == [
        {
            "usuario_id": "u-1",
            "resultado": Resultado.CORRECTO,
            "motivo": Motivo.CORRECTO,
            "ip": "10.0.0.7",
        }
    ]


def test_el_codigo_acepta_los_separadores_que_muestran_las_aplicaciones() -> None:
    assert Entorno().confirmar("123 456") is ResultadoConfirmacion.ACEPTADO


def test_un_codigo_valido_pone_el_contador_en_cero() -> None:
    e = Entorno(fallos_codigo=3)
    assert e.confirmar() is ResultadoConfirmacion.ACEPTADO
    assert e.actual.fallos_codigo == 0


# --- Codigo incorrecto y repetido -----------------------------------------------------------------


def test_un_codigo_incorrecto_suma_un_fallo_y_se_puede_reintentar() -> None:
    e = Entorno()
    assert e.confirmar(MALO) is ResultadoConfirmacion.INCORRECTO
    assert e.actual.fallos_codigo == 1
    assert e.accesos.intentos[-1]["motivo"] is Motivo.CODIGO_INVALIDO
    assert e.confirmar() is ResultadoConfirmacion.ACEPTADO  # el bueno todavia sirve


@pytest.mark.parametrize("basura", ["", "abc", "12345", "1234567", "<script>", "٠٠٠٠٠٠"])
def test_un_codigo_mal_escrito_tambien_cuenta_como_fallo(basura: str) -> None:
    """Mandar basura no esquiva el limite de intentos."""
    e = Entorno()
    assert e.confirmar(basura) is ResultadoConfirmacion.INCORRECTO
    assert e.actual.fallos_codigo == 1
    assert e.accesos.intentos[-1]["motivo"] is Motivo.CODIGO_INVALIDO


def test_un_codigo_ya_usado_se_rechaza_con_su_motivo_y_cuenta_como_fallo() -> None:
    e = Entorno()
    assert e.confirmar() is ResultadoConfirmacion.ACEPTADO
    assert e.confirmar() is ResultadoConfirmacion.INCORRECTO  # "alguien" repite el codigo
    assert e.accesos.intentos[-1]["motivo"] is Motivo.CODIGO_REPETIDO
    assert e.actual.fallos_codigo == 1


# --- Limite de intentos (5 seguidos bloquean 15 minutos; contador separado) -----------------------


def test_cinco_codigos_incorrectos_seguidos_bloquean_la_cuenta_quince_minutos() -> None:
    e = Entorno()
    for _ in range(4):
        assert e.confirmar(MALO) is ResultadoConfirmacion.INCORRECTO
    assert e.confirmar(MALO) is ResultadoConfirmacion.BLOQUEADA
    assert e.actual.bloqueada_hasta == e.reloj.ahora() + DURACION_BLOQUEO
    assert e.actual.fallos_codigo == 0  # el siguiente ciclo empieza limpio
    assert e.accesos.acciones == [
        {"accion": AccionDeCuenta.BLOQUEO, "objetivo": "u-1", "hecha_por": None}
    ]
    # Los cinco intentos quedaron registrados, con su factor.
    assert [i["motivo"] for i in e.accesos.intentos] == [Motivo.CODIGO_INVALIDO] * 5


def test_bloqueada_ni_el_codigo_correcto_pasa_y_ni_se_consulta_al_verificador() -> None:
    e = Entorno()
    for _ in range(5):
        e.confirmar(MALO)
    assert e.confirmar() is ResultadoConfirmacion.BLOQUEADA
    assert e.accesos.intentos[-1]["motivo"] is Motivo.CUENTA_BLOQUEADA
    assert e.verificador.usados == set()  # el bueno ni se probo


def test_el_contador_del_codigo_es_independiente_del_de_la_contrasena() -> None:
    """4 fallos de contrasena y 4 de codigo NO suman 8: cada contador es de 5."""
    e = Entorno(fallos_contrasena=4)
    for _ in range(4):
        assert e.confirmar(MALO) is ResultadoConfirmacion.INCORRECTO
    assert e.actual.bloqueada_hasta is None
    assert (e.actual.fallos_contrasena, e.actual.fallos_codigo) == (4, 4)


def test_los_fallos_del_codigo_no_tocan_el_contador_de_la_contrasena() -> None:
    e = Entorno()
    e.confirmar(MALO)
    assert (e.actual.fallos_contrasena, e.actual.fallos_codigo) == (0, 1)


def test_los_fallos_se_acumulan_entre_ingresos_hasta_un_codigo_valido() -> None:
    """Re-ingresar con la contrasena no reinicia el contador del codigo: solo un codigo valido."""
    e = Entorno()
    for _ in range(3):
        e.confirmar(MALO)
    assert e.actual.fallos_codigo == 3
    for _ in range(2):  # el segundo ingreso suma sobre los 3 de antes
        resultado = e.confirmar(MALO)
    assert resultado is ResultadoConfirmacion.BLOQUEADA


# --- Enrolamiento --------------------------------------------------------------------------------


def test_confirmar_el_enrolamiento_con_un_codigo_valido_lo_deja_registrado() -> None:
    e = Entorno(enrolado=False)
    assert e.confirmar(enrolando=True) is ResultadoConfirmacion.ACEPTADO
    assert e.verificador.esta_enrolado("u-1")
    assert e.accesos.acciones == [
        {
            "accion": AccionDeCuenta.ENROLAMIENTO_SEGUNDO_FACTOR,
            "objetivo": "u-1",
            "hecha_por": "u-1",
        }
    ]
    assert e.accesos.intentos[-1]["resultado"] is Resultado.CORRECTO


def test_un_codigo_malo_en_el_enrolamiento_no_lo_confirma_y_cuenta_como_fallo() -> None:
    e = Entorno(enrolado=False)
    assert e.confirmar(MALO, enrolando=True) is ResultadoConfirmacion.INCORRECTO
    assert not e.verificador.esta_enrolado("u-1")
    assert e.actual.fallos_codigo == 1
    assert e.accesos.acciones == []


def test_cinco_codigos_malos_en_el_enrolamiento_tambien_bloquean() -> None:
    e = Entorno(enrolado=False)
    resultados = [e.confirmar(MALO, enrolando=True) for _ in range(5)]
    assert resultados[-1] is ResultadoConfirmacion.BLOQUEADA
    assert e.actual.bloqueada_hasta is not None


def test_el_intento_de_codigo_se_registra_con_el_factor_codigo() -> None:
    e = Entorno()
    registrados: list[Factor] = []
    original = e.accesos.registrar_intento

    def espia(**datos: object) -> None:
        registrados.append(datos["factor"])  # type: ignore[arg-type]
        original(**datos)  # type: ignore[arg-type]

    e.accesos.registrar_intento = espia  # type: ignore[method-assign,assignment]
    e.confirmar(MALO)
    e.confirmar()
    assert registrados == [Factor.CODIGO, Factor.CODIGO]


# --- Revalidacion de la etapa (D.3.10): el caso de uso vuelve a comprobar todo -------------------


def test_con_otro_sello_la_etapa_ya_no_es_valida() -> None:
    e = Entorno()
    e.cuentas.rotar_sello("u-1")  # por ejemplo, el Administrador restablecio la contrasena
    with pytest.raises(EtapaInvalida):
        e.confirmar()
    assert e.verificador.usados == set()


def test_sin_sello_la_etapa_no_es_valida() -> None:
    with pytest.raises(EtapaInvalida):
        Entorno().confirmar(sello=None)


def test_si_el_rol_sensible_se_quito_la_etapa_ya_no_es_valida() -> None:
    e = Entorno(roles=frozenset({"usuario"}), exige_segundo_factor=False)
    with pytest.raises(EtapaInvalida):
        e.confirmar()


def test_una_cuenta_desactivada_no_completa_la_etapa() -> None:
    with pytest.raises(CuentaNoDisponible):
        Entorno(activo=False).confirmar()


def test_sin_adaptador_falla_cerrado_y_registra_el_intento() -> None:
    e = Entorno()
    with pytest.raises(RequiereSegundoFactor):
        e.confirmar(verificador=None)
    assert e.accesos.intentos[-1]["motivo"] is Motivo.REQUIERE_SEGUNDO_FACTOR


def test_con_el_adaptador_no_disponible_falla_cerrado() -> None:
    e = Entorno()
    e.verificador.disponible = False  # por ejemplo, la llave cambio y el secreto no se descifra
    with pytest.raises(RequiereSegundoFactor):
        e.confirmar()


def test_no_se_pide_el_codigo_a_quien_todavia_debe_enrolarse() -> None:
    with pytest.raises(EtapaInvalida):
        Entorno(enrolado=False).confirmar(enrolando=False)


def test_no_se_enrola_a_quien_ya_tiene_segundo_factor() -> None:
    with pytest.raises(EtapaInvalida):
        Entorno(enrolado=True).confirmar(enrolando=True)


def test_el_bloqueo_pasado_deja_confirmar_de_nuevo_en_otra_etapa() -> None:
    e = Entorno()
    for _ in range(5):
        e.confirmar(MALO)
    e.reloj.avanzar(minutes=15, seconds=1)
    assert e.confirmar() is ResultadoConfirmacion.ACEPTADO


# --- IniciarEnrolamiento -------------------------------------------------------------------------


def _iniciar(e: Entorno, *, sello: str | None = "sello-0") -> object:
    caso = IniciarEnrolamiento(e.cuentas, e.accesos, e.reloj, e.verificador)
    return caso("u-1", sello_esperado=sello, ip="10.0.0.7")


def test_iniciar_el_enrolamiento_devuelve_la_clave_y_el_uri() -> None:
    material = _iniciar(Entorno(enrolado=False))
    assert material.clave == "ABCDEFGH"  # type: ignore[attr-defined]
    assert material.uri.startswith("otpauth://totp/")  # type: ignore[attr-defined]


def test_iniciar_el_enrolamiento_pasa_el_momento_del_reloj_inyectado_al_adaptador() -> None:
    e = Entorno(enrolado=False)
    _iniciar(e)
    assert e.verificador.enrolamientos == [("u-1", e.reloj.ahora())]


def test_el_secreto_del_enrolamiento_no_sale_en_el_repr() -> None:
    """la clave y el URI son el secreto en claro; no deben salir en trazas ni en logs."""
    material = Enrolamiento(clave="JBSWY3DPEHPK3PXP", uri="otpauth://totp/App:a?secret=JBSWY3DP")
    texto = f"{material!r} {material}"
    assert "JBSWY3DP" not in texto
    assert "otpauth" not in texto
    assert material.clave == "JBSWY3DPEHPK3PXP"  # sigue disponible para quien lo muestra


def test_iniciar_el_enrolamiento_revalida_la_etapa() -> None:
    e = Entorno(enrolado=False)
    with pytest.raises(EtapaInvalida):
        _iniciar(e, sello="otro")
    with pytest.raises(EtapaInvalida):
        _iniciar(Entorno(enrolado=True))  # ya tiene segundo factor


def test_iniciar_el_enrolamiento_de_una_cuenta_bloqueada_no_se_permite() -> None:
    e = Entorno(enrolado=False)
    for _ in range(5):
        e.confirmar(MALO, enrolando=True)
    with pytest.raises(CuentaBloqueada):
        _iniciar(e)


# --- ReiniciarSegundoFactor --------------------------------------

ADMIN = Actor.de("a-1", ["administrador"])


def _reiniciar(e: Entorno, actor: Actor = ADMIN, objetivo: str = "u-1") -> bool:
    caso = ReiniciarSegundoFactor(e.cuentas, e.accesos, e.reloj, e.verificador)
    return caso(actor, objetivo)


def test_reiniciar_borra_el_segundo_factor_y_rota_el_sello() -> None:
    e = Entorno()
    assert _reiniciar(e) is True
    assert not e.verificador.esta_enrolado("u-1")
    assert e.actual.sello_sesion != "sello-0"  # cierra las sesiones y las etapas pendientes


def test_reiniciar_deja_el_registro_sin_el_secreto() -> None:
    e = Entorno()
    _reiniciar(e)
    assert e.accesos.acciones == [
        {"accion": AccionDeCuenta.REINICIO_SEGUNDO_FACTOR, "objetivo": "u-1", "hecha_por": "a-1"}
    ]


def test_despues_de_reiniciar_la_etapa_pendiente_anterior_deja_de_valer() -> None:
    e = Entorno()
    _reiniciar(e)
    with pytest.raises(EtapaInvalida):
        e.confirmar()  # la etapa se abrio con "sello-0"


def test_reiniciar_a_quien_no_tenia_segundo_factor_avisa_que_no_habia() -> None:
    assert _reiniciar(Entorno(enrolado=False)) is False


def test_reiniciar_pone_en_cero_el_contador_del_codigo_pero_no_desbloquea() -> None:
    e = Entorno(fallos_codigo=3)
    _reiniciar(e)
    assert e.actual.fallos_codigo == 0
    e2 = Entorno()
    for _ in range(5):
        e2.confirmar(MALO)
    bloqueo = e2.actual.bloqueada_hasta
    _reiniciar(e2)
    assert e2.actual.bloqueada_hasta == bloqueo  # desbloquear es otra accion


def test_solo_un_administrador_puede_reiniciar() -> None:
    e = Entorno()
    for rol in ("usuario", "auditor", "usuario", "auditor"):
        with pytest.raises(PermisoDenegado):
            _reiniciar(e, Actor.de("x-1", [rol]))
    assert e.verificador.reinicios == []


def test_nadie_reinicia_el_segundo_factor_de_su_propia_cuenta_de_administrador() -> None:
    e = Entorno(roles=frozenset({"administrador"}))
    with pytest.raises(PermisoDenegado):
        _reiniciar(e, Actor.de("u-1", ["administrador"]))
    assert e.verificador.reinicios == []
    assert _reiniciar(e, ADMIN) is True  # lo hace otro Administrador


def test_reiniciar_a_un_usuario_que_no_existe() -> None:
    with pytest.raises(CuentaNoDisponible):
        _reiniciar(Entorno(), objetivo="no-existe")


def test_reiniciar_sin_adaptador_falla_cerrado_y_no_finge() -> None:
    e = Entorno()
    caso = ReiniciarSegundoFactor(e.cuentas, e.accesos, e.reloj, None)
    with pytest.raises(RequiereSegundoFactor):
        caso(ADMIN, "u-1")
    assert e.accesos.acciones == []
    assert e.actual.sello_sesion == "sello-0"


def test_el_tiempo_del_caso_de_uso_es_el_del_reloj_inyectado() -> None:
    e = Entorno()
    e.reloj.avanzar(hours=5)
    for _ in range(5):
        e.confirmar(MALO)
    assert e.actual.bloqueada_hasta == e.reloj.ahora() + timedelta(minutes=15)
