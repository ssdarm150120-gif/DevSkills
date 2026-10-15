#!/usr/bin/env bash

# ============================================================================
# DevSkills - Desinstalador
# ============================================================================
# Quita EXACTAMENTE lo que registró install.sh en su manifiesto (agentes, skills
# y CLI) y la carpeta de la carga útil. No toca nada que no esté en el manifiesto
# ni los proyectos creados con `devskills init`.
# Variables: DEVSKILLS_SHARE_DIR (si se usó al instalar)
# ============================================================================

set -euo pipefail

if [[ -t 1 ]]; then
  VERDE='\033[0;32m'; AMARILLO='\033[1;33m'; CIAN='\033[0;36m'; NEGRITA='\033[1m'; NC='\033[0m'
else
  VERDE=''; AMARILLO=''; CIAN=''; NEGRITA=''; NC=''
fi

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) SO="windows" ;;
  *) SO="unix" ;;
esac

if [[ -n "${DEVSKILLS_SHARE_DIR:-}" ]]; then
  SHARE_DIR="$DEVSKILLS_SHARE_DIR"
elif [[ "$SO" == "windows" ]]; then
  SHARE_DIR="$HOME/bin/lib/devskills"
else
  SHARE_DIR="$HOME/.local/share/devskills"
fi
MANIFIESTO="$SHARE_DIR/manifiesto.txt"

echo ""
echo -e "${CIAN}${NEGRITA}  DevSkills - Desinstalador${NC}"
echo ""

if [[ ! -f "$MANIFIESTO" || ! -f "$SHARE_DIR/.devskills" ]]; then
  echo -e "${AMARILLO}⚠ DevSkills no está instalado con install.sh (no existe $MANIFIESTO).${NC}"
  echo "  Si lo instalaste como plugin: /plugin uninstall devskills@devskills-local"
  exit 0
fi

quitados=0
while IFS= read -r archivo; do
  [[ -z "$archivo" ]] && continue
  # Solo se quita lo que tiene aspecto de DevSkills: un manifiesto alterado no borra archivos ajenos.
  if [[ "$archivo" != *"/devskills-"* && "$(basename "$archivo")" != "devskills" && "$(basename "$archivo")" != "devskills.cmd" ]]; then
    continue
  fi
  if [[ -f "$archivo" ]]; then
    rm -f "$archivo"
    quitados=$((quitados + 1))
  fi
  # Borra carpetas que quedaron vacías (por ejemplo, la de cada skill), sin subir más allá.
  dir="$(dirname "$archivo")"
  while [[ "$dir" == *"/devskills-"* ]] && rmdir "$dir" 2>/dev/null; do
    dir="$(dirname "$dir")"
  done
done <"$MANIFIESTO"

rm -rf "$SHARE_DIR"
echo -e "${VERDE}✔ Quitados $quitados archivos y $SHARE_DIR.${NC}"
echo ""
echo -e "${NEGRITA}Nota:${NC} los proyectos creados con 'devskills init' no se tocan."
echo ""
