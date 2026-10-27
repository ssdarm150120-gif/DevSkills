#!/usr/bin/env bash

# ============================================================================
# DevSkills - Instalador (sin el sistema de plugins de Claude Code)
# ============================================================================
# Copia los agentes y las skills a ~/.claude con el prefijo "devskills-" para no
# pisar nada, deja la carga útil (plantillas, scripts) en una carpeta propia e
# instala el CLI `devskills` en el PATH del usuario. Registra cada archivo en un
# manifiesto para que uninstall.sh quite exactamente lo instalado.
#
# Uso: bash install.sh [--si] [--forzar]
#   --si      no pregunta antes de reinstalar
#   --forzar  sobrescribe archivos ajenos que choquen (por defecto pregunta o aborta)
# Variables: CLAUDE_CONFIG_DIR (por defecto ~/.claude), DEVSKILLS_BIN_DIR, DEVSKILLS_SHARE_DIR
# ============================================================================

set -euo pipefail

if [[ -t 1 ]]; then
  ROJO='\033[0;31m'; VERDE='\033[0;32m'; AMARILLO='\033[1;33m'; AZUL='\033[0;34m'; CIAN='\033[0;36m'; NEGRITA='\033[1m'; NC='\033[0m'
else
  ROJO=''; VERDE=''; AMARILLO=''; AZUL=''; CIAN=''; NEGRITA=''; NC=''
fi

detectar_so() {
  case "$(uname -s)" in
    Darwin*) echo "macos" ;;
    MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
    *) echo "linux" ;;
  esac
}
SO="$(detectar_so)"

SI=false
FORZAR=false
for arg in "$@"; do
  case "$arg" in
    --si|-y) SI=true ;;
    --forzar) FORZAR=true ;;
    -h|--help) sed -n '3,17p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo -e "${ROJO}Opción desconocida: $arg${NC}" >&2; exit 2 ;;
  esac
done

ORIGEN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

if [[ -n "${DEVSKILLS_BIN_DIR:-}" ]]; then
  BIN_DIR="$DEVSKILLS_BIN_DIR"
elif [[ "$SO" == "windows" ]]; then
  BIN_DIR="$HOME/bin"
elif [[ -w "/usr/local/bin" ]]; then
  BIN_DIR="/usr/local/bin"
else
  BIN_DIR="$HOME/.local/bin"
fi

if [[ -n "${DEVSKILLS_SHARE_DIR:-}" ]]; then
  SHARE_DIR="$DEVSKILLS_SHARE_DIR"
elif [[ "$SO" == "windows" ]]; then
  SHARE_DIR="$HOME/bin/lib/devskills"
else
  SHARE_DIR="$HOME/.local/share/devskills"
fi
MANIFIESTO="$SHARE_DIR/manifiesto.txt"
MARCA="$SHARE_DIR/.devskills"

# Las rutas se escriben dentro de las skills y del CLI instalados y en el manifiesto (una por línea).
# Se rechazan las que no se pueden incrustar sin riesgo: saltos de línea o caracteres de control,
# y `$`, comillas dobles y acento grave, que un shell interpretaría al correr los comandos de las skills.
# Los caracteres especiales de sed (`&`, `\`, `#`) sí se admiten: se escapan al sustituir.
validar_ruta() {
  local nombre="$1" ruta="$2"
  if [[ "$ruta" =~ [[:cntrl:]] ]]; then
    echo -e "${ROJO}✘ $nombre lleva un salto de línea o un carácter de control; elige otra ruta.${NC}" >&2
    exit 2
  fi
  if [[ "$ruta" == *'$'* || "$ruta" == *'"'* || "$ruta" == *'`'* ]]; then
    echo -e "${ROJO}✘ $nombre ($ruta) lleva \$, comillas dobles o acento grave, que no se pueden incrustar con seguridad en las skills; elige otra ruta.${NC}" >&2
    exit 2
  fi
}
validar_ruta "La carpeta de la carga útil" "$SHARE_DIR"
validar_ruta "La carpeta del CLI" "$BIN_DIR"
validar_ruta "La carpeta de Claude" "$CLAUDE_DIR"
validar_ruta "La carpeta de origen" "$ORIGEN"

# Escapa un texto para usarlo como reemplazo de sed con `#` de delimitador.
escapar_sed() {
  printf '%s' "$1" | sed -e 's/[\\&#]/\\&/g'
}

# Ruta que entienden tanto Git Bash como los programas nativos de Windows.
ruta_portable() {
  if [[ "$SO" == "windows" ]] && command -v cygpath >/dev/null 2>&1; then
    cygpath -m "$1"
  else
    echo "$1"
  fi
}

VERSION="$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$ORIGEN/.claude-plugin/plugin.json" | head -n 1)"

