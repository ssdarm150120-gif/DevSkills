---
name: implementar-historia
description: >
  Flujo de desarrollo de una historia (HU) o habilitador (EN) con TDD, arquitectura hexagonal, trazabilidad
  al SRS y la lista de lecciones aprendidas. Trigger: cuando un agente desarrollador implementa un elemento
  del backlog o una ronda de correcciones.
license: Apache-2.0
metadata:
  author: devskills
  version: "1.0"
---

## When to Use

- Un desarrollador (`devskills:dev-a` o `devskills:dev-b`) recibe un ID del backlog (`HU-xx` o `EN-xx`) para implementarlo.
- Una ronda de correcciones después de QA, del Angel Fixer o de la verificación final (con su lista exacta).

## Critical Patterns

### Paso 0. Entender antes de tocar código
1. Cargar `devskills:proyecto-contexto` y leer `documentacion/CONTEXTO.md`.
2. Leer en `documentacion/SRS.md`: la historia (Anexo B) con sus escenarios Gherkin, los RF y RNF de su línea "Trazabilidad", y su caso de uso (Anexo A). Para un EN, leer el ADR o la sección de `documentacion/DISENO.md` que cita el plan.
3. Verificar la **Definición de Listo**. Si falta algo, hay una contradicción o el DISEÑO no define lo que hace falta (por ejemplo, los métodos de un puerto o dónde vive), **detenerse antes de escribir código y reportarlo**: no inventar requisitos ni diseño.
4. **Estimar contra el plan:** si el elemento excede claramente sus puntos (por ejemplo, 13 o más para algo estimado en 5), **detenerse y reportarlo** con la estimación y una propuesta para partirlo. Lección del proyecto modelo: dos habilitadores que no se detuvieron llevaron 3 y 6 rondas; los que se detuvieron cupieron en lo estimado.
5. Marcar el elemento como `En proceso` en `documentacion/avance/estado_backlog.json`.

### Paso 1. Ubicar el trabajo en la arquitectura
| Qué toca la historia | Dónde va | Subagente |
|----------------------|----------|-----------|
| Reglas, entidades, estados, cálculos | `<modulo>/dominio/` | `devskills:dev-dominio` |
| Caso de uso (orquesta dominio + puertos + permisos) | `<modulo>/aplicacion/<cu>.py` | `devskills:dev-dominio` |
| Sistemas externos, outbox, Celery, ORM, migraciones | `<modulo>/adaptadores/salida/`, `nucleo/puertos/` | `devskills:dev-integraciones` |
| Pantallas Django + HTMX, accesibilidad | `<modulo>/adaptadores/entrada/` y plantillas | `devskills:dev-interfaz` |
| Servicio interno separado (algoritmos, modelos) | su propia carpeta de servicio | `devskills:dev-servicios` |

Delegar en el subagente que corresponda; si la historia cruza capas, empezar por el dominio. Un módulo nuevo se declara en `configuracion/modulos.py` (con sus dependencias del DISEÑO) y se regeneran los contratos de import-linter con `python -m herramientas.contratos_importlinter --escribir`.

### Paso 2. TDD (rojo → verde → refactor)
- Escribir primero las **pruebas unitarias del dominio** derivadas de los escenarios Gherkin.
- Implementar lo mínimo para ponerlas en verde; refactorizar sin cambiar el comportamiento.
- Los adaptadores se prueban contra **puertos falsos** y con su prueba de contrato.
- Las pruebas de aceptación (pytest-bdd sobre el Gherkin del SRS) las escribe y ejecuta **QA**, no el desarrollador.
- Las pruebas deben **morder**: comprueba en una copia del scratchpad que una mutación del código las hace fallar.

### Paso 3. Reglas que siempre se revisan antes de entregar
- [ ] `dominio/` no importa Django, ORM ni librerías de red; nada fuera de la lista blanca.
- [ ] Otro módulo se usa solo por `api_publica.py` o por eventos; cada módulo publica solo sus eventos.
- [ ] Transiciones de estado por la tabla del dominio; evento emitido y registrado en la bitácora.
- [ ] Envíos externos por outbox, en la misma transacción, con clave de idempotencia.
- [ ] Permisos verificados en el caso de uso con la matriz central y el `Actor` (incluidos filtros de propiedad: nadie ve lo de otro).
- [ ] Sistemas de solo lectura: ningún puerto de escritura implementado; SQL siempre parametrizado.
- [ ] Sin datos personales en logs ni en eventos; secretos por variables de entorno; nada de la empresa en constantes.
- [ ] Tiempo con `Reloj` inyectado (UTC); dinero como monto + moneda.
- [ ] `lint-imports`, `ruff check .`, `ruff format --check .`, `mypy .`, `pytest`, `bandit`, `pip-audit` y `makemigrations --check` en verde.

