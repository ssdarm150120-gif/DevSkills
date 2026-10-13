"""Casos de uso de la gestion de usuarios contra puertos falsos.

El comportamiento con base real esta en `test_gestion_usuarios_base.py` y las pantallas en
`test_escenarios_gestion_de_usuarios.py` (escenarios Gherkin).
"""

import dataclasses
from datetime import timedelta
from typing import Any

import pytest

from identidad.aplicacion.consultar_usuarios import ConsultarUsuarios, EstadoSegundoFactor
from identidad.aplicacion.crear_usuario import CrearUsuario
from identidad.aplicacion.editar_usuario import EditarUsuario
from identidad.aplicacion.errores import ConflictoDeUsuario, CuentaNoDisponible, PermisoDenegado
from identidad.aplicacion.estado_de_usuario import DesactivarUsuario, ReactivarUsuario
from identidad.aplicacion.puertos import Cuenta
from identidad.aplicacion.recuperar_acceso import DesbloquearCuenta, RestablecerContrasena
from identidad.aplicacion.reiniciar_segundo_factor import ReiniciarSegundoFactor
from identidad.dominio.acceso import AccionDeCuenta
from identidad.dominio.roles import CATALOGO_DE_ROLES, ROLES_CON_SEGUNDO_FACTOR
from identidad.dominio.usuarios import UsuarioInvalido
from identidad.pruebas.falsos import (
    AccesosEnMemoria,
    CatalogoEnMemoria,
    ContrasenasFalsas,
    CuentasEnMemoria,
    RelojFalso,
    VerificadorEnMemoria,
    cuenta,
)
from nucleo.actor import Actor


class Mundo:
    def __init__(self) -> None:
        self.cuentas = CuentasEnMemoria()
        self.accesos = AccesosEnMemoria()
        self.contrasenas = ContrasenasFalsas()
        self.reloj = RelojFalso()
        self.verificador = VerificadorEnMemoria()
        self.admin = self.agregar("adm", "adm@empresa.example", {"administrador"})
        self.actor = Actor.de("adm", ["administrador"])

    def agregar(self, id: str, correo: str, roles: set[str], **c: Any) -> Cuenta:
        sensible = bool(roles & ROLES_CON_SEGUNDO_FACTOR)
        return self.cuentas.agregar(
            cuenta(id=id, correo=correo, roles=frozenset(roles), exige_segundo_factor=sensible, **c)
        )

    def otro_actor(self, *roles: str) -> Actor:
        return Actor.de("x", roles)


@pytest.fixture
def m() -> Mundo:
    return Mundo()


def _crear(m: Mundo) -> CrearUsuario:
    return CrearUsuario(m.cuentas, m.accesos, m.contrasenas, m.reloj)


def _alta(m: Mundo, **c: object) -> tuple[str, str]:
    """Da de alta y devuelve `(id, contrasena_temporal)`."""
    datos = {"correo": "Ana@empresa.example", "nombre": "Ana", "roles": ["usuario", "auditor"]}
    creado = _crear(m)(m.actor, **{**datos, **c})  # type: ignore[arg-type]
    return creado.id, creado.temporal


def _editar(m: Mundo) -> EditarUsuario:
    return EditarUsuario(m.cuentas, m.accesos, m.reloj)


def _desactivar(m: Mundo) -> DesactivarUsuario:
    return DesactivarUsuario(m.cuentas, m.accesos, m.reloj)


def _consulta(m: Mundo, verificador: VerificadorEnMemoria | None) -> ConsultarUsuarios:
    return ConsultarUsuarios(m.cuentas, CatalogoEnMemoria(), m.reloj, verificador)


def _otro_admin(m: Mundo) -> Actor:
    m.agregar("adm2", "adm2@n.co", {"administrador"})
    return Actor.de("adm2", ["administrador"])


# --- Alta -------------------------------------------------------------------------------------


def test_alta_con_varios_roles_temporal_y_bitacora_sin_contrasena(m: Mundo) -> None:
    uid, temporal = _alta(m)
    nueva = m.cuentas.por_id(uid)
    assert nueva is not None
    assert nueva.roles == {"usuario", "auditor"}
    assert nueva.debe_cambiar_contrasena and nueva.correo == "ana@empresa.example"
    assert nueva.hash_contrasena == m.contrasenas.hashear(temporal)
    registro = m.accesos.acciones[-1]
    assert registro["accion"] is AccionDeCuenta.ALTA
    assert registro["objetivo"] == uid and registro["hecha_por"] == "adm"
    assert registro["detalle"] == {"roles": ["auditor", "usuario"]}
    assert temporal not in repr(m.accesos.acciones)


