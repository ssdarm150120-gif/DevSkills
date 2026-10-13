"""Mapa de modulos del monolito (DISENO D.1.2). Fuente unica para settings, migraciones y CI.

El esqueleto trae `identidad` (usuarios, roles, ingreso y segundo factor) y `auditoria` (modulo
hexagonal vacio, listo para la bitacora). Para agregar un modulo: crea su carpeta con la estructura
hexagonal (copia la de `auditoria`), agregalo a `MODULOS_NEGOCIO`, declara sus dependencias en
`DEPENDENCIAS` segun el DISENO (D.1.3) y regenera los contratos:

    python -m herramientas.contratos_importlinter --escribir
"""

# Modulos de negocio, en el orden de D.1.2.
MODULOS_NEGOCIO: tuple[str, ...] = (
    "identidad",
    "auditoria",
)

# Modulos de integracion (no son de negocio, D.1.2): extraen datos de un sistema externo hacia una
# cache propia y ofrecen lecturas. El esqueleto no trae ninguno.
MODULOS_INTEGRACION: tuple[str, ...] = ()

# `nucleo`: nucleo compartido minimo (actor, permisos, puertos, bus de eventos, outbox).
MODULO_NUCLEO = "nucleo"

# `identidad` es hoja del grafo: NADIE la importa. Los permisos llegan a los casos de uso como un
# `Actor` inmutable definido en `nucleo` (D.1.3), resuelto por el adaptador de entrada.
MODULO_IDENTIDAD = "identidad"

# Modulos con estructura hexagonal completa (dominio/aplicacion/adaptadores/api_publica).
MODULOS_HEXAGONALES: tuple[str, ...] = (*MODULOS_NEGOCIO, *MODULOS_INTEGRACION)

# Aplicaciones Django propias.
APPS_PROPIAS: tuple[str, ...] = (MODULO_NUCLEO, *MODULOS_HEXAGONALES)

# Dependencias sincronas permitidas entre modulos (DISENO D.1.3): "A usa la `api_publica` de B".
# Es la transcripcion literal del diagrama; todo lo que no esta aqui esta PROHIBIDO y rompe
# `lint-imports`. No hay ciclos (se verifica al generar `.importlinter`). La comunicacion por
# eventos no es un import: el bus de eventos vive en `nucleo`.
# Los modulos sin entrada (identidad, ...) no importan a ningun otro modulo.
# Ejemplo: "modulo_a": ("modulo_b", "modulo_c"),
DEPENDENCIAS: dict[str, tuple[str, ...]] = {}

# Esquema de PostgreSQL por modulo (D.2.1): el mismo nombre del modulo. Si un modulo necesita otro
# nombre de esquema, se agrega aqui la excepcion.
ESQUEMAS: dict[str, str] = {modulo: modulo for modulo in APPS_PROPIAS}

# Donde vive la carpeta de migraciones de cada app (arquitectura hexagonal: adaptador de salida).
MIGRATION_MODULES: dict[str, str] = {
    **{modulo: f"{modulo}.adaptadores.salida.migraciones" for modulo in MODULOS_HEXAGONALES},
    MODULO_NUCLEO: "nucleo.adaptadores.migraciones",
}
