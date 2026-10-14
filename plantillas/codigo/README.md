# {{NOMBRE_PROYECTO}}: codigo

Monolito modular Django 5 (Python 3.12, PostgreSQL 16, Celery y Redis) con arquitectura hexagonal por
modulo. Los requisitos estan en `documentacion/SRS.md` y el diseno en `documentacion/DISENO.md`; este
archivo explica como levantarlo, probarlo y desplegarlo. **Todos los comandos se ejecutan desde
`codigo/`** (salvo los de Compose, que se ejecutan desde `codigo/despliegue/`).

El esqueleto viene del plugin DevSkills y ya trae los cimientos probados: `configuracion` (settings por
entorno con validacion, raiz de composicion), `nucleo` (actor, matriz de permisos, puertos, reloj y bus
de eventos con outbox), `identidad` (usuarios, roles, ingreso, segundo factor, gestion de usuarios y
aviso por reuso de un codigo), `auditoria` (modulo vacio, listo para la bitacora), `herramientas`
(contratos de import-linter, roles de la base, bases embebidas) y `despliegue` (Compose, nginx con TLS,
Dockerfile).

## Requisitos

| Para | Hace falta |
|------|------------|
| Todo | Git y Python 3.12 (`python --version`) |
| Compose, escaneres de seguridad | Docker Desktop (en Windows, con WSL2) y Docker Compose 2.24 o superior |
| Desarrollo sin Docker | Nada mas: la base de datos la levanta `herramientas.base_local` |

```bash
python -m venv ../.venv                      # el entorno virtual vive en la raiz del repositorio
../.venv/Scripts/activate                    # Windows (en Linux o macOS: source ../.venv/bin/activate)
pip install -r requirements-dev.txt          # dependencias, pruebas y herramientas de calidad
```

## Reglas del host (Docker y puertos)

- Los contenedores de este proyecto llevan el prefijo **`{{SLUG}}`** (nombre del proyecto de Compose:
  `{{SLUG}}-dev` y `{{SLUG}}-pruebas`). Para ver, detener o limpiar solo lo tuyo:
  `docker ps --filter name={{SLUG}}`.
- El proyecto solo publica puertos de **su rango propio**: {{PUERTO_BASE}} a {{PUERTO_FINAL}}. nginx usa
  `{{PUERTO_HTTP}}` (HTTP) y `{{PUERTO_HTTPS}}` (HTTPS), y solo en `127.0.0.1`.
- **Nunca** se usan los puertos reservados del host: **{{PUERTOS_RESERVADOS}}** (por ejemplo, el
  PostgreSQL de otro sistema en 5432). Ningun valor por defecto apunta a `localhost:5432`.

## Levantar todo con Docker Compose (desarrollo)

Servicios: `nginx` (TLS), `web` (Django con uvicorn), `worker` (Celery), `worker-outbox` y `beat` (el bus
de eventos), `postgres` 16 y `redis`, mas dos pasos de una sola vez: `certificado` y `migrar`. Cada
servicio sigue las redes de DISENO D.6.1.

```bash
cd despliegue
cp .env.ejemplo .env            # en PowerShell: Copy-Item .env.ejemplo .env
# Reemplaza cada CAMBIAR_... de .env por un secreto propio:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up -d --build
curl -k https://localhost:{{PUERTO_HTTPS}}/salud          # 200 {"estado": "ok"}
docker compose down -v                        # baja todo y BORRA los datos
```

- **Puertos del host:** `https://localhost:{{PUERTO_HTTPS}}` y `http://localhost:{{PUERTO_HTTP}}`
  (redirige a HTTPS). Solo nginx publica puertos, y solo en `127.0.0.1`. **PostgreSQL no se publica**,
  asi que nunca choca con otro PostgreSQL de tu maquina. Para entrar:
  `docker compose exec postgres psql -U app_admin app`.
