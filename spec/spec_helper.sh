# shellcheck shell=bash

# Ayudas comunes de las pruebas. Compatible con ShellSpec 0.28.0+.

PROJECT_ROOT=""

spec_helper_configure() {
  PROJECT_ROOT="$(cd "$(dirname "$SHELLSPEC_SPECDIR")" && pwd)"
  export PROJECT_ROOT
}

# HOME temporal para instalar sin tocar el del usuario.
preparar_home() {
  HOME_TEMPORAL="$(mktemp -d)"
  BIN_TEMPORAL="$HOME_TEMPORAL/bin"
  SHARE_TEMPORAL="$HOME_TEMPORAL/share/devskills"
  export HOME_TEMPORAL BIN_TEMPORAL SHARE_TEMPORAL
}

limpiar_home() {
  cd / || true
  if [[ -n "${HOME_TEMPORAL:-}" && -d "$HOME_TEMPORAL" ]]; then
    rm -rf "$HOME_TEMPORAL"
  fi
}

instalar() {
  HOME="$HOME_TEMPORAL" DEVSKILLS_BIN_DIR="$BIN_TEMPORAL" DEVSKILLS_SHARE_DIR="$SHARE_TEMPORAL" CLAUDE_CONFIG_DIR="" \
    bash "$PROJECT_ROOT/install.sh" "$@" </dev/null
}

desinstalar() {
  HOME="$HOME_TEMPORAL" DEVSKILLS_SHARE_DIR="$SHARE_TEMPORAL" bash "$PROJECT_ROOT/uninstall.sh" </dev/null
}

contar_archivos() {
  find "$1" -type f 2>/dev/null | wc -l | tr -d ' '
}

lineas_del_manifiesto() {
  wc -l <"$SHARE_TEMPORAL/manifiesto.txt" | tr -d ' '
}

# Archivos instalados fuera de la carga útil: los de ~/.claude más el CLI.
archivos_fuera_de_la_carga() {
  echo $(($(contar_archivos "$HOME_TEMPORAL/.claude") + $(contar_archivos "$BIN_TEMPORAL")))
}

marcadores_sin_sustituir() {
  grep -rlE '\{\{(NOMBRE_PROYECTO|SLUG|SLUG_GUION_BAJO|PUERTO_BASE|PUERTOS_RESERVADOS|FECHA|AUTOR)\}\}' "$1" --exclude-dir=.git 2>/dev/null | wc -l | tr -d ' '
}

version_del_plugin() {
  sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$PROJECT_ROOT/.claude-plugin/plugin.json" | head -n 1
}
