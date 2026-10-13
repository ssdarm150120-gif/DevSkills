from django.test import Client


def test_salud_responde_ok() -> None:
    respuesta = Client().get("/salud")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}


def test_salud_responde_a_head_sin_cuerpo() -> None:
    respuesta = Client().head("/salud")
    assert respuesta.status_code == 200
    assert respuesta.content == b""


def test_salud_rechaza_los_metodos_que_no_son_seguros() -> None:
    cliente = Client()
    assert cliente.post("/salud").status_code == 405
    assert cliente.put("/salud").status_code == 405
    assert cliente.delete("/salud").status_code == 405


def test_salud_es_publica_aunque_drf_deniegue_por_defecto() -> None:
    # Sin sesion ni credenciales: la vista de liveness no depende de DRF ni de autenticacion.
    assert Client().get("/salud").status_code == 200