def test_alta_solo_el_administrador(m: Mundo) -> None:
    for rol in ("auditor", "usuario"):
        with pytest.raises(PermisoDenegado):
            _crear(m)(m.otro_actor(rol), correo="a@b.co", nombre="A", roles=["usuario"])
    assert len(m.cuentas.cuentas) == 1


def test_alta_correo_repetido_sin_distinguir_mayusculas(m: Mundo) -> None:
    _alta(m)
    with pytest.raises(ConflictoDeUsuario, match="correo"):
        _alta(m, correo="ANA@empresa.example")


def test_alta_con_datos_invalidos(m: Mundo) -> None:
    invalidos: tuple[dict[str, object], ...] = (
        {"correo": "no-es-correo"},
        {"nombre": "  "},
        {"roles": []},
        {"roles": ["x"]},
    )
    for datos in invalidos:
        with pytest.raises(UsuarioInvalido):
            _alta(m, **datos)
    assert len(m.cuentas.cuentas) == 1  # nada se guardo


@pytest.mark.parametrize(
    "correo", ["ana@empresa.example", "a.b-c_d9@sub.empresa.example", "ANA@Empresa.Example"]
)
def test_alta_acepta_solo_correos_ascii(m: Mundo, correo: str) -> None:
    assert _alta(m, correo=correo)[0]


@pytest.mark.parametrize(
    "correo",
    [
        "josé@empresa.example",
        "peña@empresa.example",
        "ana@empresá.example",
        "ana+x@empresa.example",
        "a na@empresa.example",
        "ana@@empresa.example",
        "ａｎａ@empresa.example",
        "аna@empresa.example",  # "a" cirilica (U+0430), homoglifo de la "a" latina
        "ana@empresa.exаmple",  # el mismo homoglifo en el dominio
        "Karla@empresa.example",  # signo Kelvin: `lower()` lo volveria una "k" ASCII
        "a..b@x.co",  # dos puntos seguidos
        ".a@x.co",  # punto al inicio
        "a.@x.co",  # punto al final
        "a@x..co",  # lo mismo en el dominio
        "a@.x.co",
        "a@x.co.",
        "a@-x.co",
    ],
)
def test_alta_rechaza_caracteres_y_puntos_no_permitidos_diciendo_que_se_acepta(
    m: Mundo, correo: str
) -> None:
    with pytest.raises(UsuarioInvalido, match="letras sin acento, números, punto, guion"):
        _alta(m, correo=correo)
    assert len(m.cuentas.cuentas) == 1


def test_alta_normaliza_el_nombre(m: Mundo) -> None:
    uid, _ = _alta(m, nombre="Ａｎａ")  # anchura completa: NFKC lo vuelve "Ana"
    assert m.cuentas.por_id(uid).nombre == "Ana"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "nombre",
    [
        "An​a",  # Cf: espacio de ancho cero
        "‮Ana",  # Cf: inversion de direccion
        "Ana⁠",  # Cf: unidor de palabras
        "A\x00na",  # Cc: control
        "Ana Ruiz",  # Zl: separador de linea
        "Ana Ruiz",  # Zp: separador de parrafo
        "Ana",  # Co: uso privado
        "Ana\ud800",  # Cs: sustituto suelto
    ],
)
def test_el_nombre_rechaza_control_invisibles_separadores_uso_privado_y_sustitutos(
    m: Mundo, nombre: str
) -> None:
    with pytest.raises(UsuarioInvalido, match="control ni invisibles"):
        _alta(m, correo="b@empresa.example", nombre=nombre)
    assert len(m.cuentas.cuentas) == 1


# --- Editar datos y roles ---------------------------------------------------------------------


