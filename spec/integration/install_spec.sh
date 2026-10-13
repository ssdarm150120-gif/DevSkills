# shellcheck shell=bash

Describe 'install.sh y uninstall.sh'
  BeforeEach 'preparar_home'
  AfterEach 'limpiar_home'

  Describe 'instalación limpia'
    It 'termina bien y avisa cuántos archivos registró'
      When call instalar --si
      The status should be success
      The output should include 'instalado'
    End

    It 'copia cada agente con el prefijo devskills-'
      instalar --si >/dev/null
      The path "$HOME_TEMPORAL/.claude/agents/devskills-orquestador.md" should be file
      The path "$HOME_TEMPORAL/.claude/agents/devskills-analista-arquitecto.md" should be file
      The path "$HOME_TEMPORAL/.claude/agents/devskills-verificador.md" should be file
      The path "$HOME_TEMPORAL/.claude/agents/devskills-dev-a.md" should be file
      The path "$HOME_TEMPORAL/.claude/agents/devskills-qa.md" should be file
    End

    It 'copia cada skill en su carpeta con prefijo, con sus recursos'
      instalar --si >/dev/null
      The path "$HOME_TEMPORAL/.claude/skills/devskills-ciclo-historia/SKILL.md" should be file
      The path "$HOME_TEMPORAL/.claude/skills/devskills-registrar-avance/assets/plantilla_reporte.md" should be file
      The path "$HOME_TEMPORAL/.claude/skills/devskills-iniciar-proyecto/SKILL.md" should be file
    End

    It 'renombra el agente y sus referencias (devskills:x pasa a devskills-x)'
      instalar --si >/dev/null
      The contents of file "$HOME_TEMPORAL/.claude/agents/devskills-dev-a.md" should include 'name: devskills-dev-a'
      The contents of file "$HOME_TEMPORAL/.claude/agents/devskills-dev-a.md" should include 'devskills-proyecto-contexto'
      The contents of file "$HOME_TEMPORAL/.claude/agents/devskills-dev-a.md" should not include 'devskills:'
    End

    It 'resuelve las variables del plugin a la carpeta instalada'
      instalar --si >/dev/null
      The contents of file "$HOME_TEMPORAL/.claude/skills/devskills-ciclo-historia/SKILL.md" should not include 'CLAUDE_PLUGIN_ROOT'
      The contents of file "$HOME_TEMPORAL/.claude/skills/devskills-iniciar-proyecto/SKILL.md" should not include 'CLAUDE_SKILL_DIR'
      The contents of file "$HOME_TEMPORAL/.claude/skills/devskills-iniciar-proyecto/SKILL.md" should include 'skills/iniciar-proyecto/scripts/crear_proyecto.py'
    End

    It 'instala el CLI ejecutable y la carga útil con las plantillas'
      instalar --si >/dev/null
      The path "$BIN_TEMPORAL/devskills" should be executable
      The path "$SHARE_TEMPORAL/plantillas" should be directory
      The path "$SHARE_TEMPORAL/skills/iniciar-proyecto/scripts/crear_proyecto.py" should be file
      The path "$SHARE_TEMPORAL/manifiesto.txt" should be file
    End

    It 'el CLI instalado apunta a la carga útil instalada'
      instalar --si >/dev/null
      When run bash "$BIN_TEMPORAL/devskills" version
      The status should be success
      The output should eq "devskills $(version_del_plugin)"
    End

    It 'registra en el manifiesto exactamente los archivos que puso fuera de la carga útil'
      instalar --si >/dev/null
      The value "$(lineas_del_manifiesto)" should eq "$(archivos_fuera_de_la_carga)"
    End
  End

  Describe 'idempotencia'
    It 'reinstalar deja el mismo manifiesto y los mismos archivos'
      instalar --si >/dev/null
      antes="$(sort "$SHARE_TEMPORAL/manifiesto.txt")"
      archivos_antes="$(contar_archivos "$HOME_TEMPORAL")"
      instalar --si >/dev/null
      The value "$(sort "$SHARE_TEMPORAL/manifiesto.txt")" should eq "$antes"
      The value "$(contar_archivos "$HOME_TEMPORAL")" should eq "$archivos_antes"
    End

    It 'sin --si y sin terminal reinstala avisando'
      instalar --si >/dev/null
      When call instalar
      The status should be success
      The output should include 'reinstalando'
    End
  End

  Describe 'no pisa archivos del usuario'
    It 'aborta sin instalar nada si un agente ajeno ya existe'
      mkdir -p "$HOME_TEMPORAL/.claude/agents"
      echo "propio" >"$HOME_TEMPORAL/.claude/agents/devskills-qa.md"
      When call instalar --si
      The status should be failure
      The output should include 'no los instaló DevSkills'
      The stderr should include 'Cancelado'
      The contents of file "$HOME_TEMPORAL/.claude/agents/devskills-qa.md" should eq "propio"
      The path "$BIN_TEMPORAL/devskills" should not be exist
    End

    It 'con --forzar lo sobrescribe'
      mkdir -p "$HOME_TEMPORAL/.claude/agents"
      echo "propio" >"$HOME_TEMPORAL/.claude/agents/devskills-qa.md"
      When call instalar --si --forzar
      The status should be success
      The output should include 'instalado'
      The contents of file "$HOME_TEMPORAL/.claude/agents/devskills-qa.md" should include 'name: devskills-qa'
    End

    It 'no toca archivos del usuario que no son de DevSkills'
      mkdir -p "$HOME_TEMPORAL/.claude/agents" "$HOME_TEMPORAL/.claude/skills/otra-skill"
      echo "propio" >"$HOME_TEMPORAL/.claude/agents/otro-agente.md"
      echo "propia" >"$HOME_TEMPORAL/.claude/skills/otra-skill/SKILL.md"
      instalar --si >/dev/null
      desinstalar >/dev/null
      The contents of file "$HOME_TEMPORAL/.claude/agents/otro-agente.md" should eq "propio"
      The contents of file "$HOME_TEMPORAL/.claude/skills/otra-skill/SKILL.md" should eq "propia"
    End

    It 'se niega si la carpeta de la carga útil existe y no es suya'
      mkdir -p "$SHARE_TEMPORAL"
      echo "ajeno" >"$SHARE_TEMPORAL/archivo.txt"
      When call instalar --si
      The status should be failure
      The output should include 'Instalador'
      The stderr should include 'no es una instalación de DevSkills'
      The contents of file "$SHARE_TEMPORAL/archivo.txt" should eq "ajeno"
    End
  End

  Describe 'desinstalación'
    It 'no deja ningún archivo'
      instalar --si >/dev/null
      When call desinstalar
      The status should be success
      The output should include 'Quitados'
      The value "$(contar_archivos "$HOME_TEMPORAL")" should eq 0
      The path "$SHARE_TEMPORAL" should not be exist
      The path "$HOME_TEMPORAL/.claude/skills/devskills-ciclo-historia" should not be exist
    End

    It 'sin instalación previa lo dice y no falla'
      When call desinstalar
      The status should be success
      The output should include 'no está instalado'
    End
  End
End