- **Orden de arranque:** `postgres` y `redis` sanos, luego `migrar` (roles y migraciones), luego `web`,
  `worker`, `worker-outbox` y `beat`, y al final `nginx`. `docker compose ps` muestra el estado de salud
  de cada uno.
- **`.env` no se versiona** (esta en `.gitignore`); `.env.ejemplo` si, con valores ficticios. Si queda un
  `CAMBIAR...`, la aplicacion, `migrar` y los roles se niegan a arrancar.
- **Logs y shell:** `docker compose logs -f web`; `docker compose exec web python manage.py check --deploy`.
- **Primer Administrador:** `docker compose exec web python manage.py crear_administrador correo@dominio`
  (muestra una contrasena temporal una sola vez; se cambia en el primer ingreso y despues se enrola el
  segundo factor).

### Entorno de pruebas (staging, en localhost mientras no exista el servidor)

Staging corre en **localhost** con una imagen **construida en tu maquina** hasta que exista el servidor
de pruebas. `docker-compose.pruebas.yml` se superpone al de desarrollo, no construye y usa la imagen que
le des (`APP_IMAGEN`, por defecto `{{SLUG}}:pruebas`). El CI **no** publica imagenes: las construye, las
escanea y las descarta.

```bash
# 1. Construir la imagen (desde codigo/)
docker build -f despliegue/Dockerfile -t {{SLUG}}:pruebas .

# 2. Configurar el entorno (desde codigo/despliegue/)
cd despliegue
cp .env.ejemplo .env.pruebas    # en PowerShell: Copy-Item .env.ejemplo .env.pruebas
# Reemplaza cada CAMBIAR_... por un secreto propio.
# En localhost deja APP_NOMBRE_PUBLICO=localhost, los puertos del rango propio y las tres lineas de HSTS cortas.

# 3. Levantar (usa la imagen local: nunca la descarga mientras exista)
docker compose --env-file .env.pruebas -f docker-compose.yml -f docker-compose.pruebas.yml up -d
docker compose --env-file .env.pruebas -f docker-compose.yml -f docker-compose.pruebas.yml ps   # "healthy"
curl -k https://localhost:{{PUERTO_HTTPS}}/salud                                                # 200

# 4. Bajar y borrar los datos
docker compose --env-file .env.pruebas -f docker-compose.yml -f docker-compose.pruebas.yml down -v
```

- Corre **un solo entorno a la vez** en localhost: desarrollo y pruebas publican los mismos puertos. Sus
  volumenes si son distintos (proyectos `{{SLUG}}-dev` y `{{SLUG}}-pruebas`).
- Despues de cambiar el codigo, vuelve a ejecutar el paso 1 y el 3.
- **Imagen de un registro** (cuando exista el servidor de pruebas): en `.env.pruebas`,
  `APP_IMAGEN=ghcr.io/<organizacion>/{{SLUG}}:<sha>` y `APP_PULL_POLICY=always`. En el servidor tambien
  se borran las tres lineas de HSTS y se usan los puertos 80 y 443 (`.env.ejemplo` lo explica).
- El despliegue automatico esta preparado en `.github/workflows/desplegar-pruebas.yml`, sin ejecutar: falta
  el servidor. Solo corre desde `main`, y el environment `pruebas` de GitHub debe restringirse a `main` y
  exigir revisores (lo configura una persona; el detalle esta en el encabezado del flujo).

### Endurecimiento de los contenedores

