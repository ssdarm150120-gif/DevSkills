"""Etapas del ingreso con segundo factor por HTTP (DISENO D.3.10 y D.5.4)."""

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.test import Client, override_settings

from identidad.adaptadores.entrada.middleware import CLAVE_ETAPA
from identidad.adaptadores.salida.modelos import IntentoIngreso, SegundoFactor, Usuario
from identidad.adaptadores.salida.repositorios import RepositorioCuentasDjango
from identidad.adaptadores.salida.segundo_factor import codigo_del_paso
from identidad.dominio.segundo_factor import paso_de
from identidad.pruebas.conftest import CONTRASENA, RelojAdelantable
from nucleo.pruebas.aislamiento import Aislamiento

pytestmark = pytest.mark.django_db

# La CSP de produccion (la define `configuracion.seguridad`; un modulo no importa `configuracion`, y
# `configuracion/pruebas/test_settings.py` vigila que no cambie). Se repite aqui para probar que la
# pantalla del QR funciona SIN relajarla.
CSP_ESTRICTA = (
    "default-src 'self'; frame-ancestors 'none'; object-src 'none'; "
    "base-uri 'self'; form-action 'self'"
)

CORREO = "ana@empresa.example"
REQUIERE = "Tu rol requiere un segundo factor para ingresar"
VENCIDA = "Tu ingreso ya no es válido"


def _ingresar(cliente: Client, contrasena: str = CONTRASENA, correo: str = CORREO) -> Any:
    return cliente.post("/ingresar", {"correo": correo, "contrasena": contrasena})


def _bueno(secreto: bytes, reloj: RelojAdelantable | None = None) -> str:
    ahora = reloj.ahora() if reloj else datetime.now(UTC)
    return codigo_del_paso(secreto, paso_de(ahora))


def _malo(secreto: bytes) -> str:
    bueno = _bueno(secreto)
    return "000000" if bueno != "000000" else "000001"


@pytest.fixture
def con_codigo_pendiente(
    cliente: Client,
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable[..., bytes],
) -> tuple[Client, Usuario, bytes]:
    """Un usuario sensible ya enrolado, con la contrasena puesta y esperando el codigo."""
    usuario = crear_usuario(roles=("auditor",))
    secreto = registrar_segundo_factor(usuario)
    assert _ingresar(cliente)["Location"] == "/ingresar/codigo"
    return cliente, usuario, secreto