def test_cambio_de_roles_rota_el_sello_y_se_registra(m: Mundo) -> None:
    m.agregar("u", "u@n.co", {"usuario"})
    antes = m.cuentas.por_id("u").sello_sesion  # type: ignore[union-attr]
    r = _editar(m)(m.actor, "u", nombre="U", roles=["usuario", "auditor"])
    despues = m.cuentas.por_id("u")
    assert r.roles_cambiados and despues.sello_sesion != antes  # type: ignore[union-attr]
    assert despues.exige_segundo_factor  # type: ignore[union-attr]
    ultimo = [a for a in m.accesos.acciones if a["accion"] is AccionDeCuenta.CAMBIO_DE_ROLES]
    assert ultimo[0]["detalle"] == {"antes": ["usuario"], "despues": ["auditor", "usuario"]}


def test_sin_cambio_de_roles_no_rota_el_sello(m: Mundo) -> None:
    m.agregar("u", "u@n.co", {"auditor"}, nombre="U")
    r = _editar(m)(m.actor, "u", nombre="Nuevo", roles=["auditor"])
    assert r.datos_cambiados and not r.roles_cambiados
    assert m.cuentas.sellos["u"] == 0
    assert m.accesos.acciones[-1]["detalle"] == {"campos": ["nombre"]}
    r = _editar(m)(m.actor, "u", nombre="Nuevo", roles=["auditor"])
    assert not r.datos_cambiados


def test_editar_valida_los_datos(m: Mundo) -> None:
    m.agregar("u", "u@n.co", {"usuario"}, nombre="U")
    with pytest.raises(UsuarioInvalido, match="al menos un rol"):
        _editar(m)(m.actor, "u", nombre="U", roles=[])
    with pytest.raises(UsuarioInvalido, match="obligatorio"):
        _editar(m)(m.actor, "u", nombre=" ", roles=["usuario"])


def test_editar_permisos_y_cuenta_inexistente(m: Mundo) -> None:
    with pytest.raises(PermisoDenegado):
        _editar(m)(m.otro_actor("usuario"), "adm", nombre="A", roles=["usuario"])
    with pytest.raises(CuentaNoDisponible):
        _editar(m)(m.actor, "nada", nombre="A", roles=["usuario"])


def test_un_administrador_cambia_sus_propios_roles_y_queda_en_la_bitacora(m: Mundo) -> None:
    """Puede agregarse y quitarse OTROS roles; no el de Administrador."""
    editar = _editar(m)
    editar(m.actor, "adm", nombre="A", roles=["administrador", "usuario"])
    assert m.cuentas.por_id("adm").roles == {"administrador", "usuario"}  # type: ignore[union-attr]
    editar(m.actor, "adm", nombre="A", roles=["administrador"])
    assert m.cuentas.por_id("adm").roles == {"administrador"}  # type: ignore[union-attr]
    cambios = [a for a in m.accesos.acciones if a["accion"] is AccionDeCuenta.CAMBIO_DE_ROLES]
    assert [(c["objetivo"], c["hecha_por"]) for c in cambios] == [("adm", "adm")] * 2
    with pytest.raises(PermisoDenegado, match="otro administrador"):
        editar(m.actor, "adm", nombre="A", roles=["usuario"])
    assert "administrador" in m.cuentas.por_id("adm").roles  # type: ignore[operator,union-attr]
    with pytest.raises(PermisoDenegado):
        _desactivar(m)(m.actor, "adm")


def test_no_se_le_quita_el_rol_al_ultimo_administrador(m: Mundo) -> None:
    otro = _otro_admin(m)
    editar = _editar(m)
    editar(m.actor, "adm2", nombre="B", roles=["auditor"])
    with pytest.raises(ConflictoDeUsuario, match="al menos un administrador activo"):
        editar(otro, "adm", nombre="A", roles=["auditor"])
    assert m.cuentas.por_id("adm").roles == {"administrador"}  # type: ignore[union-attr]


def test_un_administrador_desactivado_no_cuenta_como_activo(m: Mundo) -> None:
    otro = _otro_admin(m)
    m.cuentas.fijar_activo("adm", False)
    m.agregar("adm3", "adm3@n.co", {"administrador"})
    m.cuentas.fijar_activo("adm3", False)
    tercero = Actor.de("adm3", ["administrador"])
    with pytest.raises(ConflictoDeUsuario, match="al menos un administrador activo"):
        _editar(m)(tercero, "adm2", nombre="B", roles=["auditor"])
    # Quitarle el rol a un administrador YA desactivado no cambia a los activos: se permite.
    _editar(m)(otro, "adm", nombre="A", roles=["auditor"])
    assert m.cuentas.por_id("adm").roles == {"auditor"}  # type: ignore[union-attr]


