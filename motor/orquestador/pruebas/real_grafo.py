"""Prueba REAL mínima (no la corre pytest): instrucción de solo lectura con contexto "grafo" contra un proyecto con
graph.json. Usa la API del ejecutor directamente con un registro temporal que apunta a la carpeta indicada, sin
tocar `proyectos.json`. Gasta tokens (una llamada al modelo; dos si se enruta y escala).

  .venv\\Scripts\\python.exe pruebas\\real_grafo.py <carpeta> [id] ["instrucción"] [--enrutado]

--enrutado: el registro temporal marca `enrutamiento.activo: true` (lectura → sonnet con esfuerzo medio, y escala a
opus una vez si falla).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo import ajustes as mod_ajustes  # noqa: E402
from nucleo.ejecutor import Ejecutor  # noqa: E402
from nucleo.engram import Engram  # noqa: E402
from nucleo.grafo import Grafo  # noqa: E402
from nucleo.registro import Registro  # noqa: E402
from nucleo.sesiones import Activas, Catalogo, Propias  # noqa: E402


def main(argv: list[str]) -> int:
    enrutado = "--enrutado" in argv
    argv = [x for x in argv if x != "--enrutado"]
    carpeta = Path(argv[0])
    pid = argv[1] if len(argv) > 1 else "dashboard"
    texto = argv[2] if len(argv) > 2 else ("¿Cómo se calcula el cumplimiento del presupuesto (Sell In real contra "
                                           "Budget) y en qué archivos y funciones está? Responde en máximo 6 líneas.")
    a = mod_ajustes.cargar(RAIZ)
    with tempfile.TemporaryDirectory() as tmp:
        reg = Path(tmp) / "proyectos.json"
        entrada = {"id": pid, "nombre": pid, "carpeta": str(carpeta)}
        if enrutado:
            entrada["enrutamiento"] = {"activo": True}
        reg.write_text(json.dumps({"proyectos": [entrada]}), encoding="utf-8")
        a.registro = reg
        registro = Registro(reg)
        catalogo = Catalogo(a.claude_home, Propias(a.sesiones_propias), Activas(), a.umbral_actividad_s,
                            a.sesiones_protegidas)
        e = Ejecutor(a, registro, catalogo, Engram(a.engram_db, a.engram_alias), grafo=Grafo(a))
        r = e.recibir({"proyecto": pid, "texto": texto, "modo": "lectura", "contexto": "grafo"})
        f = e.ejecutar(e.almacen.obtener(r["id"]))
    resumen = {k: f.get(k) for k in ("id", "estado", "costo_usd", "num_turnos", "duracion_ms", "uso", "denegaciones",
                                     "errores", "modelo_decision", "modelo_usado", "modelo_real", "escalado",
                                     "motivo_escalamiento")}
    resumen["intentos"] = [{k: i.get(k) for k in ("modelo", "esfuerzo", "estado", "costo_usd", "num_turnos",
                                                  "modelo_real", "fallo")} for i in f.get("intentos") or []]
    resumen["contexto_usado"] = f.get("contexto_usado")
    resumen["herramientas"] = [(h.get("herramienta"), h.get("permitida")) for h in f.get("herramientas") or []]
    resumen["respuesta"] = f.get("respuesta")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0 if f.get("estado") == "completada" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