echo ""
echo -e "${CIAN}${NEGRITA}  DevSkills ${VERSION} - Instalador${NC}"
echo ""
echo -e "${AZUL}ℹ Agentes y skills: $CLAUDE_DIR${NC}"
echo -e "${AZUL}ℹ CLI: $BIN_DIR/devskills${NC}"
echo -e "${AZUL}ℹ Carga útil: $SHARE_DIR${NC}"
echo ""

if [[ -e "$SHARE_DIR" && ! -f "$MARCA" ]]; then
  echo -e "${ROJO}✘ $SHARE_DIR existe y no es una instalación de DevSkills. No lo toco.${NC}" >&2
  exit 1
fi

if [[ -f "$MANIFIESTO" && "$SI" != true ]]; then
  if [[ -t 0 ]]; then
    echo -e "${AMARILLO}⚠ DevSkills ya está instalado.${NC}"
    read -r -p "¿Reinstalar? (s/N): " respuesta
    if [[ "$respuesta" != "s" && "$respuesta" != "S" ]]; then
      echo "Cancelado."
      exit 0
    fi
  else
    echo -e "${AMARILLO}⚠ DevSkills ya está instalado; reinstalando...${NC}"
  fi
fi

# Archivos que ya son nuestros (instalación anterior). Sin arreglos asociativos:
# el bash 3.2 de macOS no los tiene.
es_propio() {
  [[ -f "$MANIFIESTO" ]] && grep -Fxq -- "$(ruta_portable "$1")" "$MANIFIESTO"
}

# Lista de (origen|destino|tipo) a instalar.
PLAN=()
for agente in "$ORIGEN"/agents/*.md; do
  nombre="$(basename "$agente" .md)"
  PLAN+=("$agente|$CLAUDE_DIR/agents/devskills-$nombre.md|agente:$nombre")
done
for dir_skill in "$ORIGEN"/skills/*/; do
  nombre="$(basename "$dir_skill")"
  while IFS= read -r archivo; do
    relativo="${archivo#"$dir_skill"}"
    PLAN+=("$archivo|$CLAUDE_DIR/skills/devskills-$nombre/$relativo|skill:$nombre")
  done < <(find "$dir_skill" -type f | sort)
done
PLAN+=("$ORIGEN/bin/devskills|$BIN_DIR/devskills|cli")

# Choques con archivos ajenos.
CHOQUES=()
for entrada in "${PLAN[@]}"; do
  destino="${entrada#*|}"; destino="${destino%%|*}"
  if [[ -e "$destino" ]] && ! es_propio "$destino"; then
    CHOQUES+=("$destino")
  fi
