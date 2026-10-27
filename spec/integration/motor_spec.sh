# shellcheck shell=bash

Describe 'CLI devskills: motor gráfico'
  # El estado va a una carpeta temporal (DEVSKILLS_DATOS): nunca se toca ~/.devskills.
  preparar_datos() {
    DATOS="$(mktemp -d)"
    PREVIA="$(mktemp -d)"
    export DATOS PREVIA
  }
  limpiar_datos() { rm -rf "$DATOS" "$PREVIA"; }
  devskills() { DEVSKILLS_DATOS="$DATOS" bash "$PROJECT_ROOT/bin/devskills" "$@" </dev/null; }
  BeforeEach 'preparar_datos'
  AfterEach 'limpiar_datos'

  Describe 'ayuda'
    It 'help lista panel, servicios, orquestador y motor'
      When call devskills help
      The status should be success
      The output should include 'devskills panel'
      The output should include 'devskills servicios'
      The output should include 'devskills orquestador'
      The output should include 'devskills motor migrar --desde'
      The output should include 'OPCIONAL'
    End
  End

  Describe 'devskills panel'
    It 'rechaza un puerto inválido'
      When call devskills panel --puerto abc
      The status should eq 2
      The stderr should include '--puerto'
    End

    It 'rechaza un puerto fuera de rango'
      When call devskills panel iniciar --puerto 80
      The status should eq 2
      The stderr should include '--puerto'
    End

    It 'rechaza una opción desconocida'
      When call devskills panel --inventada
      The status should eq 2
      The stderr should include 'Opción desconocida'
    End

    It 'estado informa que el panel está detenido'
      When call devskills panel estado --puerto 18971
      The status should be success
      The output should include 'detenido'
      The output should include 'Datos:'
    End
  End

  Describe 'devskills servicios'
    It 'exige la acción'
      When call devskills servicios
      The status should eq 2
      The stderr should include 'Falta la acción'
    End

    It 'levantar exige el objetivo'
      When call devskills servicios levantar
      The status should eq 2
      The stderr should include 'Falta el objetivo'
    End

    It 'rechaza una opción desconocida'
      When call devskills servicios listar --inventada
      The status should eq 2
      The stderr should include 'Opción desconocida'
    End

    It 'sin registro avisa cómo crearlo'
      When call devskills servicios listar
      The status should eq 1
      The stderr should include 'devskills motor iniciar'
    End

    Describe 'con el registro de ejemplo'
      crear_registro() { devskills motor iniciar >/dev/null; }
      BeforeEach 'crear_registro'

      It 'listar muestra los servicios del ejemplo'
        When call devskills servicios listar
        The status should be success
        The output should include 'ejemplo-api'
        The output should include 'ejemplo-web'
      End

      It 'levantar --simular no ejecuta nada y muestra el comando'
        When call devskills servicios levantar ejemplo-api --simular
        The status should be success
        The output should include 'Simulación'
        The output should include '-m uvicorn'
      End

      It 'apagar --simular muestra qué apagaría'
        When call devskills servicios apagar ejemplo --simular
        The status should be success
        The output should include 'Simulación: apagaría ejemplo-api'
        The output should include 'Simulación: apagaría ejemplo-web'
      End

      It 'rechaza un objetivo que no está en el registro'
        When call devskills servicios levantar inventado --simular
        The status should eq 2
        The stderr should include "No existe 'inventado'"
      End

      It '--simular no crea logs ni pids'
        sin_rastros() {
          devskills servicios levantar ejemplo-api --simular >/dev/null
          test ! -e "$DATOS/servicios"
        }
        When call sin_rastros
        The status should be success
      End
    End
  End

  Describe 'devskills orquestador (opcional)'
    It 'estado dice que no está instalado y que es opcional'
      When call devskills orquestador estado
      The status should be success
      The output should include 'no instalado'
      The output should include 'opcional'
    End

    It 'iniciar sin instalar falla y explica cómo instalarlo'
      When call devskills orquestador iniciar
      The status should eq 1
      The output should include 'devskills orquestador instalar'
    End

    It 'rechaza una acción desconocida'
      When call devskills orquestador inventado
      The status should eq 2
      The stderr should include 'Argumento de más'
    End
  End

  Describe 'devskills motor'
    It 'exige una acción'
      When call devskills motor
      The status should eq 2
      The stderr should include 'Falta la acción'
    End

    It 'iniciar crea el registro desde la plantilla'
      When call devskills motor iniciar
      The status should be success
      The output should include 'Creé'
      The output should include 'detección automática'
      The path "$DATOS/proyectos.json" should be file
    End

    It 'iniciar no pisa un registro existente'
      existente() {
        printf '%s' '{"proyectos": []}' >"$DATOS/proyectos.json"
        devskills motor iniciar
      }
      When call existente
      The status should be success
      The output should include 'no lo toqué'
      The contents of file "$DATOS/proyectos.json" should eq '{"proyectos": []}'
    End

    It 'migrar exige --desde'
      When call devskills motor migrar
      The status should eq 2
      The stderr should include '--desde'
    End

    It '--forzar solo aplica a migrar'
      When call devskills motor iniciar --forzar
      The status should eq 2
      The stderr should include '--forzar'
    End

    Describe 'enganchar'
      # CLAUDE_CONFIG_DIR apunta a una carpeta temporal: nunca se toca el settings.json real.
      enganchar() { CLAUDE_CONFIG_DIR="$DATOS/claude" devskills motor enganchar "$@"; }
      It 'rechaza las opciones de enganchar en otras acciones'
        When call devskills motor iniciar --quitar
        The status should eq 2
        The stderr should include 'solo aplican a'
      End

      It 'sin terminal exige --si y no cambia nada'
        preparar() { mkdir -p "$DATOS/claude"; printf '%s' '{"theme":"dark"}' >"$DATOS/claude/settings.json"; }
        BeforeCall 'preparar'
        When call enganchar
        The status should eq 1
        The stdout should include 'statusLine'
        The stderr should include '--si'
        The contents of file "$DATOS/claude/settings.json" should eq '{"theme":"dark"}'
      End

      It 'con --si escribe la status line con la ruta de este equipo, respalda y es idempotente'
        flujo() {
          mkdir -p "$DATOS/claude"
          printf '%s' '{"theme":"dark"}' >"$DATOS/claude/settings.json"
          enganchar --si >/dev/null || return 1
          grep -q 'statusline_limites.py' "$DATOS/claude/settings.json" || return 1
          grep -q '"theme": "dark"' "$DATOS/claude/settings.json" || return 1
          [[ "$(find "$DATOS/claude" -name 'settings.json.bak-*' | wc -l | tr -d ' ')" == "1" ]] || return 1
          enganchar --si
        }
        When call flujo
        The status should be success
        The output should include 'Sin cambios'
      End

      It '--quitar deshace lo que puso'
        quitar() {
          enganchar --si >/dev/null || return 1
          enganchar --si --quitar >/dev/null || return 1
          ! grep -q 'statusLine' "$DATOS/claude/settings.json"
        }
        When call quitar
        The status should be success
      End
    End

    Describe 'migrar'
      crear_previa() {
        mkdir -p "$PREVIA/panel/estado" "$PREVIA/orquestador/historial"
        printf '%s' '{"proyectos": []}' >"$PREVIA/proyectos.json"
        printf '%s' '{"acento":"#ffffff"}' >"$PREVIA/panel/preferencias.json"
        printf '%s' '[]' >"$PREVIA/panel/estado/avisos.json"
        printf '%s' '{}' >"$PREVIA/orquestador/historial/a.json"
        printf '%s' 'SECRETO' >"$PREVIA/panel/.token"
        printf '%s' 'SECRETO' >"$PREVIA/orquestador/.token"
      }
      BeforeEach 'crear_previa'

      It 'copia los datos, no los tokens, y no toca el origen'
        migrar_y_revisar() {
          devskills motor migrar --desde "$PREVIA" >/dev/null || return 1
          test -f "$DATOS/proyectos.json" && test -f "$DATOS/preferencias.json" \
            && test -f "$DATOS/panel/estado/avisos.json" && test -f "$DATOS/orquestador/historial/a.json" \
            && test ! -e "$DATOS/panel/.token" && test ! -e "$DATOS/orquestador/.token" \
            && test -f "$PREVIA/proyectos.json" && test -f "$PREVIA/panel/.token"
        }
        When call migrar_y_revisar
        The status should be success
      End

      It 'no sobrescribe sin --forzar y sí con --forzar'
        sobrescribir() {
          printf '%s' 'MIO' >"$DATOS/proyectos.json"
          devskills motor migrar --desde "$PREVIA" >/dev/null
          [[ "$(cat "$DATOS/proyectos.json")" == "MIO" ]] || return 1
          devskills motor migrar --desde "$PREVIA" --forzar >/dev/null
          [[ "$(cat "$DATOS/proyectos.json")" == '{"proyectos": []}' ]]
        }
        When call sobrescribir
        The status should be success
      End

      It 'falla con una carpeta de origen inexistente'
        When call devskills motor migrar --desde "$PREVIA/no-existe"
        The status should be failure
        The stderr should include 'No existe la carpeta de origen'
      End
    End
  End

  Describe 'doctor'
    It 'incluye el motor gráfico entre los opcionales'
      When call devskills doctor
      The status should be success
      The output should include 'Motor gráfico'
    End
  End
End