| Servicio | Usuario | Sistema de archivos | Capacidades de Linux | Limites |
|----------|---------|---------------------|----------------------|---------|
| `web`, `worker`, `worker-outbox`, `beat`, `migrar` | `app` (10001) | solo lectura, `/tmp` en memoria | ninguna | `web`: 512 MB y 256 procesos. `worker`: 768 MB y 256 procesos. `worker-outbox`: 512 MB y 256. `beat`: 256 MB y 128 |
| `redis` | `redis` | solo lectura, `/tmp` en memoria, datos en el volumen | ninguna | |
| `nginx` | `nginx` (101) | solo lectura; `/tmp`, `/var/cache/nginx`, `/run` y `/etc/nginx/conf.d` en memoria | ninguna | |
| `postgres` | `postgres` | escritura (datos en el volumen) | solo `CHOWN`, `SETUID`, `SETGID`, `FOWNER` y `DAC_OVERRIDE` | |
| `certificado` | root, un solo paso | solo lectura | solo `CHOWN` | |

Todos llevan `no-new-privileges`. Los limites se suben en `docker-compose.yml` si la carga real lo pide.
`nginx` tiene un healthcheck que espera el `301` del puerto 8080 del contenedor con el nombre publico.

### TLS

nginx acepta TLS 1.2 y 1.3. En TLS 1.2 solo negocia `ECDHE` con `AES-GCM` o `CHACHA20-POLY1305` (perfil
"intermediate" de Mozilla sin los cifrados `CBC` ni `DHE`). Para comprobar que se rechaza uno debil:

```bash
echo | openssl s_client -connect localhost:{{PUERTO_HTTPS}} -servername localhost -tls1_2 -cipher ECDHE-ECDSA-AES128-SHA
# esperado: "alert handshake failure" y "Cipher is (NONE)"
```

### Certificado TLS (autofirmado, solo desarrollo y pruebas)

`docker compose up` lo genera solo, una vez, en el volumen `certificados` (nunca en el repositorio):
EC P-256, 365 dias, con `localhost`, `127.0.0.1`, `::1` y `APP_NOMBRE_PUBLICO` como nombres validos. Por
eso `curl` necesita `-k` y el navegador avisa.

```bash
docker compose run --rm certificado                       # lo crea si falta o si cambio el nombre
docker compose run --rm -e REGENERAR=1 certificado        # lo regenera
docker compose restart nginx                              # nginx lee el certificado al arrancar
```

`APP_NOMBRE_PUBLICO` solo admite letras, digitos, `.` y `-` (sin empezar ni terminar en `.` o `-`).
En produccion el certificado del dominio real lo entrega quien opera la infraestructura y se monta como
`tls.crt` y `tls.key` en ese mismo volumen (DISENO D.6.1).

### Quien emite cada encabezado

- **nginx:** TLS, redireccion de HTTP a HTTPS, proxy con `X-Forwarded-Proto: https` **fijo** (nunca
  reenvia el del cliente), limite de 10 MB, corte de los `Host` desconocidos y limite de peticiones (POST)
  por IP en el ingreso (ver abajo).
- **Django:** `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options`, `nosniff` y
  `Referrer-Policy`. nginx **no** agrega ninguno, para que el navegador nunca reciba dos CSP.
- **Confianza en el proxy:** Django solo cree en `X-Forwarded-Proto` si `CONFIAR_EN_PROXY_TLS=true`, que
  el Compose define porque nginx siempre esta delante. `web` no publica puertos: solo nginx llega a el.

### Limite de peticiones en el ingreso (DISENO D.5.4)

`/ingresar` es la unica ruta interna sin sesion. Ademas del bloqueo por cuenta (5 intentos, 15 minutos),
nginx limita las peticiones **POST por IP** a `/ingresar` y a todas sus etapas (`/ingresar/contrasena`,
`/ingresar/enrolar`, `/ingresar/codigo`) con `limit_req`: cada intento cuesta un hash Argon2, y el bloqueo
por cuenta no frena a quien prueba muchas cuentas desde un mismo origen. Los GET y el resto de rutas no
se cuentan. La ruta se compara sobre la URI ya normalizada.

- Por defecto: ritmo de **180 POST por minuto** por IP (`APP_LIMITE_INGRESO=180r/m`) y una rafaga de
  **40** (`APP_RAFAGA_INGRESO=40`). Es holgado a proposito: varios usuarios detras de una VPN o un NAT
  comparten IP.
