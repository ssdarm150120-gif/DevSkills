# shellcheck shell=bash

# Pruebas de install.ps1 y uninstall.ps1. Solo corren donde hay PowerShell de Windows (powershell.exe),
# por ejemplo Git Bash en Windows y el job de Windows del CI; en el resto se omiten.

no_hay_powershell() { ! command -v powershell.exe >/dev/null 2>&1; }

Describe 'install.ps1 y uninstall.ps1' # (solo con PowerShell)
  Skip if 'no hay powershell.exe' no_hay_powershell

  BeforeEach 'preparar_home'
  AfterEach 'limpiar_home'

  win() { cygpath -w "$1"; }

  # $1 = script (install.ps1 | uninstall.ps1) en el origen $2; el resto, argumentos.
  ps1() {
    local script="$1" origen="$2" share="$3"
    shift 3
    HOME="$(win "$HOME_TEMPORAL")" USERPROFILE="$(win "$HOME_TEMPORAL")" \
      DEVSKILLS_BIN_DIR="$(win "$BIN_TEMPORAL")" DEVSKILLS_SHARE_DIR="$(win "$share")" \
      CLAUDE_CONFIG_DIR="$(win "$HOME_TEMPORAL/.claude")" \
      powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(win "$origen/$script")" "$@" </dev/null
  }

  Describe 'manifiesto: lo que la versión nueva ya no trae se quita'
    It 'reinstalar con un agente y una skill quitados no deja huérfanos y desinstalar deja todo limpio'
      crear_origen_falso
      cp "$PROJECT_ROOT/install.ps1" "$PROJECT_ROOT/uninstall.ps1" "$ORIGEN_FALSO/"
      ps1 install.ps1 "$ORIGEN_FALSO" "$SHARE_TEMPORAL" -Si >/dev/null
      test -f "$HOME_TEMPORAL/.claude/agents/devskills-b.md"
      rm -f "$ORIGEN_FALSO/agents/b.md"
      rm -rf "$ORIGEN_FALSO/skills/s2"
      ps1 install.ps1 "$ORIGEN_FALSO" "$SHARE_TEMPORAL" -Si >/dev/null
      The path "$HOME_TEMPORAL/.claude/agents/devskills-a.md" should be file
      The path "$HOME_TEMPORAL/.claude/agents/devskills-b.md" should not be exist
      The path "$HOME_TEMPORAL/.claude/skills/devskills-s2" should not be exist
      ps1 uninstall.ps1 "$ORIGEN_FALSO" "$SHARE_TEMPORAL" >/dev/null
      The value "$(contar_archivos "$HOME_TEMPORAL/.claude")" should eq 0
      The value "$(contar_archivos "$BIN_TEMPORAL")" should eq 0
    End
  End

  Describe 'rutas con caracteres especiales'
    It 'una ruta con &, # y comilla simple se instala literal en las skills y el CLI'
      crear_origen_falso
      cp "$PROJECT_ROOT/install.ps1" "$ORIGEN_FALSO/"
      ESPECIAL="$HOME_TEMPORAL/sh&re#c'd"
      ps1 install.ps1 "$ORIGEN_FALSO" "$ESPECIAL" -Si >/dev/null
      The contents of file "$HOME_TEMPORAL/.claude/skills/devskills-s1/SKILL.md" should include "sh&re#c'd/skills/s1"
      The contents of file "$BIN_TEMPORAL/devskills" should include "sh&re#c'\''d"
    End

    It 'el CLI instalado en esa ruta arranca'
      crear_origen_falso
      cp "$PROJECT_ROOT/install.ps1" "$ORIGEN_FALSO/"
      ESPECIAL="$HOME_TEMPORAL/sh&re#c'd"
      ps1 install.ps1 "$ORIGEN_FALSO" "$ESPECIAL" -Si >/dev/null
      When run bash "$BIN_TEMPORAL/devskills" version
      The status should be success
      The output should eq 'devskills 9.9.9'
    End

    It 'rechaza una ruta con $ sin instalar nada'
      crear_origen_falso
      cp "$PROJECT_ROOT/install.ps1" "$ORIGEN_FALSO/"
      When call ps1 install.ps1 "$ORIGEN_FALSO" "$HOME_TEMPORAL/sh\$re" -Si
      The status should eq 2
      The stderr should include 'no se pueden incrustar'
      The path "$BIN_TEMPORAL/devskills" should not be exist
    End
  End
End
