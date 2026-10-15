# Stack

DevSkills es una metodología y un stack para construir cualquier sistema, nacida de un proyecto real. El stack es **fijo**: cada proyecto nuevo arranca con el mismo esqueleto en `codigo/`, que ya trae lo genérico hecho y con sus pruebas. Lo que cambia por proyecto son los módulos de negocio, los roles y las integraciones, que salen de su SRS y de su DISEÑO.

## Tecnologías

Python 3.12 · Django 5 + Django REST Framework · PostgreSQL 16 · Redis · Celery (`worker`, `worker-outbox`, `beat`) · HTMX · nginx con TLS · Docker Compose · ruff, mypy, pytest, pytest-bdd, import-linter, bandit, pip-audit.

## Qué trae el esqueleto

| Carpeta | Contenido |
|---------|-----------|
| `configuracion/` | Settings por entorno (dev, pruebas, prod, migraciones) con validación del entorno al arrancar, `modulos.py` (mapa de módulos, dependencias y esquemas), seguridad (CSP, encabezados), salud, Celery, composición de adaptadores |
| `nucleo/` | `Actor`, matriz de permisos central, puertos compartidos, reloj, y el outbox de eventos con despachador, reintentos, purga y filtro de datos sensibles |
| `identidad/` | Usuarios, roles, ingreso con Argon2, bloqueo por cuenta, sesión con sello y tope, segundo factor TOTP cifrado, gestión de usuarios y aviso por reuso de código |
| `auditoria/` | Molde: módulo hexagonal vacío (el esqueleto **no trae bitácora**) para copiar o retirar según el SRS |
| `herramientas/` | Generador de contratos de import-linter, roles de PostgreSQL con mínimo privilegio, bases embebidas para desarrollo y pruebas, sonda de salud |
| `despliegue/` | Dockerfile, Compose de desarrollo y de pruebas, nginx con TLS, pasos `certificado` y `migrar`, `.env.ejemplo` |

Trae el rol **Administrador** (gestiona usuarios y exige segundo factor) y dos roles **de ejemplo** que cada proyecto sustituye por los de su SRS: `auditor` (rol sensible, con segundo factor) y `usuario` (sin segundo factor). Hacen falta para ejercitar en las pruebas los dos caminos del ingreso y la suma de permisos de varios roles. También trae `auditoria`, un módulo hexagonal vacío que sirve de molde para los módulos nuevos. Los nombres propios del sistema van por variables de entorno con el prefijo `APP_`.

## Arquitectura

- **Monolito modular:** un paquete por módulo de negocio, cada uno dueño de su esquema de PostgreSQL.
- **Hexagonal por módulo:** `dominio/` (Python puro) · `aplicacion/` (un caso de uso por archivo) · `adaptadores/entrada|salida/` · `api_publica.py` · `pruebas/`.
- **Límites verificados por máquina:** los contratos de import-linter se generan desde `configuracion/modulos.py`; pruebas AST vigilan que el dominio sea puro.
- **Todo lo externo detrás de un puerto**, con adaptador falso y prueba de contrato.
- **Outbox:** lo que sale hacia afuera se guarda en la misma transacción que el cambio.

## Cómo extenderlo para tu dominio

| Qué | Dónde |
|-----|-------|
| Un módulo nuevo | Copia la estructura de `auditoria/`, agrégalo a `MODULOS_NEGOCIO` y a `DEPENDENCIAS` en `configuracion/modulos.py`, y regenera: `python -m herramientas.contratos_importlinter --escribir` |
| Roles | Catálogo de roles de `identidad` con una migración de datos nueva |
| Permisos | `nucleo/permisos.py` (capacidades por rol, denegación por defecto) |
| Un sistema externo | Puerto en `nucleo/puertos/` o en el módulo dueño, con su falso y su prueba de contrato |
| Eventos | Catálogo de eventos de `nucleo` |

El `README.md` de `codigo/` de cada proyecto trae el detalle: variables de entorno, operación con Compose, roles y permisos, segundo factor, puertos y la cola del outbox.

## Lecciones del stack (CI y despliegue)

- **Docker Compose 2.38 (el del runner de GitHub) pierde `!reset` si llega por la fusión `<<:` de un ancla YAML.** En `despliegue/docker-compose.pruebas.yml`, `build: !reset null` va **directamente en cada servicio**, nunca dentro del ancla; en local con un Compose más nuevo el error no se ve y el CI sí lo muestra (intenta construir en lugar de usar la imagen). Una prueba estática del esqueleto lo vigila.
- **Fija la imagen del runner:** `ubuntu-24.04` en lugar de `ubuntu-latest`; cambiarla es un cambio a mano.
- **semgrep local = semgrep del CI:** la misma versión (la de `semgrep==` en `ci.yml`), nativo en macOS y Linux, por WSL o Docker en Windows (opcionales), código 0 y "Findings: 0"; en el CI de GitHub siempre es obligatorio. Un hallazgo se corrige o se suprime en su línea con motivo (`# nosemgrep: <regla>`), nunca se excluye una carpeta; con gitleaks, igual: `gitleaks:allow` en la misma línea. La regla `django-no-csrf-token` es genérica y solo reconoce `{% csrf_token %}` si el `</form>` está a 10 líneas o menos: los formularios largos se parten en parciales.
- **El CI se prueba temprano:** crea el remoto privado desde el inicio (con tu confirmación) y revisa cada push con `gh run list` (ver [instalación](instalacion.md#github-cli-gh-y-el-ci)).

## Verificación

Desde `codigo/`:

```bash
python -m pytest
ruff check . && ruff format --check . && mypy .
lint-imports
python manage.py makemigrations --check --dry-run
```

semgrep, con la misma versión que el CI (nativo en macOS y Linux o por WSL; por Docker en Windows con `MSYS_NO_PATHCONV=1`, `pwd -W` y el montaje de solo lectura `:ro`):

```bash
pipx run --spec "semgrep==1.178.0" semgrep scan --config p/python --config p/django --error --metrics=off \
  --exclude pruebas --exclude conftest.py .
```

`bandit`, `pip-audit`, gitleaks nativo y los escáneres de Docker (opcionales) están en la sección "Pruebas y calidad" del `README.md` de `codigo/`.
