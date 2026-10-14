# shellcheck shell=bash

Describe 'CLI devskills'
  devskills() {
    bash "$PROJECT_ROOT/bin/devskills" "$@"
  }

  Describe 'comandos básicos'
    It 'version muestra la versión del plugin'
      When call devskills version
      The status should be success
      The output should eq "devskills $(version_del_plugin)"
    End

    It 'help lista los subcomandos'
      When call devskills help
      The status should be success
      The output should include 'devskills init'
      The output should include 'devskills doctor'
      The output should include 'devskills update'
    End

    It 'sin argumentos muestra la ayuda'
      When call devskills
      The status should be success
      The output should include 'Uso:'
    End

    It 'rechaza un comando desconocido'
      When call devskills inventado
      The status should eq 2
      The output should include 'Uso:'
      The stderr should include 'Comando desconocido'
    End

    It 'doctor revisa los requisitos sin fallar'
      When call devskills doctor
      The status should be success
      The output should include 'git'
      The output should include 'Python 3.12'
      The output should include 'gitleaks'
    End

    Describe 'doctor y mermaid-cli en la carpeta fija ~/.devskills/doc'
      setup_mmdc() {
        CASA_FALSA="$(mktemp -d)"
        mkdir -p "$CASA_FALSA/.devskills/doc/node_modules/.bin"
        : > "$CASA_FALSA/.devskills/doc/node_modules/.bin/mmdc"
      }
      cleanup_mmdc() { rm -rf "$CASA_FALSA"; }
      BeforeEach 'setup_mmdc'
      AfterEach 'cleanup_mmdc'

      doctor_con_casa_falsa() { HOME="$CASA_FALSA" bash "$PROJECT_ROOT/bin/devskills" doctor; }

      It 'detecta mermaid-cli instalado en ~/.devskills/doc'
        When call doctor_con_casa_falsa
        The status should be success
        The output should include '✔ mermaid-cli'
      End
    End
  End

  Describe 'init'
    setup() {
      CARPETA="$(mktemp -d)"
      export CARPETA
    }
    cleanup() {
      cd / || true
      rm -rf "$CARPETA"
    }
    BeforeEach 'setup'
    AfterEach 'cleanup'

    It 'exige la ruta'
      When call devskills init
      The status should eq 2
      The stderr should include 'Falta la ruta'
    End

    It 'genera la estructura del proyecto con su primer commit'
      When call devskills init "$CARPETA/demo" --nombre "Sistema Demo" --slug demo --puerto-base 19100 --autor "Pruebas"
      The status should be success
      The output should include 'Siguientes pasos'
      The path "$CARPETA/demo/AGENTS.md" should be file
      The path "$CARPETA/demo/.gitignore" should be file
      The path "$CARPETA/demo/.github/workflows/ci.yml" should be file
      The path "$CARPETA/demo/codigo/manage.py" should be file
      The path "$CARPETA/demo/codigo/configuracion/modulos.py" should be file
      The path "$CARPETA/demo/codigo/despliegue/docker-compose.yml" should be file
      The path "$CARPETA/demo/documentacion/SRS.md" should be file
      The path "$CARPETA/demo/documentacion/DISENO.md" should be file
      The path "$CARPETA/demo/documentacion/PLAN.md" should be file
      The path "$CARPETA/demo/documentacion/CONTEXTO.md" should be file
      The path "$CARPETA/demo/documentacion/analisis/plan_sprints.py" should be file
      The path "$CARPETA/demo/documentacion/analisis/trazabilidad.py" should be file
      The path "$CARPETA/demo/documentacion/avance/estado_backlog.json" should be file
      The path "$CARPETA/demo/.git" should be directory
    End

    It 'sustituye los marcadores con los datos del proyecto'
      devskills init "$CARPETA/demo" --nombre "Sistema Demo" --slug demo --puerto-base 19100 --autor "Pruebas" >/dev/null
      The contents of file "$CARPETA/demo/documentacion/SRS.md" should include 'Sistema Demo'
      The contents of file "$CARPETA/demo/documentacion/CONTEXTO.md" should include 'demo'
      The value "$(marcadores_sin_sustituir "$CARPETA/demo")" should eq 0
    End

    It 'se niega a escribir en una carpeta que no está vacía'
      mkdir -p "$CARPETA/ocupada"
      echo "algo" >"$CARPETA/ocupada/archivo.txt"
      When call devskills init "$CARPETA/ocupada" --slug demo
      The status should be failure
      The stderr should be present
      The contents of file "$CARPETA/ocupada/archivo.txt" should eq "algo"
    End

    It 'rechaza un rango de puertos que incluye uno reservado'
      When call devskills init "$CARPETA/demo" --slug demo --puerto-base 5400 --puertos-reservados 5432
      The status should be failure
      The stderr should be present
      The path "$CARPETA/demo/codigo" should not be exist
    End
  End
End
