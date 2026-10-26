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

    Describe 'doctor explica cómo instalar semgrep sin que lo instale un agente'
      setup_sin_semgrep() {
        FALSOS="$(mktemp -d)"
        CASA_SIN="$(mktemp -d)"
        printf '%s\n' '#!/usr/bin/env bash' 'exit 1' >"$FALSOS/docker"
        printf '%s\n' '#!/usr/bin/env bash' 'exit 1' >"$FALSOS/wsl"
        chmod +x "$FALSOS/docker" "$FALSOS/wsl"
      }
      cleanup_sin_semgrep() { rm -rf "$FALSOS" "$CASA_SIN"; }
      BeforeEach 'setup_sin_semgrep'
      AfterEach 'cleanup_sin_semgrep'

      doctor_sin_semgrep() { HOME="$CASA_SIN" PATH="$FALSOS:$PATH" bash "$PROJECT_ROOT/bin/devskills" doctor; }

      It 'da el comando con la versión del CI de la plantilla y avisa que los agentes no instalan'
        When call doctor_sin_semgrep
        The status should be success
        The output should include 'semgrep (análisis estático local) (opcional)'
        The output should include "semgrep==$(sed -n 's/.*semgrep==\([0-9][0-9.]*\).*/\1/p' "$PROJECT_ROOT/plantillas/raiz/.github/workflows/ci.yml" | head -n 1)"
        The output should include 'python3 -m venv ~/semgrep'
        The output should include 'los agentes del equipo no instalan software'
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

    Describe 'doctor trata Graphify como opcional'
      # Un `graphify` falso que siempre falla simula una máquina sin Graphify.
      setup_sin_graphify() {
        FALSOS="$(mktemp -d)"
        PROYECTO_G="$(mktemp -d)"
        printf '%s\n' '#!/usr/bin/env bash' 'exit 1' >"$FALSOS/graphify"
        chmod +x "$FALSOS/graphify"
      }
      cleanup_sin_graphify() {
        cd / || true
        rm -rf "$FALSOS" "$PROYECTO_G"
      }
      BeforeEach 'setup_sin_graphify'
      AfterEach 'cleanup_sin_graphify'

      doctor_sin_graphify() { PATH="$FALSOS:$PATH" bash "$PROJECT_ROOT/bin/devskills" doctor; }

      It 'sin Graphify avisa que es opcional, dice cómo instalarlo y no falla'
        When call doctor_sin_graphify
        The status should be success
        The output should include 'Graphify (grafo de conocimiento) (opcional)'
        The output should include 'uv tool install graphifyy'
        The output should include 'el método sigue funcionando igual'
        The output should not include 'Merge driver de Graphify'
      End

      It 'dentro de un proyecto sin el merge driver dice cómo configurarlo'
        doctor_en_proyecto() {
          mkdir -p "$PROYECTO_G/documentacion" && : >"$PROYECTO_G/documentacion/CONTEXTO.md"
          git -C "$PROYECTO_G" init -q
          cd "$PROYECTO_G" && doctor_sin_graphify
        }
        When call doctor_en_proyecto
        The status should be success
        The output should include 'Merge driver de Graphify en este proyecto (opcional)'
        The output should include 'graphify merge-driver %O %A %B'
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

  Describe 'sync-scripts'
    setup_sync() {
      CARPETA="$(mktemp -d)"
      export CARPETA
      bash "$PROJECT_ROOT/bin/devskills" init "$CARPETA/demo" --nombre "Demo" --slug demo --puerto-base 19100 --sin-git >/dev/null 2>&1
      ANALISIS="$CARPETA/demo/documentacion/analisis"
      export ANALISIS
    }
    cleanup_sync() {
      cd / || true
      rm -rf "$CARPETA"
    }
    BeforeEach 'setup_sync'
    AfterEach 'cleanup_sync'

    sincronizar() { bash "$PROJECT_ROOT/bin/devskills" sync-scripts "$@" </dev/null; }
    # Plantillas falsas (con marcadores) para probar la sustitución sin tocar las reales.
    sincronizar_falso() {
      DEVSKILLS_HOME="$CARPETA/falso" bash "$PROJECT_ROOT/bin/devskills" sync-scripts "$@" </dev/null
    }
    preparar_falso() {
      mkdir -p "$CARPETA/falso/plantillas/analisis"
      printf '%s\n' 'SLUG = "{{SLUG}}"' 'NOMBRE = "{{NOMBRE_PROYECTO}}"' >"$CARPETA/falso/plantillas/analisis/con_marcador.py"
      printf '%s\n' 'FECHA = "{{FECHA}}"' >"$CARPETA/falso/plantillas/analisis/con_fecha.py"
      printf '%s\n' '<html>plantilla</html>' >"$CARPETA/falso/plantillas/analisis/plan_sprints_plantilla.html"
      printf '%s\n' 'SLUG = "demo"' 'NOMBRE = "Demo"' >"$ANALISIS/con_marcador.py"
      printf '%s\n' '<html>plantilla</html>' >"$ANALISIS/plan_sprints_plantilla.html"
    }

    It 'sin cambios dice que los scripts están al día y no copia nada'
      When call sincronizar "$CARPETA/demo"
      The status should be success
      The output should include 'ya están al día'
    End

    It 'con cambios pero sin --si (y sin terminal) lista, muestra el diff --stat y no copia'
      echo '# cambio local' >>"$ANALISIS/plan_sprints.py"
      rm "$ANALISIS/porcentaje.py"
      When call sincronizar "$CARPETA/demo"
      The status should be failure
      The output should include 'cambiado  plan_sprints.py'
      The output should include 'nuevo     porcentaje.py'
      The output should include '1 file changed'
      The stderr should include '--si'
      The contents of file "$ANALISIS/plan_sprints.py" should include '# cambio local'
      The path "$ANALISIS/porcentaje.py" should not be exist
    End

    It 'con --si copia solo los scripts y no toca codigo/, los .md ni los JSON'
      echo '# cambio local' >>"$ANALISIS/plan_sprints.py"
      rm "$ANALISIS/porcentaje.py"
      echo 'versión del proyecto' >>"$CARPETA/demo/documentacion/SRS.md"
      echo '{"propio": true}' >"$ANALISIS/plan_entregas.json"
      echo '# propio' >>"$CARPETA/demo/codigo/manage.py"
      When call sincronizar "$CARPETA/demo" --si
      The status should be success
      The output should include 'Copiado plan_sprints.py'
      The output should include 'Copiado porcentaje.py'
      The contents of file "$ANALISIS/plan_sprints.py" should not include '# cambio local'
      The path "$ANALISIS/porcentaje.py" should be file
      The contents of file "$CARPETA/demo/documentacion/SRS.md" should include 'versión del proyecto'
      The contents of file "$ANALISIS/plan_entregas.json" should eq '{"propio": true}'
      The contents of file "$CARPETA/demo/codigo/manage.py" should include '# propio'
    End

    It 'no copia la plantilla HTML personalizada: la compara y avisa'
      echo '<!-- mi tablero -->' >>"$ANALISIS/plan_sprints_plantilla.html"
      When call sincronizar "$CARPETA/demo"
      The status should be success
      The output should include 'plan_sprints_plantilla.html'
      The output should include 'difiere'
      The output should include 'git diff --no-index'
      The contents of file "$ANALISIS/plan_sprints_plantilla.html" should include '<!-- mi tablero -->'
    End

    It 'sin ruta usa la carpeta actual'
      sincronizar_aqui() { (cd "$CARPETA/demo" && bash "$PROJECT_ROOT/bin/devskills" sync-scripts </dev/null); }
      When call sincronizar_aqui
      The status should be success
      The output should include 'ya están al día'
    End

    It 'una ruta que no es un proyecto DevSkills falla sin tocar nada'
      mkdir -p "$CARPETA/otro/documentacion/analisis"
      echo 'x = 1' >"$CARPETA/otro/documentacion/analisis/plan_sprints.py"
      When call sincronizar "$CARPETA/otro" --si
      The status should be failure
      The stderr should include 'no es un proyecto DevSkills'
      The contents of file "$CARPETA/otro/documentacion/analisis/plan_sprints.py" should eq 'x = 1'
    End

    It 'rechaza una opción desconocida'
      When call sincronizar --otra
      The status should eq 2
      The stderr should include 'Opción desconocida'
    End

    It 'sustituye los marcadores con los datos del proyecto antes de comparar'
      preparar_falso
      When call sincronizar_falso "$CARPETA/demo"
      The status should be success
      The output should not include 'cambiado'
      The output should include 'Scripts omitidos'
      The output should include '{{FECHA}}'
      The output should include 'ya están al día'
    End

    It 'un script con marcadores que cambió se copia ya sustituido, y el que no se puede resolver se omite'
      preparar_falso
      printf '%s\n' 'SLUG = "otro"' 'NOMBRE = "Demo"' >"$ANALISIS/con_marcador.py"
      When call sincronizar_falso "$CARPETA/demo" --si
      The status should be success
      The output should include 'Copiado con_marcador.py'
      The output should include 'con_fecha.py'
      The contents of file "$ANALISIS/con_marcador.py" should include 'SLUG = "demo"'
      The path "$ANALISIS/con_fecha.py" should not be exist
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

    It 'sin --correo avisa qué correo quedó en el primer commit y cómo cambiarlo antes de publicar'
      When call devskills init "$CARPETA/demo" --nombre "Demo" --slug demo --puerto-base 19100
      The status should be success
      The output should include 'Aviso: el primer commit quedó con el correo'
      The output should include "$(git config --global user.email)"
      The output should include 'users.noreply.github.com'
      The output should include 'git config user.email'
      The output should include '--correo'
    End

    It 'con --sin-git no avisa de ningún correo'
      When call devskills init "$CARPETA/demo" --nombre "Demo" --slug demo --puerto-base 19100 --sin-git
      The status should be success
      The output should not include 'Aviso:'
    End

    # Corre init con --correo y muestra con qué correo quedó el primer commit y el user.email local.
    init_con_correo() {
      devskills init "$CARPETA/demo" --nombre "Demo" --slug demo --puerto-base 19100 --correo "$1" || return 1
      echo "commit: $(git -C "$CARPETA/demo" log -1 --format=%ae)"
      echo "local: $(git -C "$CARPETA/demo" config --local user.email)"
    }

    It 'con --correo fija user.email local antes del primer commit y no avisa'
      When call init_con_correo '12345+ana@users.noreply.github.com'
      The status should be success
      The output should include 'correo del autor (user.email local): 12345+ana@users.noreply.github.com'
      The output should include 'commit: 12345+ana@users.noreply.github.com'
      The output should include 'local: 12345+ana@users.noreply.github.com'
      The output should not include 'Aviso:'
    End

    Describe 'rechaza un correo inválido sin crear nada'
      Parameters
        'sin-arroba' 'Correo inválido'
        'ana@sin-punto' 'Correo inválido'
        'ana @x.com' 'Correo inválido'
        '-ana@x.com' 'Correo inválido'
        'ana@x.com#' 'no puede llevar'
      End
      It "correo: $1"
        When call devskills init "$CARPETA/demo" --nombre "Demo" --slug demo --puerto-base 19100 --correo "$1"
        The status should be failure
        The stderr should include "$2"
        The path "$CARPETA/demo/codigo" should not be exist
      End
    End

    It 'rechaza un correo con salto de línea'
      When call devskills init "$CARPETA/demo" --nombre "Demo" --slug demo --puerto-base 19100 --correo "$(printf 'a@x.com\nb@x.com')"
      The status should be failure
      The stderr should include 'caracteres de control'
      The path "$CARPETA/demo/codigo" should not be exist
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

    It 'crea CLAUDE.md que importa AGENTS.md y fija el idioma del proyecto desde --idioma'
      When call devskills init "$CARPETA/demo" --nombre "Demo" --slug demo --puerto-base 19100 --sin-git
      The status should be success
      The output should include 'Siguientes pasos'
      The contents of file "$CARPETA/demo/CLAUDE.md" should start with '@AGENTS.md'
      The contents of file "$CARPETA/demo/CLAUDE.md" should include 'prevalece sobre el estilo personal del usuario'
      The contents of file "$CARPETA/demo/CLAUDE.md" should include 'Español de México con tuteo'
      The contents of file "$CARPETA/demo/documentacion/CONTEXTO.md" should include 'Español de México con tuteo (código `es`'
    End

    It 'el idioma de CLAUDE.md, de AGENTS.md y de CONTEXTO.md sale de --idioma'
      When call devskills init "$CARPETA/demo" --nombre "Demo" --slug demo --puerto-base 19100 --sin-git --idioma en
      The status should be success
      The output should include 'idioma: en'
      The contents of file "$CARPETA/demo/CLAUDE.md" should include 'English; código `en`'
      The contents of file "$CARPETA/demo/AGENTS.md" should include 'English'
      The contents of file "$CARPETA/demo/documentacion/CONTEXTO.md" should include 'English (código `en`'
    End

    It 'un archivo en .devskills/ no aparece en git status ni entra con el comando del punto de control'
      punto_de_control() {
        devskills init "$CARPETA/demo" --nombre "Demo" --slug demo --puerto-base 19100 --correo 'ana@example.invalid' >/dev/null
        mkdir -p "$CARPETA/demo/.devskills"
        echo 'borrador' >"$CARPETA/demo/.devskills/lecciones.md"
        echo 'pendiente' >"$CARPETA/demo/.devskills/engram_pendiente.md"
        echo "estado=[$(git -C "$CARPETA/demo" status --porcelain)]"
        echo "ignorado=$(git -C "$CARPETA/demo" check-ignore .devskills/lecciones.md)"
        echo 'reporte' >"$CARPETA/demo/documentacion/avance/reporte.md"
        git -C "$CARPETA/demo" add -A -- codigo .github documentacion/avance
        echo "preparado=[$(git -C "$CARPETA/demo" diff --cached --name-only)]"
      }
      When call punto_de_control
      The status should be success
      The line 1 of output should eq 'estado=[]'
      The line 2 of output should eq 'ignorado=.devskills/lecciones.md'
      The line 3 of output should eq 'preparado=[documentacion/avance/reporte.md]'
    End

    It 'prepara Graphify: exclusiones, grafos versionados sin cachés y merge driver local'
      preparar_graphify() {
        devskills init "$CARPETA/demo" --nombre "Demo" --slug demo --puerto-base 19100 --correo 'ana@example.invalid' >/dev/null
        cd "$CARPETA/demo" || return 1
        mkdir -p codigo/graphify-out/cache documentacion/graphify-out
        echo '{}' >codigo/graphify-out/graph.json
        echo '# r' >codigo/graphify-out/GRAPH_REPORT.md
        echo '<html>' >codigo/graphify-out/graph.html
        echo '{}' >codigo/graphify-out/cache/x.json
        echo '{}' >codigo/graphify-out/manifest.json
        echo '{}' >documentacion/graphify-out/graph.json
        echo "driver=$(git config --get merge.graphify.driver)"
        echo "atributo=$(git check-attr merge -- codigo/graphify-out/graph.json documentacion/graphify-out/graph.json | tr '\n' ' ')"
        echo "estado=[$(git status --porcelain --untracked-files=all | LC_ALL=C sort | tr '\n' ' ')]"
      }
      When call preparar_graphify
      The status should be success
      The path "$CARPETA/demo/.graphifyignore" should be file
      The contents of file "$CARPETA/demo/.graphifyignore" should include 'documentacion/sesiones/'
      The contents of file "$CARPETA/demo/.graphifyignore" should include '.env.*'
      The contents of file "$CARPETA/demo/codigo/.dockerignore" should include 'graphify-out/'
      The line 1 of output should eq 'driver=graphify merge-driver %O %A %B'
      The line 2 of output should eq 'atributo=codigo/graphify-out/graph.json: merge: graphify documentacion/graphify-out/graph.json: merge: graphify '
      The line 3 of output should eq 'estado=[?? codigo/graphify-out/GRAPH_REPORT.md ?? codigo/graphify-out/graph.json ?? documentacion/graphify-out/graph.json ]'
    End

    It 'el .gitignore del proyecto lista .devskills/'
      When call devskills init "$CARPETA/demo" --nombre "Demo" --slug demo --puerto-base 19100 --sin-git
      The status should be success
      The output should include 'Proyecto creado'
      The contents of file "$CARPETA/demo/.gitignore" should include '.devskills/'
    End

    It 'rechaza un rango de puertos que incluye uno reservado'
      When call devskills init "$CARPETA/demo" --slug demo --puerto-base 5400 --puertos-reservados 5432
      The status should be failure
      The stderr should be present
      The path "$CARPETA/demo/codigo" should not be exist
    End
  End
End