- Al rebasarlo, nginx contesta `429` con el texto "Demasiadas peticiones desde tu red. Espera un minuto e
  inténtalo de nuevo." y lo anota en su bitacora (`limiting requests`).
- Si algun dia hay un balanceador delante de nginx, todos compartirian IP: antes de tocar este limite hay
  que configurar el modulo `realip` de nginx.

### Base de datos: el rol de la aplicacion no es dueno del esquema (D.6.3)

| Cuenta | Para que | Quien la usa |
|--------|----------|--------------|
| `app_admin` | Administra PostgreSQL y crea los roles | Solo `migrar` |
| `app_migraciones` | Dueno de la base y de las tablas | Solo `manage.py migrate` (`settings.migraciones`) |
| `app_web` | SELECT, INSERT, UPDATE y DELETE; sin CREATE ni ownership | `web` y `worker` (`DATABASE_URL`) |

`python -m herramientas.roles_bd` es idempotente y concede tambien sobre lo que ya exista. Si alguna vez
una migracion falla por permisos, vuelve a correr `docker compose run --rm migrar`.

## Levantar la base local sin Docker

```bash
python -m herramientas.base_local            # imprime DATABASE_URL (PostgreSQL 16 embebido en ../.pgdata)
export DATABASE_URL="<la URL impresa>"       # PowerShell: $env:DATABASE_URL = "<la URL impresa>"
python manage.py migrate
python manage.py runserver                   # usa configuracion.settings.dev
python -m herramientas.base_local --detener
```

En desarrollo `DATABASE_URL` es obligatoria: ningun valor por defecto apunta a `localhost:5432`. Esa base
usa `--auth=trust` y es **solo para tu maquina**.

## Pruebas y calidad

```bash
pytest -q                          # todo; usa su propio PostgreSQL embebido (../.pgdata_pruebas)
pytest -q -m "not lento"           # sin las que lanzan procesos externos (lint-imports, Docker, pg)
ruff check . && ruff format --check .
mypy && mypy .                     # estricto en */dominio y despues todo el codigo
lint-imports                       # limites entre modulos
python -m herramientas.contratos_importlinter | diff - .importlinter    # contratos sincronizados
bandit -q -r . -x "*/pruebas/*,./conftest.py"
pip-audit -r requirements.txt -r requirements-dev.txt
python manage.py makemigrations --check --dry-run
python manage.py check --deploy --fail-level WARNING        # con las variables de prod, como en el CI
```

Dos sesiones de `pytest` a la vez no se pisan: cada una crea su base `test_<base>_<pid>_<azar>`.

### Escaneres con Docker (los mismos del CI, sin instalar nada)

```bash
docker build -f despliegue/Dockerfile -t {{SLUG}}:dev .
docker run --rm -i hadolint/hadolint:v2.15.1 < despliegue/Dockerfile
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.75.0 image \
  --exit-code 1 --severity CRITICAL,HIGH --ignore-unfixed --no-progress {{SLUG}}:dev
docker run --rm -v "$PWD:/src" semgrep/semgrep:1.178.0 semgrep scan --config p/python --config p/django \
  --error --metrics=off --exclude pruebas --exclude conftest.py /src
docker run --rm -v "$PWD/..:/repo" zricethezav/gitleaks:v8.21.2 detect --source /repo --redact --no-banner
```

En Git Bash sobre Windows antepone `MSYS_NO_PATHCONV=1` a los comandos con `-v` y usa `$(pwd -W)` en lugar de `$PWD` (por ejemplo, `-v "$(pwd -W):/src"`). La versión de semgrep es la misma de `semgrep==` en `.github/workflows/ci.yml`; debe terminar con código 0 y "Findings: 0". La regla `django-no-csrf-token` solo reconoce `{% csrf_token %}` con el `</form>` a 10 líneas o menos: los formularios largos se parten en parciales.

