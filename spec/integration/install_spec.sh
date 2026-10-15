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

  Describe 'manifiesto: lo que la versión nueva ya no trae se quita'
    It 'reinstalar con un agente y una skill quitados no deja huérfanos, y desinstalar deja todo limpio'
      crear_origen_falso
      instalar_falso --si >/dev/null
      test -f "$HOME_TEMPORAL/.claude/agents/devskills-b.md"
      test -f "$HOME_TEMPORAL/.claude/skills/devskills-s2/assets/x.txt"
      rm -f "$ORIGEN_FALSO/agents/b.md"
      rm -rf "$ORIGEN_FALSO/skills/s2"
      instalar_falso --si >/dev/null
      The path "$HOME_TEMPORAL/.claude/agents/devskills-a.md" should be file
      The path "$HOME_TEMPORAL/.claude/skills/devskills-s1/SKILL.md" should be file
      The path "$HOME_TEMPORAL/.claude/agents/devskills-b.md" should not be exist
      The path "$HOME_TEMPORAL/.claude/skills/devskills-s2" should not be exist
      The contents of file "$SHARE_TEMPORAL/manifiesto.txt" should not include 'devskills-b'
      The contents of file "$SHARE_TEMPORAL/manifiesto.txt" should not include 'devskills-s2'
    End

    It 'tras quitar elementos, desinstalar no deja ningún archivo huérfano'
      crear_origen_falso
      instalar_falso --si >/dev/null
      rm -f "$ORIGEN_FALSO/agents/b.md"
      rm -rf "$ORIGEN_FALSO/skills/s2"
      instalar_falso --si >/dev/null
      desinstalar >/dev/null
      The value "$(contar_archivos "$HOME_TEMPORAL/.claude")" should eq 0
      The value "$(contar_archivos "$BIN_TEMPORAL")" should eq 0
      The path "$SHARE_TEMPORAL" should not be exist
    End

    # La ruta del usuario contiene "/devskills-": la limpieza de carpetas vacías no puede subir de la raíz de la skill.
    desinstalar_con_ruta_con_prefijo() {
      local original="$HOME_TEMPORAL"
      HOME_TEMPORAL="$original/devskills-casa"
      BIN_TEMPORAL="$HOME_TEMPORAL/bin"
      SHARE_TEMPORAL="$HOME_TEMPORAL/share/devskills"
      mkdir -p "$HOME_TEMPORAL"
      crear_origen_falso
      instalar_falso --si >/dev/null
      desinstalar >/dev/null
      test -d "$HOME_TEMPORAL/.claude/skills" && echo "skills-sigue"
      test -d "$HOME_TEMPORAL/.claude/agents" && echo "agents-sigue"
      test -d "$HOME_TEMPORAL/.claude/skills/devskills-s1" && echo "skill-sigue"
      HOME_TEMPORAL="$original"
    }
    It 'la limpieza de carpetas vacías no sube por encima de la raíz de la skill'
      When call desinstalar_con_ruta_con_prefijo
      The output should include 'skills-sigue'
      The output should include 'agents-sigue'
      The output should not include 'skill-sigue'
    End

    It 'un manifiesto alterado no puede hacer borrar archivos ajenos al desinstalar'
      crear_origen_falso
      instalar_falso --si >/dev/null
      echo "importante" >"$HOME_TEMPORAL/ajeno.txt"
      echo "$HOME_TEMPORAL/ajeno.txt" >>"$SHARE_TEMPORAL/manifiesto.txt"
      desinstalar >/dev/null
      The contents of file "$HOME_TEMPORAL/ajeno.txt" should eq "importante"
    End
  End

  Describe 'rutas con caracteres especiales'
    It 'una ruta con &, # y comilla simple se instala literal en las skills y el CLI'
      crear_origen_falso
      ESPECIAL="$HOME_TEMPORAL/sh&re#c'd"
      instalar_falso_en "$ESPECIAL" --si >/dev/null
      The contents of file "$HOME_TEMPORAL/.claude/skills/devskills-s1/SKILL.md" should include "sh&re#c'd/skills/s1"
      The contents of file "$HOME_TEMPORAL/.claude/skills/devskills-s1/SKILL.md" should include "sh&re#c'd "
      The contents of file "$BIN_TEMPORAL/devskills" should include "sh&re#c'\''d"
    End

    It 'el CLI instalado en esa ruta encuentra sus plantillas y crea un proyecto'
      ESPECIAL="$HOME_TEMPORAL/sh&re#c'd"
      instalar_en "$ESPECIAL" --si >/dev/null
      When call bash "$BIN_TEMPORAL/devskills" init "$HOME_TEMPORAL/proyecto" --nombre "Demo" --slug demo --puerto-base 21000 --sin-git
      The status should be success
      The output should include 'Proyecto creado'
      The path "$HOME_TEMPORAL/proyecto/codigo/manage.py" should be file
    End

    It 'se desinstala sin dejar nada desde esa ruta'
      crear_origen_falso
      ESPECIAL="$HOME_TEMPORAL/sh&re#c'd"
      instalar_falso_en "$ESPECIAL" --si >/dev/null
      desinstalar_de "$ESPECIAL" >/dev/null
      The value "$(contar_archivos "$HOME_TEMPORAL/.claude")" should eq 0
      The path "$ESPECIAL" should not be exist
    End

    It 'rechaza una ruta con $ sin instalar nada'
      When call instalar_en "$HOME_TEMPORAL/sh\$re" --si
      The status should eq 2
      The stderr should include 'no se pueden incrustar'
      The path "$BIN_TEMPORAL/devskills" should not be exist
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
