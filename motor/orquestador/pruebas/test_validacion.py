import pytest

from nucleo import validacion as v
from nucleo.registro import cargar

PERMITIDOS = {"alfa", "beta"}


def test_registro_solo_admite_ids_validos_y_rutas_absolutas(entorno):
    proyectos = cargar(entorno["ajustes"].registro)
    assert set(proyectos) == {"alfa", "beta"}


def test_instruccion_valida():
    d = v.instruccion({"proyecto": "alfa", "texto": "  resume  ", "modo": "lectura"}, PERMITIDOS, 100)
    assert d == {"proyecto": "alfa", "texto": "resume", "modo": "lectura", "nueva_sesion": False,
                 "contexto": "auto"}


@pytest.mark.parametrize("contexto", ["auto", "sesion", "grafo"])
def test_contexto_valido(contexto):
    d = v.instruccion({"proyecto": "alfa", "texto": "x", "modo": "lectura", "contexto": contexto}, PERMITIDOS, 100)
    assert d["contexto"] == contexto


@pytest.mark.parametrize("contexto", ["", "GRAFO", "todo", None, 1, ["grafo"]])
def test_contexto_invalido(contexto):
    with pytest.raises(v.ErrorValidacion):
        v.instruccion({"proyecto": "alfa", "texto": "x", "modo": "lectura", "contexto": contexto}, PERMITIDOS, 100)


def test_nueva_sesion_contradice_contexto_sesion():
    with pytest.raises(v.ErrorValidacion):
        v.instruccion({"proyecto": "alfa", "texto": "x", "modo": "lectura", "contexto": "sesion",
                       "nueva_sesion": True}, PERMITIDOS, 100)


@pytest.mark.parametrize("proyecto", ["gamma", "../alfa", "C:\\x", "ALFA", "", None, 5, "alfa/../beta"])
def test_proyecto_fuera_de_lista_blanca(proyecto):
    with pytest.raises(v.ErrorValidacion):
        v.instruccion({"proyecto": proyecto, "texto": "x", "modo": "lectura"}, PERMITIDOS, 100)


@pytest.mark.parametrize("texto", ["", "   ", "x" * 101, "hola\x00", "a\x1bb", 3, None])
def test_texto_invalido(texto):
    with pytest.raises(v.ErrorValidacion):
        v.instruccion({"proyecto": "alfa", "texto": texto, "modo": "lectura"}, PERMITIDOS, 100)


@pytest.mark.parametrize("modo", ["escritura", "LECTURA", "", None])
def test_modo_invalido(modo):
    with pytest.raises(v.ErrorValidacion):
        v.instruccion({"proyecto": "alfa", "texto": "x", "modo": modo}, PERMITIDOS, 100)


@pytest.mark.parametrize("extra", ["carpeta", "cwd", "ruta", "session_id", "resume", "permission_mode", "tools"])
def test_campos_extra_como_rutas_o_permisos_se_rechazan(extra):
    with pytest.raises(v.ErrorValidacion, match="no permitidos"):
        v.instruccion({"proyecto": "alfa", "texto": "x", "modo": "lectura", extra: "C:\\Windows"}, PERMITIDOS, 100)


def test_nueva_sesion_debe_ser_booleano():
    with pytest.raises(v.ErrorValidacion):
        v.instruccion({"proyecto": "alfa", "texto": "x", "modo": "lectura", "nueva_sesion": "si"}, PERMITIDOS, 100)


@pytest.mark.parametrize("iid", ["20261026-120000-abcdef"])
def test_id_valido(iid):
    assert v.id_instruccion(iid) == iid


@pytest.mark.parametrize("iid", ["../x", "20261026-120000-ABCDEF", "20261026-120000-abcdef.json", ""])
def test_id_invalido(iid):
    with pytest.raises(v.ErrorValidacion):
        v.id_instruccion(iid)


def test_confirmacion_exige_repetir_el_id():
    iid = "20261026-120000-abcdef"
    v.confirmacion({"confirmacion": iid}, iid)
    for cuerpo in ({}, {"confirmacion": True}, {"confirmacion": "si"}, {"confirmacion": iid, "x": 1}):
        with pytest.raises(v.ErrorValidacion):
            v.confirmacion(cuerpo, iid)


def test_consulta_limitada():
    assert v.consulta(" engram ", 10) == "engram"
    with pytest.raises(v.ErrorValidacion):
        v.consulta("x" * 11, 10)