## Variables de entorno

Las lee `configuracion/entorno.py`; la lista completa y comentada esta en `despliegue/.env.ejemplo`.

| Variable | Donde | Notas |
|----------|-------|-------|
| `DATABASE_URL` | dev y prod | `postgres://usuario:clave@host:puerto/base`. En prod es la del rol `app_web` |
| `DATABASE_MIGRACIONES_URL` | solo `migrar` | Rol dueno. `settings.prod` **rechaza** que exista en `web` o `worker` |
| `DATABASE_ADMIN_URL`, `APP_MIGRACIONES_PASSWORD` | solo `migrar` | Rol administrador y clave del rol dueno. `settings.prod` tambien las **rechaza** en `web` y `worker` |
| `SECRET_KEY` | prod | 50 caracteres o mas, 16 distintos, sin el prefijo `django-insecure-` ni `CAMBIAR` |
| `APP_LLAVE_HUELLA` | prod | Llave del HMAC de la huella del correo en el registro de ingresos: mismas reglas, **distinta de `SECRET_KEY`** |
| `APP_LLAVE_SEGUNDO_FACTOR` | prod | Llave que **cifra** el secreto TOTP del segundo factor (AES-256-GCM): mismas reglas, **distinta de `SECRET_KEY` y de `APP_LLAVE_HUELLA`**. **Respáldala aparte de la base** (si se pierde, los roles sensibles se enrolan de nuevo) |
| `APP_LIMITE_INGRESO`, `APP_RAFAGA_INGRESO` | Compose | Limite de POST por IP en `/ingresar` (opcionales; `180r/m` y `40`). Los lee nginx, no Django |
| `APP_NOMBRE_APLICACION` | dev y prod | Nombre que se muestra en la interfaz y **emisor** en la aplicacion de codigos del segundo factor |
| `APP_SESION_DURACION_MAXIMA_HORAS` | dev y prod | Tope absoluto de la sesion desde el ingreso (12 por defecto; ademas rigen las 3 horas de inactividad) |
| `APP_ZONA_HORARIA` | dev y prod | Zona horaria con la que se muestran las fechas (se guardan en UTC): `UTC` o `Area/Ciudad`. Un nombre mal escrito, legado o ambiguo (`US/Eastern`, `EST5EDT`, `posixrules`, `Etc/...`) impide el arranque |
| `APP_NOMBRE_CELERY` | dev y prod | Nombre de la app de Celery (`app` por defecto) |
| `ALLOWED_HOSTS` | prod | Ver la regla de abajo |
| `REDIS_URL` | prod | Con clave: `redis://:clave@redis:6379/0` |
| `CONFIAR_EN_PROXY_TLS` | prod | `true` solo detras de nginx; por defecto `false` |
| `SECURE_SSL_REDIRECT` | prod | `true` por defecto |
| `HSTS_SEGUNDOS`, `HSTS_SUBDOMINIOS`, `HSTS_PRELOAD` | prod | Por defecto 31536000, `true`, `true`. En `localhost` se acortan (ver abajo) |
| `APP_ADAPTADOR_<PUERTO>` | dev y prod | Uno por cada puerto elegible que declares en `configuracion/adaptadores.py`: `falso` (dev) o el real. **Prod rechaza `falso`** |
| `APP_PERMITIR_ADAPTADORES_FALSOS` | solo Compose de desarrollo | Deja a `settings.prod` aceptar los falsos, **solo** si `ALLOWED_HOSTS` son de la propia maquina |

