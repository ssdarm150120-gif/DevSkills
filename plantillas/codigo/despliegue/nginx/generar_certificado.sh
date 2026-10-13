#!/bin/sh
# Certificado AUTOFIRMADO para desarrollo y pruebas (no se versiona: vive en el volumen `certificados`).
#
#   docker compose run --rm certificado            # lo genera si falta o si cambio el nombre
#   docker compose run --rm -e REGENERAR=1 certificado
#
# `docker compose up` ya lo ejecuta antes de nginx. En produccion NO se usa: el certificado lo
# provee TI para el dominio real (DISENO D.6.1: "Dominio y certificado").
set -eu

DESTINO="${DESTINO:-/certs}"
NOMBRE="${APP_NOMBRE_PUBLICO:?falta APP_NOMBRE_PUBLICO}"

# El nombre acaba dentro del `-subj` y del `subjectAltName` de openssl: una coma, una barra, un
# `=` o un salto de linea cambiarian el significado de esos campos. Solo letras, digitos, puntos y
# guiones, y sin empezar ni terminar en punto o guion (nombre de host DNS).
case "$NOMBRE" in
    *'
'*) echo "APP_NOMBRE_PUBLICO invalido: no puede tener saltos de linea" >&2; exit 1 ;;
esac
if ! printf '%s\n' "$NOMBRE" | grep -Eq '^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$'; then
    echo "APP_NOMBRE_PUBLICO invalido: solo letras, digitos, '.' y '-' (recibido: $NOMBRE)" >&2
    exit 1
fi

if [ "${REGENERAR:-0}" != "1" ] && [ -s "$DESTINO/tls.crt" ] && [ -s "$DESTINO/tls.key" ] \
    && openssl x509 -in "$DESTINO/tls.crt" -noout -checkend 86400 \
    && openssl x509 -in "$DESTINO/tls.crt" -noout -ext subjectAltName | grep -Fq "DNS:$NOMBRE,"; then
    echo "certificado vigente para $NOMBRE: no se regenera"
    exit 0
fi

# Sin DAC_OVERRIDE ni FOWNER (el contenedor solo tiene CHOWN): se borran los archivos de una
# ejecucion anterior (ya son de nginx, uid 101) y los permisos se fijan ANTES de cambiar el dueno.
rm -f "$DESTINO/tls.crt" "$DESTINO/tls.key"

# `localhost` siempre debe ir en el SAN, pero sin repetirlo si ya es el nombre publico (los nombres
# DNS no distinguen mayusculas).
SAN="DNS:$NOMBRE"
if [ "$(printf '%s' "$NOMBRE" | tr 'A-Z' 'a-z')" != "localhost" ]; then
    SAN="$SAN,DNS:localhost"
fi
SAN="$SAN,IP:127.0.0.1,IP:::1"

openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 365 \
    -keyout "$DESTINO/tls.key" -out "$DESTINO/tls.crt" \
    -subj "/O=Certificado autofirmado (solo desarrollo y pruebas)/CN=$NOMBRE" \
    -addext "subjectAltName=$SAN"

# nginx-unprivileged corre como uid 101 y solo lee.
chmod 644 "$DESTINO/tls.crt"
chmod 640 "$DESTINO/tls.key"
chown 101:101 "$DESTINO/tls.crt" "$DESTINO/tls.key"
echo "certificado autofirmado generado para $NOMBRE (365 dias)"
