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

# Instala en una carpeta de carga útil distinta (para rutas con caracteres especiales).
instalar_en() {
  local share="$1"
  shift
  HOME="$HOME_TEMPORAL" DEVSKILLS_BIN_DIR="$BIN_TEMPORAL" DEVSKILLS_SHARE_DIR="$share" CLAUDE_CONFIG_DIR="" \
    bash "$PROJECT_ROOT/install.sh" "$@" </dev/null
}

desinstalar_de() {
  HOME="$HOME_TEMPORAL" DEVSKILLS_SHARE_DIR="$1" bash "$PROJECT_ROOT/uninstall.sh" </dev/null
}

# Origen mínimo y falso (2 agentes, 2 skills) para probar reinstalaciones con elementos quitados.
crear_origen_falso() {
  ORIGEN_FALSO="$HOME_TEMPORAL/origen"
  mkdir -p "$ORIGEN_FALSO/.claude-plugin" "$ORIGEN_FALSO/agents" "$ORIGEN_FALSO/skills/s1" "$ORIGEN_FALSO/skills/s2/assets" "$ORIGEN_FALSO/bin"
  cp "$PROJECT_ROOT/install.sh" "$ORIGEN_FALSO/install.sh"
  cp "$PROJECT_ROOT/bin/devskills" "$ORIGEN_FALSO/bin/devskills"
  echo '{"version": "9.9.9"}' >"$ORIGEN_FALSO/.claude-plugin/plugin.json"
  printf '%s\n' '---' 'name: a' '---' 'Agente a' >"$ORIGEN_FALSO/agents/a.md"
  printf '%s\n' '---' 'name: b' '---' 'Agente b' >"$ORIGEN_FALSO/agents/b.md"
  # shellcheck disable=SC2016  # ${...} son marcadores literales que el instalador sustituye
  printf '%s\n' '---' 'name: s1' '---' 'Raiz: ${CLAUDE_PLUGIN_ROOT} Skill: ${CLAUDE_SKILL_DIR}' >"$ORIGEN_FALSO/skills/s1/SKILL.md"
  printf '%s\n' '---' 'name: s2' '---' 'Skill dos' >"$ORIGEN_FALSO/skills/s2/SKILL.md"
  echo "recurso" >"$ORIGEN_FALSO/skills/s2/assets/x.txt"
  export ORIGEN_FALSO
}

instalar_falso_en() {
  local share="$1"
  shift
  HOME="$HOME_TEMPORAL" DEVSKILLS_BIN_DIR="$BIN_TEMPORAL" DEVSKILLS_SHARE_DIR="$share" CLAUDE_CONFIG_DIR="" \
    bash "$ORIGEN_FALSO/install.sh" "$@" </dev/null
}

instalar_falso() {
  HOME="$HOME_TEMPORAL" DEVSKILLS_BIN_DIR="$BIN_TEMPORAL" DEVSKILLS_SHARE_DIR="$SHARE_TEMPORAL" CLAUDE_CONFIG_DIR="" \
    bash "$ORIGEN_FALSO/install.sh" "$@" </dev/null
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
