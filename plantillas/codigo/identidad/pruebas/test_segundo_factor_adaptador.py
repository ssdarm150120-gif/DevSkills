"""Adaptador TOTP y cifrado del secreto contra PostgreSQL."""

import base64
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.exceptions import InvalidTag
from django.db import IntegrityError, connection, transaction
from django_otp.oath import hotp

from identidad.adaptadores.entrada import composicion
from identidad.adaptadores.salida.cifrado import CifradoDeSecretos, SecretoIlegible
from identidad.adaptadores.salida.modelos import AccionCuenta, SegundoFactor, Usuario
from identidad.adaptadores.salida.segundo_factor import (
    VerificadorTotp,
    codigo_del_paso,
    uri_de_enrolamiento,
)
from identidad.aplicacion.errores import EtapaInvalida
from identidad.aplicacion.puertos import VerificadorSegundoFactor
from identidad.dominio.segundo_factor import ResultadoCodigo, paso_de
from nucleo.actor import Actor

pytestmark = pytest.mark.django_db

AHORA = datetime(2026, 10, 9, 12, 0, 10, tzinfo=UTC)
LLAVE = "llave-de-prueba-del-segundo-factor-no-es-secreta-0123456789"


def _secreto_de(clave: str) -> bytes:
    """El secreto a partir de la clave Base32 que ve el usuario (con o sin espacios)."""
    sin_espacios = clave.replace(" ", "")
    return base64.b32decode(sin_espacios + "=" * (-len(sin_espacios) % 8))


@pytest.fixture
def usuario(crear_usuario: Callable[..., Usuario]) -> Usuario:
    return crear_usuario(roles=("auditor",))


@pytest.fixture
def verificador() -> VerificadorTotp:
    return VerificadorTotp()


def _enrolar(verificador: VerificadorTotp, usuario: Usuario) -> bytes:
    """Genera el secreto y lo devuelve (el que vio el usuario)."""
    return _secreto_de(
        verificador.iniciar_enrolamiento(str(usuario.id), usuario.correo, AHORA).clave
    )


# --- El algoritmo es el estandar (RFC 6238, el de django-otp) ----------------------------------


@pytest.mark.parametrize(
    ("segundos", "esperado"),
    [(59, "94287082"), (1111111109, "07081804"), (20000000000, "65353130")],
)
def test_el_algoritmo_coincide_con_los_vectores_del_rfc_6238(segundos: int, esperado: str) -> None:
    """Vectores SHA-1 del RFC 6238 (8 digitos): el calculo es el estandar que usan las apps."""
    clave = b"12345678901234567890"
    assert f"{hotp(clave, segundos // 30, digits=8):08d}" == esperado


