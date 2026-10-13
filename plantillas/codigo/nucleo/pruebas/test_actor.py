"""`Actor` (DISENO D.1.3): valor inmutable, validado y sin dependencias de ningun modulo."""

import dataclasses

import pytest

from nucleo.actor import Actor


def _usuario() -> Actor:
    return Actor(id="u-1", roles=frozenset({"usuario"}))


# --- Construccion y lectura ---------------------------------------------------------------------


def test_un_actor_guarda_identificador_y_roles() -> None:
    actor = _usuario()
    assert (actor.id, actor.roles) == ("u-1", frozenset({"usuario"}))


def test_de_acepta_cualquier_iterable_y_quita_repetidos() -> None:
    desde_lista = Actor.de("u-3", ["usuario", "auditor", "usuario"])
    assert desde_lista.roles == frozenset({"usuario", "auditor"})


def test_los_roles_se_copian_y_no_comparten_el_conjunto_original() -> None:
    origen = {"usuario"}
    actor = Actor(id="u-4", roles=origen)  # type: ignore[arg-type]
    origen.add("administrador")
    assert actor.roles == frozenset({"usuario"})


def test_un_actor_sin_roles_no_tiene_ninguno() -> None:
    actor = Actor(id="u-5", roles=frozenset())
    assert not actor.tiene_rol("usuario")
    assert not actor.tiene_algun_rol("usuario", "administrador")


def test_tiene_rol_es_exacto() -> None:
    actor = _usuario()
    assert actor.tiene_rol("usuario")
    assert not actor.tiene_rol("USUARIO")


def test_tiene_algun_rol_basta_con_uno() -> None:
    actor = _usuario()
    assert actor.tiene_algun_rol("administrador", "usuario")
    assert not actor.tiene_algun_rol("administrador", "auditor")
    assert not actor.tiene_algun_rol()


# --- Inmutabilidad -------------------------------------------------------------------------------


@pytest.mark.parametrize(("campo", "valor"), [("id", "otro"), ("roles", frozenset({"x"}))])
def test_un_actor_es_inmutable(campo: str, valor: object) -> None:
    actor = _usuario()
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(actor, campo, valor)


def test_los_roles_no_se_pueden_modificar_en_el_lugar() -> None:
    assert not hasattr(_usuario().roles, "add")


def test_no_admite_atributos_nuevos() -> None:
    actor = _usuario()
    with pytest.raises((AttributeError, TypeError)):
        actor.extra = 1  # type: ignore[attr-defined]


def test_dos_actores_iguales_son_iguales_y_hashables() -> None:
    assert _usuario() == Actor.de("u-1", ["usuario"])
    assert len({_usuario(), Actor.de("u-1", ["usuario"])}) == 1
    assert _usuario() != Actor.de("u-2", ["usuario"])


# --- Validaciones --------------------------------------------------------------------------------


@pytest.mark.parametrize("identificador", ["", "   ", "\t\n"])
def test_el_identificador_no_puede_ser_vacio(identificador: str) -> None:
    with pytest.raises(ValueError, match=r"Actor\.id"):
        Actor(id=identificador, roles=frozenset({"usuario"}))


@pytest.mark.parametrize("rol", ["", " "])
def test_un_rol_no_puede_ser_vacio(rol: str) -> None:
    with pytest.raises(ValueError, match=r"Actor\.roles"):
        Actor(id="u-1", roles=frozenset({rol}))


def test_los_roles_no_pueden_ser_un_texto_suelto() -> None:
    with pytest.raises(ValueError, match=r"Actor\.roles"):
        Actor(id="u-1", roles="usuario")  # type: ignore[arg-type]


def test_de_rechaza_un_texto_suelto_en_vez_de_partirlo_en_letras() -> None:
    with pytest.raises(ValueError, match=r"Actor\.roles"):
        Actor.de("1", "usuario")


@pytest.mark.parametrize("roles", [None, 5, [["x"]], [{"x"}], [{}], ["x", []]])
def test_roles_nulos_o_no_hasheables_lanzan_value_error_y_no_type_error(roles: object) -> None:
    with pytest.raises(ValueError, match=r"Actor\.roles"):
        Actor(id="u-1", roles=roles)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match=r"Actor\.roles"):
        Actor.de("u-1", roles)  # type: ignore[arg-type]


def test_roles_con_elementos_que_no_son_texto_lanzan_value_error() -> None:
    with pytest.raises(ValueError, match=r"Actor\.roles"):
        Actor.de("u-1", ["usuario", 7])  # type: ignore[list-item]


def test_de_acepta_un_generador_de_roles() -> None:
    actor = Actor.de("u-1", (rol for rol in ("usuario", "auditor")))
    assert actor.roles == frozenset({"usuario", "auditor"})


class _TextoFalso(str):
    """Subclase de `str` que dice ser igual a cualquier cosa."""

    __slots__ = ()

    def __eq__(self, otro: object) -> bool:
        return True

    def __hash__(self) -> int:
        return hash("usuario")


def test_una_subclase_de_str_con_eq_alterado_se_rechaza_en_el_id() -> None:
    with pytest.raises(ValueError, match=r"Actor\.id"):
        Actor(id=_TextoFalso("u-1"), roles=frozenset({"usuario"}))


def test_una_subclase_de_str_con_eq_alterado_se_rechaza_como_rol() -> None:
    with pytest.raises(ValueError, match=r"Actor\.roles"):
        Actor(id="u-1", roles=frozenset({_TextoFalso("administrador")}))
    with pytest.raises(ValueError, match=r"Actor\.roles"):
        Actor.de("u-1", [_TextoFalso("administrador")])


# --- Serializacion: copiar o des-serializar vuelve a validar -------------------------------------


def _carga_manipulada(**cambios: object) -> bytes:
    """Un pickle de un `Actor` valido cuyos datos se alteran a mano, como lo haria un atacante."""
    import pickle

    original = _usuario()
    llamable = original.__reduce__()[0]
    datos: dict[str, object] = {"id": original.id, "roles": original.roles}
    datos.update(cambios)

    class _Receta:
        def __reduce__(self) -> tuple[object, tuple[object, ...]]:
            return llamable, tuple(datos.values())

    return pickle.dumps(_Receta(), protocol=4)


def test_un_actor_valido_sobrevive_a_pickle_y_a_copy() -> None:
    import copy
    import pickle

    actor = _usuario()
    assert pickle.loads(pickle.dumps(actor)) == actor  # noqa: S301  # nosec B301
    assert copy.copy(actor) == actor
    assert copy.deepcopy(actor) == actor


@pytest.mark.parametrize(
    ("cambio", "campo"),
    [
        ({"id": ""}, r"Actor\.id"),
        ({"roles": ""}, r"Actor\.roles"),
        ({"roles": frozenset({""})}, r"Actor\.roles"),
    ],
)
def test_un_pickle_manipulado_no_entra_sin_validar(cambio: dict[str, object], campo: str) -> None:
    import pickle

    carga = _carga_manipulada(**cambio)
    with pytest.raises(ValueError, match=campo):
        pickle.loads(carga)  # noqa: S301  # nosec B301


def test_el_estado_manipulado_por_setstate_tampoco_entra_sin_validar() -> None:
    """Las rutas antiguas (`__setstate__` directo, `copy` con estado) revalidan igual."""
    actor = _usuario()
    with pytest.raises(ValueError, match=r"Actor\.id"):
        actor.__setstate__({"id": "", "roles": frozenset({"usuario"})})
