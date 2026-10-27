"""Cliente de prueba del orquestador (lee puerto y token de .token; nunca los imprime).

Ejemplos:
  python cliente.py inventario [proyecto]
  python cliente.py contexto <proyecto> [consulta...]
  python cliente.py lectura <proyecto> "<texto>" [--nueva] [--esperar] [--contexto=auto|sesion|grafo]
                    [--modelo=haiku|sonnet|opus]
  python cliente.py cambios <proyecto> "<texto>" [--modelo=...]  (queda pendiente de confirmación)
  python cliente.py enrutamiento                                (costos por modelo y tasa de escalamiento)
  python cliente.py confirmar <id> [--esperar]
  python cliente.py cancelar <id>
  python cliente.py ver <id>
  python cliente.py lista
  python cliente.py grafo <proyecto> [consulta...]              (estado, resumen y consulta al grafo, sin LLM)
  python cliente.py resolver "<texto libre>"                    (proyecto más probable)
  python cliente.py propuestas [pendiente|aceptada|descartada]  (propuestas de agente/skill/comando)
  python cliente.py propuestas analizar                         (recalcula con los transcripts)
  python cliente.py propuestas version
  python cliente.py crear-agente <id> general|proyecto [<proyecto>] [--tipo=agente|skill|comando]
  python cliente.py descartar-agente <id>
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from nucleo import ajustes as mod_ajustes  # noqa: E402
from orquestador import llamar  # noqa: E402

TERMINALES = {"completada", "error", "tiempo_agotado", "aviso_sesion_abierta", "cancelada", "expirada", "interrumpida"}


def mostrar(d) -> None:
    print(json.dumps(d, ensure_ascii=False, indent=2))


def esperar(a, iid: str, limite_s: int = 900) -> dict:
    fin = time.time() + limite_s
    while time.time() < fin:
        r = llamar(a, "GET", f"/api/instruccion/{iid}")
        if r["estado"] in TERMINALES:
            return r
        time.sleep(3)
    return r


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    a = mod_ajustes.cargar()
    bandera_esperar = "--esperar" in argv
    nueva = "--nueva" in argv
    opciones = dict(x[2:].split("=", 1) for x in argv if x.startswith("--") and "=" in x)
    args = [x for x in argv if x not in ("--esperar", "--nueva") and not (x.startswith("--") and "=" in x)]
    cmd = args[0]
    try:
        if cmd == "inventario":
            mostrar(llamar(a, "GET", "/api/inventario" + (f"/{args[1]}" if len(args) > 1 else ""), timeout=120))
        elif cmd == "contexto" and len(args) >= 2:
            q = urllib.parse.quote(" ".join(args[2:]))
            mostrar(llamar(a, "GET", f"/api/contexto/{args[1]}?q={q}"))
        elif cmd in ("lectura", "cambios") and len(args) == 3:
            cuerpo = {"proyecto": args[1], "texto": args[2], "modo": cmd}
            if nueva:
                cuerpo["nueva_sesion"] = True
            if "contexto" in opciones:
                cuerpo["contexto"] = opciones["contexto"]
            if "modelo" in opciones:
                cuerpo["modelo"] = opciones["modelo"]
            r = llamar(a, "POST", "/api/instruccion", cuerpo)
            mostrar(esperar(a, r["id"]) if (bandera_esperar and r["estado"] == "en_cola") else r)
        elif cmd == "confirmar" and len(args) == 2:
            r = llamar(a, "POST", f"/api/instruccion/{args[1]}/confirmar", {"confirmacion": args[1]})
            mostrar(esperar(a, r["id"]) if bandera_esperar else r)
        elif cmd == "enrutamiento":
            mostrar(llamar(a, "GET", "/api/enrutamiento"))
        elif cmd == "cancelar" and len(args) == 2:
            mostrar(llamar(a, "POST", f"/api/instruccion/{args[1]}/cancelar", {}))
        elif cmd == "ver" and len(args) == 2:
            mostrar(llamar(a, "GET", f"/api/instruccion/{args[1]}"))
        elif cmd == "lista":
            mostrar(llamar(a, "GET", "/api/instrucciones"))
        elif cmd == "grafo" and len(args) >= 2:
            q = urllib.parse.quote(" ".join(args[2:]))
            mostrar(llamar(a, "GET", f"/api/grafo/{args[1]}" + (f"?q={q}" if q else ""), timeout=90))
        elif cmd == "resolver" and len(args) >= 2:
            mostrar(llamar(a, "GET", "/api/resolver?texto=" + urllib.parse.quote(" ".join(args[1:]))))
        elif cmd == "propuestas":
            sub = args[1] if len(args) > 1 else None
            if sub == "analizar":
                mostrar(llamar(a, "POST", "/api/propuestas-agentes/analizar", {}, timeout=600))
            elif sub == "version":
                mostrar(llamar(a, "GET", "/api/propuestas-agentes/version"))
            else:
                mostrar(llamar(a, "GET", "/api/propuestas-agentes" + (f"?estado={sub}" if sub else "")))
        elif cmd == "crear-agente" and len(args) in (3, 4):
            cuerpo = {"confirmacion": args[1], "destino": args[2]}
            if len(args) == 4:
                cuerpo["proyecto"] = args[3]
            if "tipo" in opciones:
                cuerpo["tipo"] = opciones["tipo"]
            mostrar(llamar(a, "POST", f"/api/propuestas-agentes/{args[1]}/crear", cuerpo))
        elif cmd == "descartar-agente" and len(args) == 2:
            mostrar(llamar(a, "POST", f"/api/propuestas-agentes/{args[1]}/descartar", {}))
        else:
            print(__doc__)
            return 2
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}")
        return 1
    except ConnectionError as e:
        print(str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