# --- Desactivar / reactivar -------------------------------------------------------------------


def test_desactivar_rota_sello_y_registra_sus_roles(m: Mundo) -> None:
    m.agregar("u", "u@n.co", {"usuario"})
    caso = _desactivar(m)
    assert caso(m.actor, "u")
    u = m.cuentas.por_id("u")
    assert not u.activo and m.cuentas.sellos["u"] == 1  # type: ignore[union-attr]
    assert m.accesos.acciones[-1]["detalle"] == {"roles": ["usuario"]}
    assert not caso(m.actor, "u")  # ya estaba


def test_nadie_se_desactiva_a_si_mismo_ni_sin_ser_admin(m: Mundo) -> None:
    caso = _desactivar(m)
    with pytest.raises(PermisoDenegado):
        caso(m.actor, "adm")
    with pytest.raises(PermisoDenegado):
        caso(m.otro_actor("usuario"), "adm")
    with pytest.raises(CuentaNoDisponible):
        caso(m.actor, "nada")


def test_no_se_desactiva_al_ultimo_administrador(m: Mundo) -> None:
    otro = _otro_admin(m)
    caso = _desactivar(m)
    assert caso(m.actor, "adm2")  # queda 1: adm
    with pytest.raises(ConflictoDeUsuario, match="al menos un administrador activo"):
        caso(otro, "adm")  # adm2 ya no esta activo: adm es el ultimo
    assert m.cuentas.por_id("adm").activo  # type: ignore[union-attr]


def test_reactivar(m: Mundo) -> None:
    m.agregar("u", "u@n.co", {"usuario"}, activo=False)
    caso = ReactivarUsuario(m.cuentas, m.accesos, m.reloj)
    assert caso(m.actor, "u") and m.cuentas.por_id("u").activo  # type: ignore[union-attr]
    assert m.accesos.acciones[-1]["accion"] is AccionDeCuenta.REACTIVACION
    assert not caso(m.actor, "u")
    with pytest.raises(PermisoDenegado):
        caso(m.otro_actor("usuario"), "u")
    with pytest.raises(CuentaNoDisponible):
        caso(m.actor, "nada")


# --- Recuperar acceso ------------------------------------------------------------------------


def test_restablecer_contrasena(m: Mundo) -> None:
    m.agregar("u", "u@n.co", {"usuario"})
    antes = m.cuentas.por_id("u")
    restablecida = RestablecerContrasena(m.cuentas, m.accesos, m.contrasenas, m.reloj)(m.actor, "u")
    temporal = restablecida.temporal
    assert restablecida.correo == "u@n.co" and temporal not in repr(restablecida)
    ahora = m.cuentas.por_id("u")
    assert ahora.hash_contrasena != antes.hash_contrasena  # type: ignore[union-attr]
    assert ahora.debe_cambiar_contrasena and ahora.sello_sesion != antes.sello_sesion  # type: ignore[union-attr]
    r = m.accesos.acciones[-1]
    assert (r["accion"], r["objetivo"], r["hecha_por"]) == (
        AccionDeCuenta.RESTABLECIMIENTO_CONTRASENA,
        "u",
        "adm",
    )
    assert temporal not in repr(m.accesos.acciones)


def test_nadie_restablece_ni_reinicia_lo_suyo_como_administrador(m: Mundo) -> None:
    with pytest.raises(PermisoDenegado, match="otro administrador"):
        RestablecerContrasena(m.cuentas, m.accesos, m.contrasenas, m.reloj)(m.actor, "adm")
    with pytest.raises(PermisoDenegado, match="otro administrador"):
        ReiniciarSegundoFactor(m.cuentas, m.accesos, m.reloj, m.verificador)(m.actor, "adm")
    # otro administrador si puede
    otro = _otro_admin(m)
    RestablecerContrasena(m.cuentas, m.accesos, m.contrasenas, m.reloj)(otro, "adm")
    assert m.cuentas.por_id("adm").debe_cambiar_contrasena  # type: ignore[union-attr]


