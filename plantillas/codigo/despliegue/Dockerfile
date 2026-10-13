# Imagen de la aplicacion Django (`web`, `worker` y los pasos de una sola vez: DISENO D.6.1).
# Contexto de construccion: `codigo/`.   docker build -f despliegue/Dockerfile -t {{SLUG}} .
#
# Multi-stage: el constructor instala las dependencias en un virtualenv; la imagen final solo lleva
# ese virtualenv y el codigo (sin pip cache, sin compiladores, sin pruebas ni .env: ver .dockerignore).
# Sin secretos: todo llega por variables de entorno en tiempo de ejecucion.

# Imagen base fijada por etiqueta Y digest (reproducible); se actualiza a proposito, no sola.
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS constructor
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --require-virtualenv -r /tmp/requirements.txt

FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS final
# Correcciones de seguridad de Debian publicadas despues de la imagen base (trivy falla en HIGH
# y CRITICAL con parche). `apt-get upgrade` las trae sin fijar versiones de paquetes que no usamos.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Usuario sin privilegios y sin shell. El codigo es de root y de solo lectura para la aplicacion:
# si alguien lograra ejecutar codigo en el proceso, no podria reescribirlo.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=configuracion.settings.prod \
    PUERTO_WEB=8000

COPY --from=constructor /opt/venv /opt/venv
WORKDIR /app
COPY . /app

USER 10001:10001
EXPOSE 8000

# `/salud` por el loopback del contenedor (no pasa por nginx): ver herramientas/sonda_salud.py.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-m", "herramientas.sonda_salud"]

# Un proceso por contenedor; las replicas se escalan con Compose. Los encabezados X-Forwarded-*
# no se procesan aqui: Django decide con `CONFIAR_EN_PROXY_TLS` (configuracion/settings/prod.py).
CMD ["uvicorn", "configuracion.asgi:application", "--host", "0.0.0.0", "--port", "8000", \
     "--lifespan", "off", "--no-proxy-headers", "--no-server-header"]
