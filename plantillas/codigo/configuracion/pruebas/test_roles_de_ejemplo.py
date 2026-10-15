"""El esqueleto no anuncia como existente lo que no trae (la bitacora) y documenta como se
reemplazan los roles de ejemplo. Si cambias los roles, actualiza tambien la seccion del README."""

import re
from pathlib import Path

from identidad.dominio.roles import AUDITOR, CATALOGO_DE_ROLES, USUARIO
from nucleo.permisos import CAPACIDADES_POR_ROL, DESCRIPCIONES, Capacidad

CODIGO = Path(__file__).resolve().parents[2]
README = (CODIGO / "README.md").read_text(encoding="utf-8")
_DESDE_EL_TITULO = README.split("### Reemplazar los roles de ejemplo", 1)[1]
SECCION = _DESDE_EL_TITULO.split("\n- **Matriz de permisos**", 1)[0]


def test_la_bitacora_es_un_ejemplo_marcado_y_el_administrador_no_la_anuncia() -> None:
    assert "ejemplo" in DESCRIPCIONES[Capacidad.CONSULTAR_BITACORA].lower()
    assert Capacidad.CONSULTAR_BITACORA not in CAPACIDADES_POR_ROL["administrador"]


def test_los_roles_de_ejemplo_son_los_dos_que_documenta_el_readme() -> None:
    assert set(CATALOGO_DE_ROLES) == {"administrador", AUDITOR, USUARIO}
    assert "`auditor`" in SECCION
    assert "`usuario`" in SECCION
    assert len(re.findall(r"^\d+\. ", SECCION, flags=re.MULTILINE)) >= 5


def test_los_archivos_que_nombra_la_seccion_existen() -> None:
    rutas = set(re.findall(r"`((?:identidad|nucleo)/[\w/.]+\.py)`", SECCION))
    assert {"identidad/dominio/roles.py", "nucleo/permisos.py"} <= rutas
    for ruta in rutas:
        assert (CODIGO / ruta).is_file(), ruta


def test_el_readme_no_anuncia_una_bitacora_existente() -> None:
    assert "listo para la bitacora" not in README