def test_restablecer_permisos_y_cuenta_inexistente(m: Mundo) -> None:
    caso = RestablecerContrasena(m.cuentas, m.accesos, m.contrasenas, m.reloj)
    with pytest.raises(PermisoDenegado):
        caso(m.otro_actor("usuario"), "adm")
    with pytest.raises(CuentaNoDisponible):
        caso(m.actor, "nada")


def test_desbloquear_pone_en_cero_los_dos_contadores(m: Mundo) -> None:
    hasta = m.reloj.ahora() + timedelta(minutes=15)
    m.agregar(
        "u", "u@n.co", {"usuario"}, fallos_contrasena=3, fallos_codigo=2, bloqueada_hasta=hasta
    )
    caso = DesbloquearCuenta(m.cuentas, m.accesos, m.reloj)
    caso(m.actor, "u")
    u = m.cuentas.por_id("u")
    assert (u.fallos_contrasena, u.fallos_codigo, u.bloqueada_hasta) == (0, 0, None)  # type: ignore[union-attr]
    assert m.accesos.acciones[-1]["accion"] is AccionDeCuenta.DESBLOQUEO
    with pytest.raises(PermisoDenegado):
        caso(m.otro_actor("usuario"), "u")
    with pytest.raises(CuentaNoDisponible):
        caso(m.actor, "nada")


# --- Consulta ---------------------------------------------------------------------------------


def test_listar_y_detalle(m: Mundo) -> None:
    hasta = m.reloj.ahora() + timedelta(minutes=5)
    m.agregar("b", "b@n.co", {"usuario"}, bloqueada_hasta=hasta)
    m.agregar("f", "f@n.co", {"auditor"})
    c = _consulta(m, m.verificador)
    filas = c.listar(m.actor)
    assert [f.cuenta.id for f in filas] == ["adm", "b", "f"]
    assert {f.cuenta.id: f.bloqueada for f in filas} == {"adm": False, "b": True, "f": False}
    assert len(c.catalogo_de_roles(m.actor)) == len(CATALOGO_DE_ROLES)
    assert c.detalle(m.actor, "b").segundo_factor is EstadoSegundoFactor.NO_APLICA
    assert c.detalle(m.actor, "f").segundo_factor is EstadoSegundoFactor.SIN_ENROLAR
    m.verificador.enrolados.add("f")
    assert c.detalle(m.actor, "f").segundo_factor is EstadoSegundoFactor.ENROLADO
    assert (
        _consulta(m, None).detalle(m.actor, "f").segundo_factor is EstadoSegundoFactor.NO_DISPONIBLE
    )
    propio = c.detalle(m.actor, "adm")
    assert propio.es_el_actor and not propio.puede_recuperar
    assert c.detalle(m.actor, "f").puede_recuperar


def test_consultar_exige_administrador_y_cuenta(m: Mundo) -> None:
    c = _consulta(m, None)
    for llamada in (
        lambda: c.listar(m.otro_actor("usuario")),
        lambda: c.detalle(m.otro_actor("usuario"), "adm"),
        lambda: c.catalogo_de_roles(m.otro_actor("usuario")),
    ):
        with pytest.raises(PermisoDenegado):
            llamada()
    with pytest.raises(CuentaNoDisponible):
        c.detalle(m.actor, "nada")


def test_el_aviso_de_un_solo_administrador(m: Mundo) -> None:
    c = _consulta(m, None)
    assert c.solo_un_administrador(m.actor)
    _otro_admin(m)
    assert not c.solo_un_administrador(m.actor)
    m.cuentas.fijar_activo("adm2", False)
    assert c.solo_un_administrador(m.actor)
    with pytest.raises(PermisoDenegado):
        c.solo_un_administrador(m.otro_actor("usuario"))


def test_los_permisos_de_gestion_salen_de_la_matriz_de_nucleo(m: Mundo) -> None:
    from identidad.aplicacion.permisos import exigir_administrador

    exigir_administrador(m.actor)
    for rol in ("auditor", "usuario"):
        with pytest.raises(PermisoDenegado):
            exigir_administrador(m.otro_actor(rol))


def test_el_cuenta_dataclass_sigue_siendo_inmutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        cuenta().nombre = "x"  # type: ignore[misc]