@pytest.fixture
def con_enrolamiento_pendiente(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> tuple[Client, Usuario]:
    usuario = crear_usuario(roles=("auditor",))
    assert _ingresar(cliente)["Location"] == "/ingresar/enrolar"
    return cliente, usuario


# --- Orden de las etapas (D.3.10): contrasena, cambio obligatorio, enrolamiento, codigo -----------


def test_la_cadena_completa_de_un_rol_sensible_nuevo(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    """Contrasena temporal, cambio obligatorio, enrolamiento y entra (primer ingreso del Admin)."""
    usuario = crear_usuario(roles=("administrador",), debe_cambiar_contrasena=True)
    assert _ingresar(cliente)["Location"] == "/ingresar/contrasena"
    nueva = "frase-nueva-larga-42"
    despues = cliente.post("/ingresar/contrasena", {"nueva": nueva, "confirmar": nueva})
    assert (despues.status_code, despues["Location"]) == (302, "/ingresar/enrolar")
    assert "_auth_user_id" not in cliente.session
    pagina = cliente.get("/ingresar/enrolar").content.decode()
    clave = re.search(r'<code id="clave">([^<]+)</code>', pagina)
    assert clave
    from identidad.pruebas.test_escenarios_segundo_factor import _secreto_de

    secreto = _secreto_de(clave.group(1))
    entrada = cliente.post("/ingresar/enrolar", {"codigo": _bueno(secreto)})
    assert (entrada.status_code, entrada["Location"]) == (302, "/")
    assert cliente.get("/").status_code == 200
    # Segundo ingreso: ya no cambia la contrasena ni se enrola, sino que pide el codigo.
    segundo = Client()
    assert _ingresar(segundo, contrasena=nueva)["Location"] == "/ingresar/codigo"
    assert SegundoFactor.objects.get(usuario=usuario).confirmado_en is not None


def test_con_la_temporal_y_ya_enrolado_el_cambio_obligatorio_sigue_con_el_codigo(
    cliente: Client,
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable[..., bytes],
) -> None:
    usuario = crear_usuario(roles=("auditor",), debe_cambiar_contrasena=True)
    registrar_segundo_factor(usuario)
    assert _ingresar(cliente)["Location"] == "/ingresar/contrasena"
    nueva = "frase-nueva-larga-42"
    despues = cliente.post("/ingresar/contrasena", {"nueva": nueva, "confirmar": nueva})
    assert (despues.status_code, despues["Location"]) == (302, "/ingresar/codigo")


def test_el_cambio_obligatorio_de_un_rol_comun_sigue_entrando_directo(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    crear_usuario(roles=("usuario",), debe_cambiar_contrasena=True)
    _ingresar(cliente)
    nueva = "frase-nueva-larga-42"
    despues = cliente.post("/ingresar/contrasena", {"nueva": nueva, "confirmar": nueva})
    assert (despues.status_code, despues["Location"]) == (302, "/")


def test_un_rol_comun_nunca_ve_las_etapas_del_segundo_factor(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    crear_usuario(roles=("usuario",))
    assert _ingresar(cliente)["Location"] == "/"
    # Con sesion completa, las rutas del segundo factor no tienen nada que hacer.
    for ruta in ("/ingresar/enrolar", "/ingresar/codigo"):
        respuesta = cliente.get(ruta)
        assert (respuesta.status_code, respuesta["Location"]) == (302, "/ingresar")


@pytest.mark.parametrize("ruta", ["/ingresar/enrolar", "/ingresar/codigo"])
def test_sin_etapa_pendiente_las_rutas_del_segundo_factor_mandan_a_ingresar(
    cliente: Client, ruta: str
) -> None:
    for metodo in (cliente.get, cliente.post):
        respuesta = metodo(ruta)
        assert (respuesta.status_code, respuesta["Location"]) == (302, "/ingresar")


# --- Cada etapa solo admite su ruta ---------------------------------------------------------------


def test_en_la_etapa_del_codigo_las_otras_rutas_redirigen_al_codigo(
    con_codigo_pendiente: tuple[Client, Usuario, bytes],
) -> None:
    cliente, _, _ = con_codigo_pendiente
    for ruta in ("/", "/cuenta/contrasena", "/ingresar/enrolar", "/ingresar/contrasena"):
        respuesta = cliente.get(ruta)
        assert (respuesta.status_code, respuesta["Location"]) == (302, "/ingresar/codigo"), ruta
    assert cliente.get("/ingresar/codigo").status_code == 200
    assert cliente.get("/salud").status_code == 200  # las rutas publicas siguen


def test_en_la_etapa_de_enrolamiento_las_otras_rutas_redirigen_al_enrolamiento(
    con_enrolamiento_pendiente: tuple[Client, Usuario],
) -> None:
    cliente, _ = con_enrolamiento_pendiente
    for ruta in ("/", "/cuenta/contrasena", "/ingresar/codigo", "/ingresar/contrasena"):
        respuesta = cliente.get(ruta)
        assert (respuesta.status_code, respuesta["Location"]) == (302, "/ingresar/enrolar"), ruta


def test_quien_esta_en_la_etapa_del_codigo_no_puede_saltarse_al_enrolamiento(
    con_codigo_pendiente: tuple[Client, Usuario, bytes],
) -> None:
    """Postear un codigo a la ruta de la otra etapa no abre sesion."""
    cliente, _, secreto = con_codigo_pendiente
    respuesta = cliente.post("/ingresar/enrolar", {"codigo": _bueno(secreto)})
    assert (respuesta.status_code, respuesta["Location"]) == (302, "/ingresar/codigo")
    assert "_auth_user_id" not in cliente.session


def test_un_nuevo_ingreso_descarta_la_etapa_pendiente_anterior(
    con_codigo_pendiente: tuple[Client, Usuario, bytes],
) -> None:
    cliente, _, _ = con_codigo_pendiente
    assert CLAVE_ETAPA in cliente.session
    assert MENSAJE_FALLO in _ingresar(cliente, contrasena="mala").content.decode()
    assert CLAVE_ETAPA not in cliente.session


MENSAJE_FALLO = "Correo o contraseña incorrectos"


# --- La etapa guarda el sello y una marca de tiempo, y expira como la de --------------------


def test_la_etapa_del_codigo_guarda_usuario_sello_y_marca_de_tiempo(
    con_codigo_pendiente: tuple[Client, Usuario, bytes],
) -> None:
    cliente, usuario, _ = con_codigo_pendiente
    etapa = dict(cliente.session[CLAVE_ETAPA])
    assert etapa["etapa"] == "codigo_pendiente"
    assert etapa["usuario_id"] == str(usuario.id)
    assert etapa["sello"] == str(usuario.sello_sesion)
    assert etapa["creada_en"]
    assert "iniciada_en" not in cliente.session  # solo al COMPLETAR el ingreso


def test_la_etapa_del_enrolamiento_guarda_usuario_sello_y_marca_de_tiempo(
    con_enrolamiento_pendiente: tuple[Client, Usuario],
) -> None:
    cliente, usuario = con_enrolamiento_pendiente
    etapa = dict(cliente.session[CLAVE_ETAPA])
    assert etapa["etapa"] == "enrolamiento_pendiente"
    assert (etapa["usuario_id"], etapa["sello"]) == (str(usuario.id), str(usuario.sello_sesion))


def test_la_etapa_del_codigo_expira_a_los_15_minutos(
    cliente: Client,
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable[..., bytes],
    reloj: RelojAdelantable,
) -> None:
    usuario = crear_usuario(roles=("auditor",))
    secreto = registrar_segundo_factor(usuario)
    _ingresar(cliente)
    reloj.adelantar(minutes=14, seconds=59)
    assert cliente.get("/ingresar/codigo").status_code == 200
    reloj.adelantar(seconds=2)
    respuesta = cliente.post("/ingresar/codigo", {"codigo": _bueno(secreto, reloj)})
    assert (respuesta.status_code, respuesta["Location"]) == (302, "/ingresar")
    assert "_auth_user_id" not in cliente.session


def test_la_etapa_del_enrolamiento_expira_a_los_15_minutos(
    con_enrolamiento_pendiente: tuple[Client, Usuario], reloj: RelojAdelantable
) -> None:
    cliente, _ = con_enrolamiento_pendiente
    reloj.adelantar(minutes=15, seconds=1)
    respuesta = cliente.get("/ingresar/enrolar")
    assert (respuesta.status_code, respuesta["Location"]) == (302, "/ingresar")
    assert CLAVE_ETAPA not in cliente.session


# --- Revalidacion al completar: la cuenta cambio con la etapa abierta -----------------------------


def test_si_cambia_el_sello_con_el_codigo_pendiente_no_se_abre_la_sesion(
    con_codigo_pendiente: tuple[Client, Usuario, bytes],
) -> None:
    cliente, usuario, secreto = con_codigo_pendiente
    RepositorioCuentasDjango().rotar_sello(str(usuario.pk))  # p. ej. restablecieron la contrasena
    respuesta = cliente.post("/ingresar/codigo", {"codigo": _bueno(secreto)})
    assert respuesta.status_code == 200
    assert VENCIDA in respuesta.content.decode()
    assert "_auth_user_id" not in cliente.session
    assert CLAVE_ETAPA not in cliente.session


def test_si_cambia_el_sello_con_el_enrolamiento_pendiente_no_se_confirma(
    con_enrolamiento_pendiente: tuple[Client, Usuario],
) -> None:
    cliente, usuario = con_enrolamiento_pendiente
    secreto_antes = SegundoFactor.objects.filter(usuario=usuario).first()
    RepositorioCuentasDjango().rotar_sello(str(usuario.pk))
    respuesta = cliente.get("/ingresar/enrolar")
    assert VENCIDA in respuesta.content.decode()
    assert "_auth_user_id" not in cliente.session
    assert secreto_antes is None or not secreto_antes.confirmado_en


def test_una_cuenta_desactivada_con_la_etapa_abierta_no_entra(
    con_codigo_pendiente: tuple[Client, Usuario, bytes],
) -> None:
    cliente, usuario, secreto = con_codigo_pendiente
    Usuario.objects.filter(pk=usuario.pk).update(activo=False)
    respuesta = cliente.post("/ingresar/codigo", {"codigo": _bueno(secreto)})
    assert VENCIDA in respuesta.content.decode()
    assert "_auth_user_id" not in cliente.session


def test_si_el_rol_sensible_se_quita_con_la_etapa_abierta_no_se_abre_la_sesion(
    con_codigo_pendiente: tuple[Client, Usuario, bytes],
) -> None:
    cliente, usuario, secreto = con_codigo_pendiente
    usuario.asignaciones.all().delete()  # ya no tiene ningun rol
    respuesta = cliente.post("/ingresar/codigo", {"codigo": _bueno(secreto)})
    assert VENCIDA in respuesta.content.decode()
    assert "_auth_user_id" not in cliente.session


def test_otra_sesion_que_bloqueo_la_cuenta_corta_la_etapa_abierta(
    con_codigo_pendiente: tuple[Client, Usuario, bytes],
) -> None:
    cliente, _, secreto = con_codigo_pendiente
    otro = Client()
    _ingresar(otro)
    for _ in range(5):
        otro.post("/ingresar/codigo", {"codigo": _malo(secreto)})
    respuesta = cliente.post("/ingresar/codigo", {"codigo": _bueno(secreto)})
    assert respuesta.status_code == 403
    assert "bloqueada 15 minutos" in respuesta.content.decode()
    assert "_auth_user_id" not in cliente.session


# --- Falla cerrado: la red de seguridad sigue -----------------------------------------------------


def test_sin_adaptador_en_la_etapa_del_codigo_no_se_abre_la_sesion(
    con_codigo_pendiente: tuple[Client, Usuario, bytes],
) -> None:
    cliente, usuario, secreto = con_codigo_pendiente
    with Aislamiento():
        respuesta = cliente.post("/ingresar/codigo", {"codigo": _bueno(secreto)})
    assert respuesta.status_code == 403
    assert REQUIERE in respuesta.content.decode()
    assert "_auth_user_id" not in cliente.session
    assert IntentoIngreso.objects.filter(
        usuario_id=usuario.id, motivo="requiere_segundo_factor", factor="codigo"
    ).exists()


def test_sin_adaptador_en_la_etapa_de_enrolamiento_no_se_muestra_ni_se_genera_nada(
    con_enrolamiento_pendiente: tuple[Client, Usuario],
) -> None:
    cliente, usuario = con_enrolamiento_pendiente
    SegundoFactor.objects.filter(usuario=usuario).delete()
    with Aislamiento():
        respuesta = cliente.get("/ingresar/enrolar")
    assert respuesta.status_code == 403
    assert REQUIERE in respuesta.content.decode()
    assert not SegundoFactor.objects.filter(usuario=usuario).exists()


def test_sin_llave_un_rol_sensible_no_entra_ni_se_enrola(
    cliente: Client, crear_usuario: Callable[..., Usuario], settings: Any
) -> None:
    crear_usuario(roles=("administrador",))
    settings.APP_LLAVE_SEGUNDO_FACTOR = ""
    respuesta = _ingresar(cliente)
    assert respuesta.status_code == 403
    assert REQUIERE in respuesta.content.decode()
    assert "_auth_user_id" not in cliente.session
    assert not SegundoFactor.objects.exists()


def test_si_cambia_la_llave_el_ingreso_de_los_ya_enrolados_falla_cerrado(
    cliente: Client,
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable[..., bytes],
    settings: Any,
) -> None:
    usuario = crear_usuario(roles=("auditor",))
    registrar_segundo_factor(usuario)
    settings.APP_LLAVE_SEGUNDO_FACTOR = "otra-llave-completamente-distinta-0123456789-abcdefghij"
    respuesta = _ingresar(cliente)
    assert respuesta.status_code == 403
    assert REQUIERE in respuesta.content.decode()


# --- Un codigo nunca abre la sesion si no es el de la etapa ---------------------------------------


def test_un_codigo_bueno_abre_la_sesion_con_la_marca_de_ingreso(
    con_codigo_pendiente: tuple[Client, Usuario, bytes],
) -> None:
    cliente, _, secreto = con_codigo_pendiente
    clave_antes = cliente.session.session_key
    respuesta = cliente.post("/ingresar/codigo", {"codigo": _bueno(secreto)})
    assert (respuesta.status_code, respuesta["Location"]) == (302, "/")
    assert "iniciada_en" in cliente.session
    assert CLAVE_ETAPA not in cliente.session
    assert cliente.session.session_key != clave_antes  # la sesion rota: sin fijacion de sesion
    assert cliente.get("/").status_code == 200


def test_cada_etapa_rota_la_clave_de_sesion(
    cliente: Client, crear_usuario: Callable[..., Usuario]
) -> None:
    crear_usuario(roles=("auditor",), debe_cambiar_contrasena=True)
    claves = [cliente.session.session_key]
    _ingresar(cliente)
    claves.append(cliente.session.session_key)
    nueva = "frase-nueva-larga-42"
    cliente.post("/ingresar/contrasena", {"nueva": nueva, "confirmar": nueva})
    claves.append(cliente.session.session_key)
    assert len(set(claves)) == 3


def test_el_codigo_acepta_los_espacios_que_muestra_la_aplicacion(
    con_codigo_pendiente: tuple[Client, Usuario, bytes],
) -> None:
    cliente, _, secreto = con_codigo_pendiente
    bueno = _bueno(secreto)
    respuesta = cliente.post("/ingresar/codigo", {"codigo": f" {bueno[:3]} {bueno[3:]} "})
    assert respuesta["Location"] == "/"


def test_un_codigo_larguisimo_o_sin_el_campo_no_rompe_nada(
    con_codigo_pendiente: tuple[Client, Usuario, bytes],
) -> None:
    cliente, usuario, _ = con_codigo_pendiente
    assert cliente.post("/ingresar/codigo", {"codigo": "9" * 100000}).status_code == 422
    assert cliente.post("/ingresar/codigo", {}).status_code == 422
    assert Usuario.objects.get(pk=usuario.pk).fallos_codigo == 2
    assert "_auth_user_id" not in cliente.session


def test_un_codigo_incorrecto_en_el_enrolamiento_conserva_el_mismo_qr(
    con_enrolamiento_pendiente: tuple[Client, Usuario],
) -> None:
    cliente, _ = con_enrolamiento_pendiente
    primera = cliente.get("/ingresar/enrolar").content.decode()
    clave = re.search(r'<code id="clave">([^<]+)</code>', primera)
    assert clave
    fallida = cliente.post("/ingresar/enrolar", {"codigo": "000000"})
    assert fallida.status_code == 422
    assert clave.group(1) in fallida.content.decode()  # la misma clave: su app sigue sirviendo
    assert "El código no es correcto" in fallida.content.decode()


def test_la_clave_se_muestra_en_grupos_de_cuatro(
    con_enrolamiento_pendiente: tuple[Client, Usuario],
) -> None:
    cliente, _ = con_enrolamiento_pendiente
    pagina = cliente.get("/ingresar/enrolar").content.decode()
    clave = re.search(r'<code id="clave">([^<]+)</code>', pagina)
    assert clave
    assert re.fullmatch(r"([A-Z2-7]{4} ){7}[A-Z2-7]{4}", clave.group(1))  # 32 caracteres Base32


# --- Cabeceras, CSRF y datos sensibles ------------------------------------------------------------


def test_la_pantalla_del_codigo_no_se_guarda_en_cache(
    con_codigo_pendiente: tuple[Client, Usuario, bytes],
) -> None:
    cliente, _, _ = con_codigo_pendiente
    assert "no-store" in cliente.get("/ingresar/codigo")["Cache-Control"]


def test_la_pantalla_del_enrolamiento_con_el_secreto_no_se_guarda_en_cache(
    con_enrolamiento_pendiente: tuple[Client, Usuario],
) -> None:
    cliente, _ = con_enrolamiento_pendiente
    assert "no-store" in cliente.get("/ingresar/enrolar")["Cache-Control"]


def test_las_dos_pantallas_marcan_el_codigo_como_parametro_sensible(
    con_enrolamiento_pendiente: tuple[Client, Usuario],
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable[..., bytes],
) -> None:
    cliente, _ = con_enrolamiento_pendiente
    en_enrolamiento: Any = cliente.post("/ingresar/enrolar", {"codigo": "000000"})
    assert tuple(en_enrolamiento.wsgi_request.sensitive_post_parameters) == ("codigo",)
    otro = Client()
    usuario = crear_usuario(correo="luis@empresa.example", roles=("auditor",))
    registrar_segundo_factor(usuario)
    _ingresar(otro, correo="luis@empresa.example")
    en_codigo: Any = otro.post("/ingresar/codigo", {"codigo": "000000"})
    assert tuple(en_codigo.wsgi_request.sensitive_post_parameters) == ("codigo",)


@pytest.mark.parametrize("ruta", ["/ingresar/enrolar", "/ingresar/codigo"])
def test_los_posts_del_segundo_factor_exigen_el_token_csrf(
    crear_usuario: Callable[..., Usuario],
    registrar_segundo_factor: Callable[..., bytes],
    ruta: str,
) -> None:
    usuario = crear_usuario(roles=("auditor",))
    if ruta.endswith("codigo"):
        registrar_segundo_factor(usuario)
    estricto = Client(enforce_csrf_checks=True)
    get_csrf = estricto.get("/ingresar")
    token = get_csrf.cookies["csrftoken"].value
    # Ingresa con el token (el formulario de ingreso lo lleva)...
    assert (
        estricto.post(
            "/ingresar", {"correo": CORREO, "contrasena": CONTRASENA, "csrfmiddlewaretoken": token}
        )["Location"]
        == ruta
    )
    # ...y el POST del codigo, sin token, se rechaza.
    assert estricto.post(ruta, {"codigo": "000000"}).status_code == 403


def test_el_secreto_no_queda_en_la_sesion_ni_en_el_registro(
    con_enrolamiento_pendiente: tuple[Client, Usuario],
) -> None:
    cliente, usuario = con_enrolamiento_pendiente
    pagina = cliente.get("/ingresar/enrolar").content.decode()
    clave = re.search(r'<code id="clave">([^<]+)</code>', pagina)
    assert clave
    sin_espacios = clave.group(1).replace(" ", "")
    assert sin_espacios not in str(dict(cliente.session))
    assert sin_espacios not in SegundoFactor.objects.get(usuario=usuario).secreto_cifrado
    assert sin_espacios not in str(list(IntentoIngreso.objects.values()))


# --- CSP: el QR no relaja nada --------------------------------------------------------------------


def test_con_la_csp_de_produccion_la_pantalla_del_qr_no_necesita_nada_mas(
    con_enrolamiento_pendiente: tuple[Client, Usuario],
) -> None:
    cliente, _ = con_enrolamiento_pendiente
    with override_settings(
        MIDDLEWARE=[
            "django.middleware.security.SecurityMiddleware",
            "configuracion.seguridad.EncabezadoCSPMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.common.CommonMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "identidad.adaptadores.entrada.middleware.ActorMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
            "django.middleware.clickjacking.XFrameOptionsMiddleware",
        ],
        CONTENT_SECURITY_POLICY=CSP_ESTRICTA,
    ):
        # Un cliente nuevo (la cadena de middleware se arma al primer uso) con la misma sesion.
        con_csp = Client()
        con_csp.cookies = cliente.cookies
        respuesta = con_csp.get("/ingresar/enrolar")
    assert respuesta["Content-Security-Policy"] == CSP_ESTRICTA
    html = respuesta.content.decode()
    # Todo lo que la CSP `default-src 'self'` bloquearia: nada de eso esta en la pagina.
    assert "<svg" in html and '<path d="M' in html
    for etiqueta in ("<script", "<style", "<img", "<iframe", "<object", "<embed"):
        assert etiqueta not in html, etiqueta
    assert not re.search(r"\sstyle\s*=", html, re.IGNORECASE)
    assert not re.search(r"\son[a-z]+\s*=", html, re.IGNORECASE)
    assert "javascript:" not in html.lower()
    assert "data:" not in html.lower()
    # Las hojas de estilo son archivos propios del mismo origen.
    assert re.findall(r'<link[^>]+href="([^"]+)"', html) == ["/estilos/identidad.css"]


# --- Reflejo del correo ya normalizado ------------------------------


@pytest.mark.parametrize(
    "borde", ["\x1c", "\x1d", "\x1e", "\x1f", "\x0b", "\x0c", " ", "\t", "\x85", " "]
)
def test_el_correo_reflejado_es_el_normalizado_sin_caracteres_de_control_en_los_extremos(
    cliente: Client, borde: str
) -> None:
    pagina = _ingresar(cliente, correo=f"{borde}Otra@Empresa.Example{borde}").content.decode()
    assert 'value="otra@empresa.example"' in pagina
    assert borde not in pagina if borde.strip() == "" and borde not in "\t " else True
    assert not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", pagina)


def test_el_correo_con_control_en_el_medio_sigue_sin_reflejarse(cliente: Client) -> None:
    pagina = _ingresar(cliente, correo="a\x1cb@empresa.example").content.decode()
    assert 'value=""' in pagina
    assert "\x1c" not in pagina


def test_lo_que_se_refleja_es_lo_que_se_valido(cliente: Client) -> None:
    """El formulario del fallo vuelve con el mismo valor normalizado con el que se busco."""
    pagina = _ingresar(
        cliente, correo="\x1c  ANA@Empresa.Example \x1f", contrasena="mala"
    ).content.decode()
    assert 'value="ana@empresa.example"' in pagina


def test_un_correo_de_solo_caracteres_de_control_no_se_refleja(cliente: Client) -> None:
    pagina = _ingresar(cliente, correo="\x1c\x1d\x1e\x1f").content.decode()
    assert 'value=""' in pagina


# --- El tiempo del bloqueo del codigo usa el reloj inyectado --------------------------------------


def test_el_bloqueo_por_codigos_dura_15_minutos_con_el_reloj_inyectado(
    con_codigo_pendiente: tuple[Client, Usuario, bytes], reloj: RelojAdelantable
) -> None:
    cliente, usuario, secreto = con_codigo_pendiente
    for _ in range(5):
        cliente.post("/ingresar/codigo", {"codigo": _malo(secreto)})
    bloqueada = Usuario.objects.get(pk=usuario.pk).bloqueada_hasta
    assert bloqueada is not None
    assert abs((bloqueada - reloj.ahora()) - timedelta(minutes=15)) < timedelta(seconds=5)
