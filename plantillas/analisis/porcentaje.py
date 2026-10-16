"""Formato del porcentaje de avance que usan `plan_sprints.py` (PLAN.md) y el tablero HTML.

La misma regla está en la función `porcentaje` de `plan_sprints_plantilla.html`; si cambia una, cambia la otra.

- Cero puntos terminados: `0 %`. Todo terminado: `100 %`.
- Menos de 10 %: un decimal, truncado (3 de 327 es `0.9 %`, no `0 %`); si ni así llega a una décima, `<0.1 %`.
- 10 % o más: entero truncado, para no mostrar `100 %` antes de terminar (326 de 327 es `99 %`).
"""


def formatear_porcentaje(hechos: int, total: int) -> str:
    """El porcentaje de `hechos` sobre `total` como texto, por ejemplo `0.9 %`, `42 %` o `<0.1 %`."""
    if total <= 0 or hechos <= 0:
        return "0 %"
    if hechos >= total:
        return "100 %"
    decimas = hechos * 1000 // total  # décimas de punto porcentual, truncadas
    if decimas >= 100:
        return f"{decimas // 10} %"
    if decimas == 0:
        return "<0.1 %"
    return f"{decimas / 10:.1f} %"
