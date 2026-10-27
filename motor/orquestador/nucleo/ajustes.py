"""Configuración del orquestador: config.json más las rutas del entorno.

Todas las rutas se pueden inyectar (las pruebas usan carpetas temporales); en producción salen del perfil del
usuario. El orquestador solo LEE el registro, los transcripts, la configuración de Claude y engram; solo escribe
dentro de su propia carpeta de datos (historial, .token, log, propuestas y sesiones_propias.json), que está FUERA del
repositorio: <datos>/orquestador, con <datos> = DEVSKILLS_DATOS o ~/.devskills (ver motor/comun/rutas.py).
La configuración sale de <datos>/orquestador/config.json; si no existe se usa config.defecto.json (genérica).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

AQUI = Path(__file__).resolve().parent.parent  # código del orquestador (motor/orquestador)
sys.path.insert(0, str(AQUI.parent))
from comun import rutas  # noqa: E402

PRESUPUESTO_DEFAULT = {"lectura": 2.0, "cambios": 4.0}
GRAFO_DEFAULT = {
    "ejecutable": None,            # None: busca 'graphify' en el PATH y en ~/.local/bin
    "presupuesto_chars": 6000,     # recorte del resultado de 'graphify query' dentro del bloque de contexto
    "resumen_chars": 1500,         # recorte del resumen de GRAPH_REPORT.md
    "contexto_max_chars": 10000,   # tope de todo el bloque de contexto sembrado
    "api_max_chars": 8000,         # tope de la respuesta de GET /api/grafo/<proyecto>
    "tiempo_limite_s": 30,
    "cache_estado_s": 60,
}
ENRUTAMIENTO_DEFAULT = {"lectura": "sonnet", "cambios": "opus", "esfuerzo_lectura": "medium", "escalar_a": "opus",
                        "min_caracteres": 20}
CONTEXTO_AUTO_DEFAULT = {"umbral_mb": 2.0, "umbral_tokens": 150000}
PROPUESTAS_DEFAULT = {
    "umbral_similitud": 0.4,       # coseno TF-IDF mínimo para que una instrucción entre a un grupo
    "min_veces": 3,                # propuesta si el grupo aparece >= min_veces ...
    "min_conversaciones": 2,       # ... o en >= min_conversaciones conversaciones
    "min_palabras": 2,             # instrucciones con menos palabras de contenido se ignoran ("continúa", "sí")
    "max_caracteres": 1200,        # más largo que esto (sin el contenido pegado) se considera pegado y se ignora
    "max_ejemplos": 3,
    "cada_h": 12,                  # recálculo automático
    "retraso_inicial_min": 10,
}


@dataclass
class Ajustes:
    raiz: Path = field(default_factory=rutas.orquestador_dir)
    puerto: int = 18952
    rango: tuple[int, int] = (18950, 18999)
    registro: Path = field(default_factory=rutas.registro)
    claude_home: Path = field(default_factory=rutas.claude_dir)
    claude_json: Path = field(default_factory=rutas.claude_json)
    engram_db: Path = Path.home() / ".engram" / "engram.db"
    engram_alias: dict[str, list[str]] = field(default_factory=dict)
    trabajadores: int = 1
    tiempo_limite_s: int = 600
    max_turnos: int = 25
    presupuesto_usd: dict[str, float] = field(default_factory=lambda: dict(PRESUPUESTO_DEFAULT))
    modelo: str | None = None
    umbral_actividad_s: int = 120
    politica_sesion_abierta: str = "nueva"
    lectura_permite_webfetch: bool = False
    pendiente_expira_h: int = 24
    max_texto: int = 4000
    max_consulta: int = 200
    sesiones_protegidas: frozenset[str] = frozenset()
    # fase 2
    alias_proyectos: dict[str, list[str]] = field(default_factory=dict)
    grafo: dict = field(default_factory=lambda: dict(GRAFO_DEFAULT))
    contexto_auto: dict = field(default_factory=lambda: dict(CONTEXTO_AUTO_DEFAULT))
    propuestas: dict = field(default_factory=lambda: dict(PROPUESTAS_DEFAULT))
    enrutamiento: dict = field(default_factory=lambda: dict(ENRUTAMIENTO_DEFAULT))

    @property
    def historial(self) -> Path:
        return self.raiz / "historial"

    @property
    def archivo_token(self) -> Path:
        return self.raiz / ".token"

    @property
    def archivo_log(self) -> Path:
        return self.raiz / "orquestador.log"

    @property
    def sesiones_propias(self) -> Path:
        return self.raiz / "sesiones_propias.json"

    @property
    def fallos_enrutamiento(self) -> Path:
        return self.raiz / "enrutamiento-fallos.jsonl"

    @property
    def carpeta_propuestas(self) -> Path:
        return self.raiz / "propuestas"


def _ruta(valor: str, base: Path) -> Path:
    p = Path(os.path.expandvars(os.path.expanduser(valor)))
    return p if p.is_absolute() else (base / p).resolve()


def cargar(raiz: Path | None = None) -> Ajustes:
    raiz = Path(raiz) if raiz else rutas.orquestador_dir()
    datos = {}
    archivo = raiz / "config.json"
    if not archivo.exists() and raiz == rutas.orquestador_dir():
        archivo = rutas.orquestador_config_defecto()
    if archivo.exists():
        datos = json.loads(archivo.read_text(encoding="utf-8"))
    a = Ajustes(raiz=raiz)
    if "puerto" in datos:
        a.puerto = int(datos["puerto"])
    if "rango" in datos:
        a.rango = (int(datos["rango"][0]), int(datos["rango"][1]))
    if datos.get("registro"):
        a.registro = _ruta(datos["registro"], raiz)
    eng = datos.get("engram") or {}
    if eng.get("db"):
        a.engram_db = _ruta(eng["db"], raiz)
    a.engram_alias = {str(k): [str(x) for x in v] for k, v in (eng.get("alias") or {}).items()}
    for clave in ("trabajadores", "tiempo_limite_s", "max_turnos", "umbral_actividad_s",
                  "pendiente_expira_h", "max_texto", "max_consulta"):
        if clave in datos:
            setattr(a, clave, int(datos[clave]))
    if "presupuesto_usd" in datos:
        a.presupuesto_usd = {**PRESUPUESTO_DEFAULT, **{k: float(v) for k, v in datos["presupuesto_usd"].items()}}
    a.modelo = datos.get("modelo") or None
    pol = datos.get("politica_sesion_abierta", "nueva")
    if pol not in ("nueva", "aviso"):
        raise ValueError("politica_sesion_abierta debe ser 'nueva' o 'aviso'")
    a.politica_sesion_abierta = pol
    a.lectura_permite_webfetch = bool(datos.get("lectura_permite_webfetch", False))
    a.sesiones_protegidas = frozenset(str(x).lower() for x in datos.get("sesiones_protegidas", []))
    a.trabajadores = max(1, a.trabajadores)
    a.alias_proyectos = {str(k): [str(x) for x in v] for k, v in (datos.get("alias_proyectos") or {}).items()}
    a.grafo = {**GRAFO_DEFAULT, **(datos.get("grafo") or {})}
    a.contexto_auto = {**CONTEXTO_AUTO_DEFAULT, **(datos.get("contexto_auto") or {})}
    a.propuestas = {**PROPUESTAS_DEFAULT, **(datos.get("propuestas") or {})}
    a.enrutamiento = {**ENRUTAMIENTO_DEFAULT, **(datos.get("enrutamiento") or {})}
    for clave in ("lectura", "cambios", "escalar_a"):
        if a.enrutamiento[clave] not in ("haiku", "sonnet", "opus"):
            raise ValueError(f"enrutamiento.{clave} debe ser haiku, sonnet u opus")
    return a