def test_el_codigo_de_6_digitos_son_los_ultimos_6_del_vector_y_conserva_los_ceros() -> None:
    clave = b"12345678901234567890"
    assert codigo_del_paso(clave, 59 // 30) == "287082"
    assert codigo_del_paso(clave, 1111111109 // 30) == "081804"  # cero a la izquierda


# --- El secreto va cifrado ----------------------------------------------------------------------


def test_el_cifrado_ida_y_vuelta_y_no_deja_el_secreto_en_claro() -> None:
    cifrado = CifradoDeSecretos(LLAVE)
    secreto = b"12345678901234567890"
    guardado = cifrado.cifrar(secreto, "u-1")
    assert guardado.startswith("v2.")
    assert secreto not in guardado.encode()
    assert base64.b32encode(secreto).decode() not in guardado
    assert cifrado.descifrar(guardado, "u-1") == secreto


def test_la_derivacion_lleva_una_sal_propia_de_la_aplicacion() -> None:
    """HKDF sin sal (`salt=None`) derivaria la misma llave que cualquier otra aplicacion."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    from identidad.adaptadores.salida import cifrado as modulo

    guardado = CifradoDeSecretos(LLAVE).cifrar(b"x" * 20, "u-1")
    crudo = base64.urlsafe_b64decode(guardado.removeprefix("v2."))
    sin_sal = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=modulo._INFO_CIFRADO
    ).derive(LLAVE.encode())
    with pytest.raises(InvalidTag):  # la llave sin sal NO descifra lo que se cifro con sal
        AESGCM(sin_sal).decrypt(crudo[:12], crudo[12:], b"segundo_factor:u-1")
    assert modulo._SAL  # no vacia


def test_un_secreto_v1_de_la_derivacion_anterior_se_rechaza_cerrado() -> None:
    """Sin datos productivos, `v1.` (HKDF sin sal) ya no se acepta: falla cerrado."""
    with pytest.raises(SecretoIlegible, match="version"):
        CifradoDeSecretos(LLAVE).descifrar("v1.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "u-1")


def test_cada_cifrado_usa_un_nonce_distinto() -> None:
    cifrado = CifradoDeSecretos(LLAVE)
    assert cifrado.cifrar(b"x" * 20, "u-1") != cifrado.cifrar(b"x" * 20, "u-1")


def test_otra_llave_no_descifra_y_tiene_otro_identificador() -> None:
    uno, otro = CifradoDeSecretos(LLAVE), CifradoDeSecretos(LLAVE + "-otra")
    assert uno.llave_id != otro.llave_id
    assert uno.llave_id == CifradoDeSecretos(LLAVE).llave_id  # estable
    with pytest.raises(SecretoIlegible):
        otro.descifrar(uno.cifrar(b"x" * 20, "u-1"), "u-1")


def test_el_secreto_cifrado_de_un_usuario_no_sirve_en_la_fila_de_otro() -> None:
    """El usuario va como dato asociado: copiar el cifrado de una fila a otra no descifra."""
    cifrado = CifradoDeSecretos(LLAVE)
    guardado = cifrado.cifrar(b"x" * 20, "u-1")
    with pytest.raises(SecretoIlegible):
        cifrado.descifrar(guardado, "u-2")


@pytest.mark.parametrize("basura", ["", "v2.", "v1.AAAA", "sin-version", "v2.!!!", "v2.AAAA"])
def test_un_secreto_alterado_o_ilegible_no_se_descifra(basura: str) -> None:
    with pytest.raises(SecretoIlegible):
        CifradoDeSecretos(LLAVE).descifrar(basura, "u-1")


def test_un_byte_cambiado_en_el_secreto_cifrado_se_detecta() -> None:
    cifrado = CifradoDeSecretos(LLAVE)
    guardado = cifrado.cifrar(b"x" * 20, "u-1")
    crudo = bytearray(base64.urlsafe_b64decode(guardado.removeprefix("v2.")))
    crudo[-1] ^= 1
    alterado = "v2." + base64.urlsafe_b64encode(bytes(crudo)).decode()
    with pytest.raises(SecretoIlegible):
        cifrado.descifrar(alterado, "u-1")


@pytest.mark.parametrize("llave", ["", "   "])
def test_sin_llave_no_hay_cifrado(llave: str) -> None:
    with pytest.raises(SecretoIlegible):
        CifradoDeSecretos(llave)


def test_en_la_base_el_secreto_esta_cifrado_y_no_en_claro(
    verificador: VerificadorTotp, usuario: Usuario, settings: Any
) -> None:
    material = verificador.iniciar_enrolamiento(str(usuario.id), usuario.correo, AHORA)
    secreto = _secreto_de(material.clave)
    fila = SegundoFactor.objects.get(usuario=usuario)
    assert fila.secreto_cifrado.startswith("v2.")
    assert material.clave not in fila.secreto_cifrado
    assert secreto.hex() not in fila.secreto_cifrado
    with connection.cursor() as cursor:  # lo que realmente hay en la columna
        cursor.execute('SELECT secreto_cifrado FROM "identidad"."segundo_factor"')
        (crudo,) = cursor.fetchone()
    assert material.clave not in crudo
    assert base64.b32encode(secreto).decode() not in crudo
    assert fila.llave_id == CifradoDeSecretos(settings.APP_LLAVE_SEGUNDO_FACTOR).llave_id


# --- Enrolamiento --------------------------------------------------------------------------------


def test_el_adaptador_cumple_el_puerto(verificador: VerificadorTotp) -> None:
    assert isinstance(verificador, VerificadorSegundoFactor)


def test_iniciar_el_enrolamiento_crea_un_secreto_de_160_bits_sin_confirmar(
    verificador: VerificadorTotp, usuario: Usuario
) -> None:
    secreto = _enrolar(verificador, usuario)
    assert len(secreto) == 20
    fila = SegundoFactor.objects.get(usuario=usuario)
    assert (fila.confirmado_en, fila.ultimo_paso_aceptado) == (None, None)
    assert not verificador.esta_enrolado(str(usuario.id))


def test_el_momento_de_creacion_del_secreto_viene_del_reloj_inyectado(
    verificador: VerificadorTotp, usuario: Usuario
) -> None:
    """`creado_en` es el `ahora` que pasa el caso de uso, no el reloj del sistema."""
    verificador.iniciar_enrolamiento(str(usuario.id), usuario.correo, AHORA)
    assert SegundoFactor.objects.get(usuario=usuario).creado_en == AHORA


def test_recargar_la_pantalla_muestra_el_mismo_secreto_mientras_no_se_confirme(
    verificador: VerificadorTotp, usuario: Usuario
) -> None:
    assert _enrolar(verificador, usuario) == _enrolar(verificador, usuario)
    assert SegundoFactor.objects.filter(usuario=usuario).count() == 1


def test_dos_usuarios_reciben_secretos_distintos(
    verificador: VerificadorTotp, usuario: Usuario, crear_usuario: Callable[..., Usuario]
) -> None:
    otro = crear_usuario(correo="luis@empresa.example", roles=("auditor",))
    assert _enrolar(verificador, usuario) != _enrolar(verificador, otro)


def test_el_uri_lleva_el_emisor_de_la_configuracion_y_el_correo(settings: Any) -> None:
    settings.APP_NOMBRE_APLICACION = "Mi Empresa: Ventas"
    uri = uri_de_enrolamiento(b"12345678901234567890", "ana+x@empresa.example")
    partes = urlsplit(uri)
    consulta = parse_qs(partes.query)
    assert partes.scheme == "otpauth"
    assert partes.netloc == "totp"
    assert partes.path == "/Mi%20Empresa%3A%20Ventas:ana%2Bx%40empresa.example"
    assert consulta["issuer"] == ["Mi Empresa: Ventas"]
    assert consulta["secret"] == [base64.b32encode(b"12345678901234567890").decode().rstrip("=")]
    assert (consulta["algorithm"], consulta["digits"], consulta["period"]) == (
        ["SHA1"],
        ["6"],
        ["30"],
    )


def test_el_emisor_por_defecto_no_es_el_nombre_de_ninguna_empresa(settings: Any) -> None:
    assert settings.APP_NOMBRE_APLICACION == "Aplicación"
    assert "totp/Aplicaci%C3%B3n:" in uri_de_enrolamiento(b"x" * 20, "ana@x.example")


def test_confirmar_el_enrolamiento_guarda_la_confirmacion_y_el_paso(
    verificador: VerificadorTotp, usuario: Usuario
) -> None:
    secreto = _enrolar(verificador, usuario)
    codigo = codigo_del_paso(secreto, paso_de(AHORA))
    resultado = verificador.verificar(str(usuario.id), codigo, AHORA, confirmando=True)
    assert resultado is ResultadoCodigo.ACEPTADO
    fila = SegundoFactor.objects.get(usuario=usuario)
    assert fila.confirmado_en == AHORA
    assert fila.ultimo_paso_aceptado == paso_de(AHORA)
    assert verificador.esta_enrolado(str(usuario.id))


def test_un_codigo_malo_no_confirma_el_enrolamiento(
    verificador: VerificadorTotp, usuario: Usuario
) -> None:
    secreto = _enrolar(verificador, usuario)
    bueno = codigo_del_paso(secreto, paso_de(AHORA))
    malo = "000000" if bueno != "000000" else "000001"
    assert verificador.verificar(str(usuario.id), malo, AHORA, confirmando=True) is (
        ResultadoCodigo.INCORRECTO
    )
    assert not verificador.esta_enrolado(str(usuario.id))
    assert SegundoFactor.objects.get(usuario=usuario).ultimo_paso_aceptado is None


def test_iniciar_el_enrolamiento_de_quien_ya_esta_enrolado_se_rechaza(
    verificador: VerificadorTotp, usuario: Usuario
) -> None:
    secreto = _enrolar(verificador, usuario)
    verificador.verificar(
        str(usuario.id), codigo_del_paso(secreto, paso_de(AHORA)), AHORA, confirmando=True
    )
    with pytest.raises(EtapaInvalida):  # error de dominio, no un `ValueError` generico
        verificador.iniciar_enrolamiento(str(usuario.id), usuario.correo, AHORA)


# --- Codigo en cada ingreso: ventana acotada ------------------------------------------------------


@pytest.fixture
def enrolado(verificador: VerificadorTotp, usuario: Usuario) -> bytes:
    secreto = _enrolar(verificador, usuario)
    previo = AHORA - timedelta(minutes=10)  # el enrolamiento fue hace rato
    verificador.verificar(
        str(usuario.id), codigo_del_paso(secreto, paso_de(previo)), previo, confirmando=True
    )
    return secreto


def test_el_codigo_vigente_se_acepta(
    verificador: VerificadorTotp, usuario: Usuario, enrolado: bytes
) -> None:
    codigo = codigo_del_paso(enrolado, paso_de(AHORA))
    assert verificador.verificar(str(usuario.id), codigo, AHORA, confirmando=False) is (
        ResultadoCodigo.ACEPTADO
    )


@pytest.mark.parametrize("pasos", [-1, 1])
def test_se_acepta_el_codigo_del_paso_anterior_y_del_siguiente(
    verificador: VerificadorTotp, usuario: Usuario, enrolado: bytes, pasos: int
) -> None:
    codigo = codigo_del_paso(enrolado, paso_de(AHORA) + pasos)
    assert verificador.verificar(str(usuario.id), codigo, AHORA, confirmando=False) is (
        ResultadoCodigo.ACEPTADO
    )


@pytest.mark.parametrize("pasos", [-2, 2, -10, 10])
def test_un_codigo_fuera_de_la_ventana_no_se_acepta(
    verificador: VerificadorTotp, usuario: Usuario, enrolado: bytes, pasos: int
) -> None:
    codigo = codigo_del_paso(enrolado, paso_de(AHORA) + pasos)
    assert verificador.verificar(str(usuario.id), codigo, AHORA, confirmando=False) is (
        ResultadoCodigo.INCORRECTO
    )


def test_el_mismo_codigo_no_se_acepta_dos_veces_dentro_de_su_vigencia(
    verificador: VerificadorTotp, usuario: Usuario, enrolado: bytes
) -> None:
    codigo = codigo_del_paso(enrolado, paso_de(AHORA))
    assert verificador.verificar(str(usuario.id), codigo, AHORA, confirmando=False) is (
        ResultadoCodigo.ACEPTADO
    )
    # Dentro de su vigencia (ahora y 40 s despues, el paso siguiente aun lo contiene en la ventana).
    for despues in (AHORA, AHORA + timedelta(seconds=5), AHORA + timedelta(seconds=40)):
        assert verificador.verificar(str(usuario.id), codigo, despues, confirmando=False) is (
            ResultadoCodigo.REPETIDO
        )


def test_aceptado_un_codigo_el_de_un_paso_anterior_tambien_se_rechaza(
    verificador: VerificadorTotp, usuario: Usuario, enrolado: bytes
) -> None:
    actual = codigo_del_paso(enrolado, paso_de(AHORA))
    anterior = codigo_del_paso(enrolado, paso_de(AHORA) - 1)
    assert verificador.verificar(str(usuario.id), actual, AHORA, confirmando=False) is (
        ResultadoCodigo.ACEPTADO
    )
    assert verificador.verificar(str(usuario.id), anterior, AHORA, confirmando=False) is (
        ResultadoCodigo.REPETIDO
    )


def test_el_codigo_del_paso_siguiente_se_acepta_una_vez_y_despues_se_rechaza(
    verificador: VerificadorTotp, usuario: Usuario, enrolado: bytes
) -> None:
    siguiente = codigo_del_paso(enrolado, paso_de(AHORA) + 1)
    assert verificador.verificar(str(usuario.id), siguiente, AHORA, confirmando=False) is (
        ResultadoCodigo.ACEPTADO
    )
    mas_tarde = AHORA + timedelta(seconds=30)  # ahora ese es el paso vigente
    assert verificador.verificar(str(usuario.id), siguiente, mas_tarde, confirmando=False) is (
        ResultadoCodigo.REPETIDO
    )


def test_un_codigo_rechazado_no_cambia_el_ultimo_paso_aceptado(
    verificador: VerificadorTotp, usuario: Usuario, enrolado: bytes
) -> None:
    antes = SegundoFactor.objects.get(usuario=usuario).ultimo_paso_aceptado
    actual = codigo_del_paso(enrolado, paso_de(AHORA))
    malo = "000000" if actual != "000000" else "000001"
    verificador.verificar(str(usuario.id), malo, AHORA, confirmando=False)
    assert SegundoFactor.objects.get(usuario=usuario).ultimo_paso_aceptado == antes


def test_pedir_el_codigo_de_ingreso_a_quien_no_esta_enrolado_o_confirmar_a_quien_si_falla(
    verificador: VerificadorTotp, usuario: Usuario, enrolado: bytes
) -> None:
    codigo = codigo_del_paso(enrolado, paso_de(AHORA))
    # Ya esta confirmado: confirmar de nuevo ("enrolando") no es una etapa valida.
    assert verificador.verificar(str(usuario.id), codigo, AHORA, confirmando=True) is (
        ResultadoCodigo.INCORRECTO
    )
    # Y quien no tiene fila no tiene nada que verificar.
    assert verificador.verificar(
        "00000000-0000-0000-0000-000000000000", codigo, AHORA, confirmando=False
    ) is (ResultadoCodigo.INCORRECTO)


# --- Falla cerrado: sin llave o con una llave distinta --------------------------------------------


def test_sin_llave_el_segundo_factor_no_esta_disponible(
    verificador: VerificadorTotp, usuario: Usuario, settings: Any
) -> None:
    settings.APP_LLAVE_SEGUNDO_FACTOR = ""
    assert not verificador.disponible_para(str(usuario.id))
    with pytest.raises(SecretoIlegible):
        verificador.iniciar_enrolamiento(str(usuario.id), usuario.correo, AHORA)


def test_con_la_llave_actual_y_sin_registro_esta_disponible(
    verificador: VerificadorTotp, usuario: Usuario
) -> None:
    assert verificador.disponible_para(str(usuario.id))


def test_si_cambia_la_llave_el_secreto_ya_guardado_no_esta_disponible_ni_verifica(
    verificador: VerificadorTotp, usuario: Usuario, enrolado: bytes, settings: Any
) -> None:
    codigo = codigo_del_paso(enrolado, paso_de(AHORA))
    settings.APP_LLAVE_SEGUNDO_FACTOR = "otra-llave-completamente-distinta-0123456789-abcdefghij"
    assert not verificador.disponible_para(str(usuario.id))
    assert verificador.verificar(str(usuario.id), codigo, AHORA, confirmando=False) is (
        ResultadoCodigo.INCORRECTO
    )


def test_un_secreto_corrupto_en_la_base_no_esta_disponible(
    verificador: VerificadorTotp, usuario: Usuario, enrolado: bytes
) -> None:
    SegundoFactor.objects.filter(usuario=usuario).update(secreto_cifrado="v2.AAAAAAAAAAAAAAAAAAAA")
    assert not verificador.disponible_para(str(usuario.id))


# --- Reinicio atomico -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "falla",
    [
        (
            "identidad.adaptadores.salida.repositorios.RepositorioCuentasDjango",
            "guardar_conteo_codigo",
        ),
        ("identidad.adaptadores.salida.repositorios.RegistroDeAccesosDjango", "registrar_accion"),
    ],
    ids=["falla-el-contador", "falla-el-registro-de-auditoria"],
)
def test_si_una_escritura_del_reinicio_falla_no_queda_nada_a_medias(
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable[..., bytes],
    monkeypatch: pytest.MonkeyPatch,
    falla: tuple[str, str],
) -> None:
    """El reinicio son 4 escrituras en una transaccion: si una falla, no queda nada a medias."""
    usuario = crear_usuario(roles=("auditor",), fallos_codigo=2)
    registrar_segundo_factor(usuario)
    otro_admin = crear_usuario(correo="root@empresa.example", roles=("administrador",))
    actor = Actor.de(str(otro_admin.id), ["administrador"])
    sello = Usuario.objects.get(pk=usuario.pk).sello_sesion

    def _revienta(*args: object, **kwargs: object) -> None:
        raise RuntimeError("falla simulada")

    monkeypatch.setattr(f"{falla[0]}.{falla[1]}", _revienta)
    with pytest.raises(RuntimeError, match="falla simulada"):
        composicion.reiniciar_segundo_factor()(actor, str(usuario.id))

    despues = Usuario.objects.get(pk=usuario.pk)
    assert SegundoFactor.objects.filter(usuario=usuario).exists()  # el factor no se borro
    assert despues.sello_sesion == sello  # el sello no roto: sus sesiones siguen valiendo
    assert despues.fallos_codigo == 2
    assert not AccionCuenta.objects.filter(accion="reinicio_segundo_factor").exists()


def test_el_reinicio_completo_si_deja_las_cuatro_escrituras(
    crear_usuario: Callable[..., Usuario], registrar_segundo_factor: Callable[..., bytes]
) -> None:
    usuario = crear_usuario(roles=("auditor",), fallos_codigo=2)
    registrar_segundo_factor(usuario)
    otro_admin = crear_usuario(correo="root@empresa.example", roles=("administrador",))
    actor = Actor.de(str(otro_admin.id), ["administrador"])
    sello = Usuario.objects.get(pk=usuario.pk).sello_sesion
    assert composicion.reiniciar_segundo_factor()(actor, str(usuario.id)) is True
    despues = Usuario.objects.get(pk=usuario.pk)
    assert not SegundoFactor.objects.filter(usuario=usuario).exists()
    assert (despues.sello_sesion != sello, despues.fallos_codigo) == (True, 0)
    assert AccionCuenta.objects.filter(accion="reinicio_segundo_factor").count() == 1


# --- Una fila por usuario, reinicio ---------------------------------------------------------------


def test_hay_una_sola_fila_por_usuario(usuario: Usuario) -> None:
    ahora = AHORA
    SegundoFactor.objects.create(
        usuario=usuario, secreto_cifrado="x", llave_id="k", creado_en=ahora
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        SegundoFactor.objects.create(
            usuario=usuario, secreto_cifrado="y", llave_id="k", creado_en=ahora
        )


def test_confirmado_en_y_ultimo_paso_nacen_juntos(usuario: Usuario) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        SegundoFactor.objects.create(
            usuario=usuario,
            secreto_cifrado="x",
            llave_id="k",
            creado_en=AHORA,
            confirmado_en=AHORA,  # sin ultimo_paso_aceptado
        )


def test_reiniciar_borra_el_segundo_factor_y_el_usuario_vuelve_a_enrolarse(
    verificador: VerificadorTotp, usuario: Usuario, enrolado: bytes
) -> None:
    assert verificador.reiniciar(str(usuario.id)) is True
    assert not verificador.esta_enrolado(str(usuario.id))
    assert not SegundoFactor.objects.filter(usuario=usuario).exists()
    assert verificador.reiniciar(str(usuario.id)) is False  # ya no habia
    nuevo = _enrolar(verificador, usuario)
    assert nuevo != enrolado  # un secreto nuevo: el anterior ya no sirve


def test_el_codigo_del_secreto_anterior_no_sirve_despues_de_reiniciar(
    verificador: VerificadorTotp, usuario: Usuario, enrolado: bytes
) -> None:
    viejo = codigo_del_paso(enrolado, paso_de(AHORA))
    verificador.reiniciar(str(usuario.id))
    nuevo = _enrolar(verificador, usuario)
    if codigo_del_paso(nuevo, paso_de(AHORA)) == viejo:  # 1 en un millon: no hay nada que probar
        pytest.skip("coincidencia de codigos")
    assert verificador.verificar(str(usuario.id), viejo, AHORA, confirmando=True) is (
        ResultadoCodigo.INCORRECTO
    )
