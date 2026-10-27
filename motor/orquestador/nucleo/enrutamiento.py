"""Enrutamiento de modelo por instrucción (Model Routing Playbook: por omisión un escalón abajo del más caro,
escalar UNA vez si falla y registrar los fallos).

Precedencia del modelo:
1. `modelo` en la petición (lista blanca haiku/sonnet/opus): manda; no se escala.
2. Enrutamiento activo en el registro (`proyectos.json` → `enrutamiento.activo: true`, lo escribe el panel; aquí solo
   se lee): lectura → `sonnet` con esfuerzo `medium`; cambios → `opus`. Una lectura enrutada que falla se reintenta
   una vez con `opus` (sin esfuerzo forzado).
3. Si no: el modelo de config.json (`modelo`, hoy null = el de la cuenta), como en la fase 1.

Los alias `haiku`, `sonnet` y `opus` son los que acepta `--model` del CLI (el SDK pasa `ClaudeAgentOptions.model`
tal cual); `effort` es `Literal["low","medium","high","xhigh","max"]` en claude-agent-sdk 0.2.174.

Fallo (determinista, en este orden): estado distinto de `completada` (error, tiempo agotado, presupuesto o turnos
agotados); respuesta vacía o de menos de `min_caracteres` (20); o respuesta corta (< 600 caracteres) que en sus
primeros 300 caracteres dice que no pudo ("no pude", "no fue posible", "no tengo acceso", "I was unable"...).
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import defaultdict
from pathlib import Path

from . import texto as tx

MODELOS = ("haiku", "sonnet", "opus")
DEFAULT = {"lectura": "sonnet", "cambios": "opus", "esfuerzo_lectura": "medium", "escalar_a": "opus",
           "min_caracteres": 20}

_NO_PUDO = re.compile(
    r"\b(no (pude|puedo|logre|consegui|fue posible|es posible|tengo acceso|tengo permiso|cuento con)|"
    r"me fue imposible|imposible (leer|acceder|completar)|"
    r"i (was unable|am unable|could ?not|couldn't|can ?not|can't|do not have access|don't have access)|unable to)\b")


def decidir(r: dict, proyecto, ajustes) -> dict:
    """{modelo, esfuerzo, origen: parametro|enrutamiento|config, enrutamiento_activo, escalable}."""
    cfg = {**DEFAULT, **(getattr(ajustes, "enrutamiento", None) or {})}
    activo = bool(getattr(proyecto, "enrutamiento_activo", False))
    if r.get("modelo"):
        return {"modelo": r["modelo"], "esfuerzo": None, "origen": "parametro", "enrutamiento_activo": activo,
                "escalable": False}
    if activo:
        lectura = r["modo"] == "lectura"
        return {"modelo": cfg[r["modo"]], "esfuerzo": cfg["esfuerzo_lectura"] if lectura else None,
                "origen": "enrutamiento", "enrutamiento_activo": True,
                "escalable": lectura and cfg[r["modo"]] != cfg["escalar_a"]}
    return {"modelo": ajustes.modelo, "esfuerzo": None, "origen": "config", "enrutamiento_activo": False,
            "escalable": False}


def motivo_fallo(res: dict, min_caracteres: int = DEFAULT["min_caracteres"]) -> str | None:
    if res.get("estado") != "completada":
        return f"terminó en estado '{res.get('estado')}'" + (f" ({res.get('subtipo')})" if res.get("subtipo") else "")
    texto = (res.get("respuesta") or "").strip()
    if not texto:
        return "respuesta vacía"
    if len(texto) < min_caracteres:
        return f"respuesta de {len(texto)} caracteres (< {min_caracteres})"
    if len(texto) < 600 and _NO_PUDO.search(tx.sin_acentos(texto[:300].lower())):
        return "el modelo dice que no pudo completar la instrucción"
    return None


def modelo_principal(uso: dict | None) -> str | None:
    """Id real del modelo que más costó (el SDK reporta también el modelo auxiliar, p. ej. haiku para títulos)."""
    por = (uso or {}).get("por_modelo") or {}
    if not por:
        return None
    return max(por.items(), key=lambda kv: (kv[1].get("costUSD") or 0))[0]


class BitacoraFallos:
    """`enrutamiento-fallos.jsonl`: una línea por escalamiento (sin el texto de la instrucción)."""

    def __init__(self, ruta: Path):
        self.ruta = ruta
        self._lock = threading.Lock()

    def agregar(self, datos: dict) -> None:
        with self._lock, open(self.ruta, "a", encoding="utf-8") as h:
            h.write(json.dumps({"fecha": time.strftime("%Y-%m-%dT%H:%M:%S"), **datos}, ensure_ascii=False) + "\n")

    def ultimos(self, n: int = 10) -> list[dict]:
        try:
            lineas = self.ruta.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        salida = []
        for l in lineas[-n:]:
            try:
                salida.append(json.loads(l))
            except ValueError:
                continue
        return salida


def resumen(registros: list[dict], proyectos: dict, bitacora: BitacoraFallos) -> dict:
    """Costos por modelo (de `uso.por_modelo` de cada intento) y tasa de escalamiento, a partir del historial."""
    por_modelo: dict[str, dict] = defaultdict(lambda: {"intentos": 0, "costo_usd": 0.0})
    enrutadas = escaladas = escaladas_ok = 0
    por_origen: dict[str, int] = defaultdict(int)
    for r in registros:
        if r.get("costo_usd") is None and not r.get("intentos"):
            continue
        por_origen[(r.get("modelo_decision") or {}).get("origen") or "sin_dato"] += 1
        intentos = r.get("intentos") or [{"uso": r.get("uso"), "costo_usd": r.get("costo_usd")}]
        for it in intentos:
            por = ((it.get("uso") or {}).get("por_modelo")) or {}
            if por:
                for modelo, d in por.items():
                    por_modelo[modelo]["costo_usd"] += float(d.get("costUSD") or 0)
                principal = modelo_principal(it.get("uso"))
                if principal:
                    por_modelo[principal]["intentos"] += 1
            elif it.get("costo_usd") is not None:
                por_modelo["desconocido"]["costo_usd"] += float(it["costo_usd"])
                por_modelo["desconocido"]["intentos"] += 1
        d = r.get("modelo_decision") or {}
        if d.get("origen") == "enrutamiento" and r.get("modo") == "lectura":
            enrutadas += 1
            if r.get("escalado"):
                escaladas += 1
                escaladas_ok += r.get("estado") == "completada"
    modelos = {k: {"intentos": v["intentos"], "costo_usd": round(v["costo_usd"], 4),
                   "costo_promedio_usd": round(v["costo_usd"] / v["intentos"], 4) if v["intentos"] else None}
               for k, v in sorted(por_modelo.items())}
    return {
        "proyectos_activos": sorted(pid for pid, p in proyectos.items() if getattr(p, "enrutamiento_activo", False)),
        "instrucciones": sum(por_origen.values()), "por_origen": dict(por_origen),
        "por_modelo": modelos, "costo_total_usd": round(sum(v["costo_usd"] for v in por_modelo.values()), 4),
        "lecturas_enrutadas": enrutadas, "escaladas": escaladas, "escaladas_resueltas": escaladas_ok,
        "tasa_escalamiento": round(escaladas / enrutadas, 3) if enrutadas else None,
        "ultimos_fallos": bitacora.ultimos(10),
    }