done
if [[ ${#CHOQUES[@]} -gt 0 && "$FORZAR" != true ]]; then
  echo -e "${AMARILLO}⚠ Estos archivos existen y no los instaló DevSkills:${NC}"
  printf '   %s\n' "${CHOQUES[@]}"
  if [[ -t 0 ]]; then
    read -r -p "¿Sobrescribirlos? (s/N): " respuesta
    if [[ "$respuesta" != "s" && "$respuesta" != "S" ]]; then
      echo "Cancelado: no se instaló nada."
      exit 1
    fi
  else
    echo -e "${ROJO}✘ Cancelado: no se instaló nada. Usa --forzar si de verdad quieres sobrescribirlos.${NC}" >&2
    exit 1
  fi
fi

# El manifiesto anterior se lee ANTES de reemplazar la carga útil (vive dentro de ella): sin esta copia,
# lo que la versión nueva ya no trae se quedaba instalado para siempre.
MANIFIESTO_ANTERIOR=""
if [[ -f "$MANIFIESTO" ]]; then
  MANIFIESTO_ANTERIOR="$(mktemp)"
  cp "$MANIFIESTO" "$MANIFIESTO_ANTERIOR"
  trap 'rm -f "$MANIFIESTO_ANTERIOR"' EXIT
fi

# Carga útil: se reemplaza completa (es nuestra, lo garantiza la marca).
rm -rf "$SHARE_DIR"
mkdir -p "$SHARE_DIR"
for elemento in .claude-plugin agents skills plantillas scripts bin motor LICENSE README.md CHANGELOG.md; do
  if [[ -e "$ORIGEN/$elemento" ]]; then
    cp -R "$ORIGEN/$elemento" "$SHARE_DIR/"
  fi
done
touch "$MARCA"
if [[ -d "$ORIGEN/.git" ]]; then
  echo "$ORIGEN" >"$SHARE_DIR/.origen"
fi
SHARE_PORTABLE="$(ruta_portable "$SHARE_DIR")"
SHARE_PORTABLE_SED="$(escapar_sed "$SHARE_PORTABLE")"
# Para el CLI, la ruta va entre comillas simples (donde todo es literal; la comilla simple se cierra y se
# escapa con `'\''`) dentro de una sustitución de comando: así admite hasta apóstrofos (O'Brien).
COMILLA_SIMPLE="'\\''"
SHARE_DIR_SED="$(escapar_sed "${SHARE_DIR//\'/$COMILLA_SIMPLE}")"

# Adapta el contenido de un agente o una skill instalado fuera del sistema de plugins.
adaptar() {
  local archivo="$1" nombre="$2" dir_skill="${3:-}"
  local expr=(
    -e "s#\${CLAUDE_PLUGIN_ROOT}#$SHARE_PORTABLE_SED#g"
    -e "s#devskills:\([a-z]\)#devskills-\1#g"
    -e "s#^name: $nombre\$#name: devskills-$nombre#"
  )
  if [[ -n "$dir_skill" ]]; then
    expr+=(-e "s#\${CLAUDE_SKILL_DIR}#$SHARE_PORTABLE_SED/skills/$dir_skill#g")
  fi
  sed "${expr[@]}" "$archivo"
}

: >"$MANIFIESTO.nuevo"
for entrada in "${PLAN[@]}"; do
  origen="${entrada%%|*}"
  resto="${entrada#*|}"
  destino="${resto%%|*}"
  tipo="${resto#*|}"
  mkdir -p "$(dirname "$destino")"
  case "$tipo" in
    agente:*)
      adaptar "$origen" "${tipo#agente:}" >"$destino"
      ;;
    skill:*)
      if [[ "$origen" == *.md ]]; then
        adaptar "$origen" "${tipo#skill:}" "${tipo#skill:}" >"$destino"
      else
        cp "$origen" "$destino"
      fi
      ;;
    cli)
      sed -e "s#^DEVSKILLS_HOME=.*#DEVSKILLS_HOME=\"\${DEVSKILLS_HOME:-\$(printf '%s' '$SHARE_DIR_SED')}\"#" \
          -e "s#^VERSION=.*#VERSION=\"\${DEVSKILLS_VERSION:-$VERSION}\"#" "$origen" >"$destino"
      chmod +x "$destino"
      ;;
  esac
  ruta_portable "$destino" >>"$MANIFIESTO.nuevo"
done

# Borra las carpetas que quedaron vacías, subiendo solo hasta la raíz conocida de la skill
# (<...>/skills/devskills-<nombre>): nunca por encima de ella.
limpiar_carpetas() {
  local archivo="$1" base resto raiz dir
  [[ "$archivo" == */skills/devskills-*/* ]] || return 0
  base="${archivo%/skills/devskills-*}"
  resto="${archivo#"$base"/skills/}"
  raiz="$base/skills/${resto%%/*}"
  dir="$(dirname "$archivo")"
  while [[ "$dir" == "$raiz" || "$dir" == "$raiz"/* ]] && rmdir "$dir" 2>/dev/null; do
    dir="$(dirname "$dir")"
  done
}

# Quita lo que la instalación anterior puso y esta ya no trae. Solo toca entradas con aspecto de
# DevSkills (devskills-*, o el CLI): un manifiesto alterado no puede borrar archivos ajenos.
if [[ -n "$MANIFIESTO_ANTERIOR" ]]; then
  while IFS= read -r viejo; do
    [[ -z "$viejo" ]] && continue
    if [[ "$viejo" != *"/devskills-"* && "$(basename "$viejo")" != "devskills" && "$(basename "$viejo")" != "devskills.cmd" ]]; then
      continue
    fi
    if ! grep -Fxq -- "$viejo" "$MANIFIESTO.nuevo"; then
      rm -f "$viejo"
      limpiar_carpetas "$viejo"
    fi
  done <"$MANIFIESTO_ANTERIOR"
  rm -f "$MANIFIESTO_ANTERIOR"
fi
mv "$MANIFIESTO.nuevo" "$MANIFIESTO"

echo -e "${VERDE}✔ DevSkills ${VERSION} instalado ($(wc -l <"$MANIFIESTO" | tr -d ' ') archivos registrados en $MANIFIESTO).${NC}"
echo ""
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo -e "${AMARILLO}⚠ $BIN_DIR no está en tu PATH.${NC} Agrega a tu ~/.bashrc (o ~/.zshrc):"
  echo -e "  ${CIAN}export PATH=\"$BIN_DIR:\$PATH\"${NC}"
  echo ""
fi
echo -e "${NEGRITA}Para empezar:${NC}"
echo "  devskills doctor                       # revisa los requisitos"
echo "  devskills init ~/proyectos/mi-sistema --nombre \"Mi sistema\""
echo "  En Claude Code, los agentes y skills se llaman devskills-<nombre> (por ejemplo, /devskills-ciclo HU-01)."
echo "  Si prefieres el plugin (devskills:<nombre>), usa /plugin marketplace add en lugar de este instalador."
echo ""