**`ALLOWED_HOSTS` y el despliegue.** Siempre un host **propio** (`app.empresa.example`) o un comodin propio
con punto inicial (`.empresa.example`, que cubre `empresa.example` y todos sus subdominios). Nunca `*`,
nunca un comodin de sufijo publico (`.com`, `.com.mx`, `.co.uk`), porque habilitaria **cualquier** dominio
bajo ese sufijo. Produccion rechaza `*`, `0.0.0.0`, los hosts con puerto y **todo** comodin `.x` cuyo `x`
este en la Public Suffix List completa, **incluidos sus sufijos privados** (`.github.io`); acepta
`.empresa.example` y `.empresa.com.mx`. La lista viene **empaquetada** con la dependencia
`publicsuffixlist` y se consulta **sin red**. No instales el extra `[update]` ni ejecutes
`publicsuffixlist-download`: son lo unico del paquete que usa la red.

**HSTS en `localhost`.** El navegador recuerda HSTS por dominio y por **todos** sus puertos. Por eso
`.env.ejemplo` trae `HSTS_SEGUNDOS=300` y sin `includeSubDomains` ni `preload`. En pruebas y produccion se
borran esas tres lineas.

## Roles y permisos

- **Catalogo de roles** (`identidad/dominio/roles.py`, sembrado por la migracion `0003_roles_iniciales`):
  `administrador` (gestiona usuarios, exige segundo factor), `auditor` (ejemplo de rol sensible: consulta
  la bitacora y exige segundo factor) y `usuario` (ejemplo de rol sin segundo factor). **Decision del
  esqueleto:** se quitaron los roles propios del dominio del proyecto de referencia; cada proyecto agrega
  los de su SRS (2.3 Clases de usuarios).
- **Para agregar un rol:** (1) una migracion de datos nueva en `identidad/adaptadores/salida/migraciones/`
  con el mismo patron de `0003` (su reversa se detiene con un mensaje claro si alguien tiene el rol); (2) su
  codigo en `identidad/dominio/roles.py` (y en `ROLES_CON_SEGUNDO_FACTOR` si es sensible); (3) su codigo y
  sus capacidades en `nucleo/permisos.py`; (4) las pruebas de los tres lugares.
- **Matriz de permisos** (`nucleo/permisos.py`): capacidades por rol, deniega por defecto, y los roles se
  suman. El permiso se verifica en el caso de uso (`puede(actor, capacidad)`), no solo en la vista.
- **`Actor`** (`nucleo/actor.py`): id y roles, inmutable y validado (tambien al copiar o des-serializar).
  Si tu dominio necesita un alcance de lectura (una cartera, una sucursal), agregalo al `Actor` con su
  validacion y su funcion pura en `nucleo/permisos.py`, documentado en un ADR.

## Segundo factor

Los roles sensibles (`administrador` y `auditor` en el esqueleto) no entran solo con la contrasena. Las
etapas del ingreso, en orden (DISENO D.3.10): contrasena, cambio obligatorio (si la contrasena es
temporal), **enrolamiento** (si todavia no tiene segundo factor) y **codigo**. Cada etapa pendiente guarda
el sello de la cuenta y una marca de tiempo en la sesion, vence a los 15 minutos y solo admite su propia
ruta.

- **Algoritmo:** TOTP (RFC 6238, `django_otp.oath`), SHA-1, 6 digitos, pasos de 30 s, con tolerancia de un
  paso antes y uno despues. Un codigo ya usado no se acepta otra vez (`ultimo_paso_aceptado`).
- **Secreto cifrado:** en `identidad.segundo_factor`, con AES-256-GCM y una llave derivada con HKDF de
  `APP_LLAVE_SEGUNDO_FACTOR`; la llave debe ser distinta de `SECRET_KEY` y de `APP_LLAVE_HUELLA`. El
  `usuario_id` va como dato asociado. Si la llave se pierde o cambia, el segundo factor queda "no
  disponible" (falla cerrado) y el Administrador lo reinicia.
- **Enrolamiento:** `/ingresar/enrolar` muestra el QR (SVG generado en el servidor, sin JavaScript ni
  estilos en linea: la CSP estricta no se relaja) y la clave.
