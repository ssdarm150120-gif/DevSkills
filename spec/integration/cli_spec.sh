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

    It 'el CLI no ejecuta cadenas con eval'
      When call grep -nE '(^|[^[:alnum:]_])eval[[:space:]]' "$PROJECT_ROOT/bin/devskills"
      The status should be failure
    End

    It 'doctor revisa los requisitos sin fallar'
      When call devskills doctor
      The status should be success
      The output should include 'git'
      The output should include 'Python 3.12'
      The output should include 'gitleaks'
      The output should include 'Obligatorios'
    End

    Describe 'doctor trata Docker como opcional'
      # Un `docker` falso que siempre falla simula una máquina sin Docker (o con Docker Desktop apagado).
      setup_sin_docker() {
        FALSOS="$(mktemp -d)"
        printf '%s
' '#!/usr/bin/env bash' 'exit 1' >"$FALSOS/docker"
        chmod +x "$FALSOS/docker"
      }
      cleanup_sin_docker() { rm -rf "$FALSOS"; }
      BeforeEach 'setup_sin_docker'
      AfterEach 'cleanup_sin_docker'

      doctor_sin_docker() { PATH="$FALSOS:$PATH" bash "$PROJECT_ROOT/bin/devskills" doctor; }

      It 'sin Docker avisa que es opcional, explica qué se pierde y no falla'
        When call doctor_sin_docker
        The status should be success
        The output should include 'Docker (cliente) (opcional)'
        The output should include 'sigue desarrollando y probando sin Docker'
        The output should not include 'Docker (cliente) — falta'
      End

      It 'Docker aparece en la sección de opcionales y no entre los obligatorios'
        When call doctor_sin_docker
        The status should be success
        The output should include 'Opcionales (no bloquean'
        The output should include 'gitleaks'
      End
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

  Describe 'update'
    g() { git -c user.name=Pruebas -c user.email=pruebas@example.invalid -c core.safecrlf=false "$@" >/dev/null 2>&1; }

    # Un remoto local, un clon de origen con un install.sh falso que deja una marca, y un DEVSKILLS_HOME
    # que apunta a ese clon. Después otro clon sube una segunda versión al remoto.
    preparar_update() {
      RAIZ_U="$(mktemp -d)"
      git init -q --bare -b main "$RAIZ_U/remoto.git"
      git init -q -b main "$RAIZ_U/origen"
      g -C "$RAIZ_U/origen" config core.autocrlf false
      printf '%s\n' '#!/usr/bin/env bash' 'echo "instalado v$(cat "$(dirname "$0")/VERSION.txt")" >"$MARCA_UPDATE"' >"$RAIZ_U/origen/install.sh"
      echo 1 >"$RAIZ_U/origen/VERSION.txt"
      g -C "$RAIZ_U/origen" add -A
      g -C "$RAIZ_U/origen" commit -q -m "feat: primera version"
      g -C "$RAIZ_U/origen" remote add origin "$RAIZ_U/remoto.git"
      g -C "$RAIZ_U/origen" push -q -u origin main
      mkdir -p "$RAIZ_U/casa"
      echo "$RAIZ_U/origen" >"$RAIZ_U/casa/.origen"
      MARCA_UPDATE="$RAIZ_U/marca.txt"
      export MARCA_UPDATE RAIZ_U
    }
    publicar_segunda_version() {
      git clone -q "$RAIZ_U/remoto.git" "$RAIZ_U/otro" >/dev/null 2>&1
      echo 2 >"$RAIZ_U/otro/VERSION.txt"
      g -C "$RAIZ_U/otro" commit -q -am "feat: segunda version con cambios visibles"
      g -C "$RAIZ_U/otro" push -q origin main
    }
    limpiar_update() { rm -rf "$RAIZ_U"; }
    actualizar() { DEVSKILLS_HOME="$RAIZ_U/casa" bash "$PROJECT_ROOT/bin/devskills" update "$@" </dev/null; }
    BeforeEach 'preparar_update'
    AfterEach 'limpiar_update'

    It 'sin cambios en el remoto dice que ya tienes la última versión y no reinstala'
      When call actualizar
      The status should be success
      The output should include 'última versión'
      The path "$MARCA_UPDATE" should not be exist
    End

    It 'con cambios y sin terminal muestra qué traería y no aplica nada sin --si'
      publicar_segunda_version
      When call actualizar
      The status should be failure
      The output should include 'segunda version con cambios visibles'
      The output should include 'VERSION.txt'
      The stderr should include '--si'
      The path "$MARCA_UPDATE" should not be exist
      The contents of file "$RAIZ_U/origen/VERSION.txt" should eq '1'
    End

    It 'con --si trae los cambios y reinstala con el código nuevo'
      publicar_segunda_version
      When call actualizar --si
      The status should be success
      The output should include 'segunda version con cambios visibles'
      The contents of file "$MARCA_UPDATE" should eq 'instalado v2'
      The contents of file "$RAIZ_U/origen/VERSION.txt" should eq '2'
    End

    It 'rechaza una opción desconocida'
      When call actualizar --otra
      The status should eq 2
      The stderr should include 'Opción desconocida'
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

    It 'sin --idioma ni --zona deja los valores neutrales es y UTC'
      devskills init "$CARPETA/demo" --nombre "Demo" --slug demo --puerto-base 19100 --sin-git >/dev/null
      When call cat "$CARPETA/demo/codigo/configuracion/localizacion.py"
      The output should include 'IDIOMA_PREDETERMINADO = "es"'
      The output should include 'ZONA_PREDETERMINADA = "UTC"'
    End

    It 'con --idioma y --zona los fija como valores por defecto del proyecto'
      When call devskills init "$CARPETA/demo" --nombre "Demo" --slug demo --puerto-base 19100 --sin-git --idioma pt_BR --zona America/Sao_Paulo
      The status should be success
      The output should include 'idioma: pt-br; zona horaria: America/Sao_Paulo'
      The contents of file "$CARPETA/demo/codigo/configuracion/localizacion.py" should include 'IDIOMA_PREDETERMINADO = "pt-br"'
      The contents of file "$CARPETA/demo/codigo/configuracion/localizacion.py" should include 'ZONA_PREDETERMINADA = "America/Sao_Paulo"'
    End

    It 'rechaza un idioma inválido sin crear nada'
      When call devskills init "$CARPETA/demo" --nombre "Demo" --slug demo --puerto-base 19100 --idioma 'es mx'
      The status should be failure
      The stderr should include 'Idioma inválido'
      The path "$CARPETA/demo/codigo" should not be exist
    End

    It 'rechaza una zona horaria inválida sin crear nada'
      When call devskills init "$CARPETA/demo" --nombre "Demo" --slug demo --puerto-base 19100 --zona 'US/../x"y'
      The status should be failure
      The stderr should include 'Zona horaria inválida'
      The path "$CARPETA/demo/codigo" should not be exist
    End

    It 'el .gitignore del proyecto excluye llaves, certificados privados y archivos de credenciales'
      devskills init "$CARPETA/demo" --nombre "Demo" --slug demo --puerto-base 19100 --sin-git >/dev/null
      git -C "$CARPETA/demo" init -q -b main
      When call git -C "$CARPETA/demo" check-ignore -v tls.key servidor.pem cliente.p12 id_rsa credentials.json service-account-x.json .pgpass
      The status should be success
      The output should include '*.key'
      The output should include '*.pem'
      The output should include '*.p12'
      The output should include 'id_rsa*'
      The output should include 'credentials.json'
    End

    It 'rechaza un nombre con salto de línea (inyectaría líneas en .env.ejemplo)'
      When call devskills init "$CARPETA/demo" --nombre "$(printf 'Demo\nINYECTADO=1')" --slug demo --puerto-base 19100
      The status should be failure
      The stderr should include 'caracteres de control'
      The path "$CARPETA/demo/codigo" should not be exist
    End

    It 'rechaza un autor con salto de línea'
      When call devskills init "$CARPETA/demo" --nombre "Demo" --autor "$(printf 'Ana\nRoot')" --slug demo --puerto-base 19100
      The status should be failure
      The stderr should include 'caracteres de control'
      The path "$CARPETA/demo/codigo" should not be exist
    End

    Describe 'rechaza lo que rompería TOML, JSON, YAML o .env'
      Parameters
        'Demo "x"'
        'Demo \ x'
        'Demo $HOME'
        'Demo {{SLUG}}'
        'Demo {x}'
        'Demo #1'
      End
      It "nombre: $1"
        When call devskills init "$CARPETA/demo" --nombre "$1" --slug demo --puerto-base 19100
        The status should be failure
        The stderr should include 'no puede llevar'
        The path "$CARPETA/demo/codigo" should not be exist
      End
    End

    It 'con acentos, dos puntos, apóstrofo y & genera TOML y JSON válidos'
      devskills init "$CARPETA/demo" --nombre "Ñandú: sistema d'Ana & Co." --autor "María Pérez" --slug demo --puerto-base 19100 --sin-git >/dev/null
      valida() {
        python -c "
import json, sys, tomllib
raiz = sys.argv[1]
nombre = tomllib.load(open(raiz + '/codigo/pyproject.toml', 'rb'))['project']['description']
assert nombre.startswith(\"Ñandú: sistema d'Ana & Co.\"), nombre
datos = json.load(open(raiz + '/documentacion/presentacion/datos_presentacion.json', encoding='utf-8'))
assert datos['proyecto'] == \"Ñandú: sistema d'Ana & Co.\", datos['proyecto']
print('ok')
" "$CARPETA/demo"
      }
      The value "$(valida 2>&1)" should eq 'ok'
    End

    It 'rechaza un rango de puertos que incluye uno reservado'
      When call devskills init "$CARPETA/demo" --slug demo --puerto-base 5400 --puertos-reservados 5432
      The status should be failure
      The stderr should be present
      The path "$CARPETA/demo/codigo" should not be exist
    End
  End
End