### Paso 3b. Lecciones aprendidas (checklist de incidentes reales)
- [ ] **Transacciones propias:** un "un solo uso", un contador o un bloqueo que depende de que quien llama abra la transacción no es un control; el adaptador abre su transacción y su `select_for_update`.
- [ ] **`FOR UPDATE OF` con esquemas:** falla en PostgreSQL con tablas calificadas por esquema; bloquear en pasos (leer ids, bloquear sin joins, releer).
- [ ] **Orden de bloqueos:** siempre el mismo orden para no crear interbloqueos (por ejemplo, en cambios cruzados).
- [ ] **Carreras:** pruebas de concurrencia para doble envío, dos peticiones simultáneas y "siempre queda al menos un X" (por ejemplo, un Administrador activo).
- [ ] **Celery:** `SoftTimeLimitExceeded` hereda de `Exception`; un `except Exception` se la traga y el límite suave deja de interrumpir. Captúrala antes y relánzala.
- [ ] **Ingreso sin oráculo de tiempo:** el camino de un usuario inexistente hace un trabajo equivalente al de uno existente (hash y base de datos); el mensaje es el mismo para todos los fallos.
- [ ] **Sellos de sesión:** todo camino que cambie la contraseña, los roles o el segundo factor rota el sello y cierra las demás sesiones.
- [ ] **Normalización Unicode:** valida identificadores (correos, claves) después de normalizar; caracteres invisibles, de ancho completo o "parecidos" (como el signo Kelvin) no deben pasar; un filtro de datos sensibles normaliza las claves (acentos, ancho completo, invisibles, camelCase).
- [ ] **Secretos:** nunca en `repr` ni en logs; derivación de llaves con sal propia; llaves de producción con entropía mínima y distintas entre sí.
- [ ] **Reloj:** nunca el reloj del sistema dentro del dominio o de un adaptador; las pruebas no dependen de la fecha real.
- [ ] **Errores:** errores de dominio tipados, no `ValueError` genérico para una condición de negocio; sin `except` desnudos ni excepciones tragadas.
- [ ] **Objetos inmutables:** una dataclass con `slots` no revalida en `__setstate__`; si se serializa (pickle/copy), valida también ahí.
- [ ] **Archivos generados:** escribir con `newline="\n"` (en Windows se cuelan CRLF); `.gitattributes` con LF.
- [ ] **Pruebas en paralelo:** recursos con nombre único por sesión de pytest (bases, carpetas temporales) y sin procesos huérfanos.
- [ ] **Sin duplicados:** una sola fuente para cada permiso o regla (la matriz central), sin bloques duplicados en vistas.

### Paso 4. Entregar
1. **No hacer commit:** el orquestador hace los puntos de control (`devskills:ciclo-historia`).
2. Marcar `En validación` en `documentacion/avance/estado_backlog.json`.
3. Devolver al orquestador: archivos tocados, pruebas agregadas (y cuántas en total pasan), decisiones tomadas (para que el orquestador las registre como suyas o las lleve al Product Owner), texto para `.env.ejemplo` si hace falta, y dudas abiertas.
4. Guardar en engram (`mem_save`, project de `CONTEXTO.md`) cualquier decisión o hallazgo no obvio.

## Code Examples

```python
# <modulo>/aplicacion/confirmar_solicitud.py  (CU-nn, HU-nn)
from dataclasses import dataclass

from nucleo.actor import Actor
from nucleo.permisos import exigir
from <modulo>.aplicacion.puertos import RepositorioSolicitudes
from nucleo.puertos.reloj import Reloj


@dataclass(frozen=True)
class ConfirmarSolicitud:
    solicitudes: RepositorioSolicitudes
    reloj: Reloj

    def __call__(self, actor: Actor, solicitud_id: int) -> None:
        exigir(actor, "confirmar_solicitud")          # permiso en el caso de uso
        solicitud = self.solicitudes.obtener_para_actualizar(solicitud_id)
        solicitud.confirmar(momento=self.reloj.ahora())  # transición del dominio + evento
        self.solicitudes.guardar(solicitud)          # misma transacción que el outbox
```

> Los nombres exactos de `nucleo` (permisos, reloj, puertos) son los del esqueleto del proyecto; revísalos antes de copiar el ejemplo.

## Commands

```bash
# desde codigo/
python -m pytest <modulo>/pruebas -q
lint-imports && ruff check . && ruff format --check . && mypy .
python manage.py makemigrations --check --dry-run
```