- **Limite de intentos:** 5 codigos incorrectos seguidos bloquean la cuenta 15 minutos, con un contador
  separado del de la contrasena.
- **Falla cerrado:** sin adaptador, sin llave o con un secreto que no se descifra, un rol sensible no entra.
- **Aviso por reuso de un codigo:** cada codigo repetido deja un `IntentoIngreso` con motivo
  `codigo_repetido`. En el siguiente ingreso completo del dueno, la pantalla de inicio muestra una sola vez
  el momento del intento mas reciente (en `APP_ZONA_HORARIA`), sin la IP ni nada de quien lo hizo. La marca
  de "visto" es el **id** del ultimo intento mostrado y nunca retrocede; dos pestañas no lo muestran dos
  veces.

## Puertos, adaptadores falsos y como agregar un sistema externo

Los puertos que usan varios modulos viven en `nucleo/puertos/` (Python puro, DISENO 1.7) y
`configuracion/adaptadores.py` conecta el adaptador elegido al arrancar. **Produccion se niega a arrancar
con un adaptador falso.** El esqueleto no trae ningun sistema externo; la receta para agregar uno (por
ejemplo, un ERP o un canal de mensajeria) es:

1. **Puerto:** un `Protocol` con `@runtime_checkable` en `nucleo/puertos/` (o en `aplicacion/puertos.py` del
   modulo, si solo lo usa el), con valores como dataclasses inmutables y errores tipados que hereden de
   `nucleo.puertos.ErrorDeIntegracion` (`reintentable`, `reintentar_en_segundos`).
2. **Adaptador falso** en el adaptador de salida del modulo duenio, con datos **ficticios** y seguro con
   hilos, y **prueba de contrato** reutilizable en `nucleo/pruebas/contratos/` (una clase base con las
   fixtures `adaptador` y `referencias`; el adaptador real la reutilizara).
3. **Eleccion por entorno:** un `PuertoElegible("APP_ADAPTADOR_<PUERTO>", (FALSO, "real"), "real")` en
   `PUERTOS_ELEGIBLES`, su bloque en `conectar(...)`, `APP_ADAPTADOR_<PUERTO>: falso` en el Compose de
   desarrollo y el real en el de pruebas.
4. Si escribe hacia afuera, **por el outbox**: el envio se guarda en la misma transaccion que el cambio.

**Con adaptadores falsos, `APP_ENLACE` debe seguir en `127.0.0.1`.** El permiso
`APP_PERMITIR_ADAPTADORES_FALSOS` solo valida el `Host` contra `ALLOWED_HOSTS`; no mira la interfaz de red.

Reglas del registro de puertos (`nucleo/puertos/registro.py`): un puerto se conecta **una sola vez**
(`PuertoYaConectado`); pedir uno sin adaptador lanza `PuertoSinAdaptador` (hereda de `RuntimeError`); las
pruebas que reemplazan un adaptador usan `nucleo.pruebas.aislamiento.Aislamiento`, exclusivo de pruebas.

## Modulos y limites (import-linter)

`configuracion/modulos.py` es la fuente unica de los modulos, sus esquemas de PostgreSQL y sus
dependencias permitidas (DISENO D.1.3). Para agregar un modulo: copia la estructura de `auditoria`
(`dominio/`, `aplicacion/`, `adaptadores/entrada|salida/`, `api_publica.py`, `pruebas/`, `apps.py` y su
migracion `0001_esquema`), agregalo a `MODULOS_NEGOCIO`, declara sus flechas en `DEPENDENCIAS` y regenera
los contratos con `python -m herramientas.contratos_importlinter --escribir`. Una prueba compara
`DEPENDENCIAS` con el diagrama Mermaid de D.1.3 del DISENO cuando ese diagrama existe.

## Bus de eventos y outbox

Los modulos se avisan con **eventos de dominio** (DISENO D.5.1 y D.5.2). El catalogo esta en
`nucleo/puertos/catalogo_eventos.py`: un evento que no esta ahi no se puede publicar, y cada modulo solo
publica los suyos (`EmisorNoAutorizado`).

- **Publicar:** el caso de uso llama a `PublicadorDeEventos.publicar(evento)`. El evento se guarda en
  `nucleo.evento_outbox` en la **misma transaccion** que el cambio de negocio; sin transaccion se niega
  (`EventoFueraDeTransaccion`).
- **Entregar:** por cada consumidor suscrito hay una fila en `nucleo.entrega_outbox`. `beat` dispara
  `nucleo.despachar_outbox` cada 5 segundos y la atiende `worker-outbox` (cola `outbox`) con
  `SELECT ... FOR UPDATE SKIP LOCKED`. La entrega es **al menos una vez**: los consumidores son
  idempotentes por `evento_id`.
- **Reintentos:** espera exponencial de 30 s (maximo 5 reintentos, tope de 1 h); agotados, la entrega
  queda en `error` y se publica `ErrorIntegracionRegistrado`.
- **Tiempo maximo:** `statement_timeout` de 30 s y `lock_timeout` de 5 s por entrega; la tarea lleva
  `soft_time_limit` de 240 s. **`SoftTimeLimitExceeded` hereda de `Exception`**: el despachador la deja
  pasar a proposito (un `except Exception` se la tragaria) y la entrega en curso queda `pendiente`.
- **Datos que no viajan:** el bus rechaza claves (normalizadas) como `correo`, `telefono`, `codigo`,
  `token`, `api_key`, `cookie`..., y valores con forma de correo o de telefono. Una `terminacion_*` solo
  admite 4 caracteres.
- **Retencion:** 30 dias despues de entregados, por lotes, con la funcion `nucleo.purgar_eventos_outbox`
  (SECURITY DEFINER); la aplicacion no puede borrar eventos.
- **Suscribir un consumidor:** desde `configuracion/adaptadores.py`,
  `obtener(RegistroDeConsumidores).suscribir("nombre", manejador, eventos=[...])`, al arrancar.

### Operar la cola

```bash
docker compose exec web python manage.py outbox_estado            # pendientes, atraso, errores
docker compose exec web python manage.py outbox_estado --errores  # y la lista de entregas en error
docker compose exec web python manage.py outbox_reintentar --entrega 12
docker compose exec web python manage.py outbox_purgar --dry-run   # cuantos eventos se purgarian
docker compose logs -f worker-outbox
```

`outbox_estado` sale con codigo 1 si hay entregas en error (sirve de sonda). Solo debe haber **un** `beat`.

## Gotchas conocidos (aprendidos en el proyecto de referencia)

- **`SELECT ... FOR UPDATE OF` falla en PostgreSQL con tablas calificadas por esquema** (las de este
  esqueleto lo son: `"modulo"."tabla"`). Para bloquear filas con joins: lee los ids, bloquea sin joins en
  orden estable y vuelve a leer (ver `bloquear_administradores_activos`).
- **Oraculo de tiempo en el ingreso:** el camino de un correo inexistente hace el mismo trabajo de base de
  datos y de hash que el de una cuenta existente (`trabajo_equivalente_sin_cuenta`, `verificar_ficticia`).
- **Un "un solo uso" que depende de que quien llama abra una transaccion no es un control:** el adaptador
  garantiza su propio bloqueo (segundo factor, aviso por reuso).
- **Todo camino que cambie la contrasena rota el sello de sesion** (`set_password` incluido): el hash de la
  sesion depende solo del sello.
- **Windows y CRLF:** `.gitattributes` fuerza LF; los generadores escriben con `newline="\n"`.

## Que no esta todavia

Lo que tu DISENO pida y el esqueleto no trae (almacenamiento de archivos, antivirus, observabilidad con
logs JSON, respaldos, limite de peticiones de webhooks publicos, sistemas externos) se agrega con el
elemento del plan que lo construya.
