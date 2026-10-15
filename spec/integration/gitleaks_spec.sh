# shellcheck shell=bash

# Pruebas del escáner de secretos. Las que necesitan el binario real se omiten donde no está instalado.
sin_gitleaks() { ! command -v gitleaks >/dev/null 2>&1; }

Describe 'scripts/gitleaks_archivos.py'
  setup_gitleaks() {
    TMP_G="$(mktemp -d)"
    mkdir -p "$TMP_G/repo"
    git -C "$TMP_G/repo" init -q -b main
    echo "hola" >"$TMP_G/repo/archivo.txt"
    echo ".env" >"$TMP_G/repo/.gitignore"
    PYTHON_ABS="$(command -v python3 || command -v python)"
    export TMP_G PYTHON_ABS
  }
  # Una llave privada falsa (aleatoria) armada en tiempo de ejecución: el repo de DevSkills también se escanea.
  llave_falsa() {
    printf '%s' '-----BEGIN'
    printf '%s
' ' PRIVATE KEY-----'
    head -c 120 /dev/urandom | base64 | fold -w 64
    printf '%s' '-----END'
    printf '%s
' ' PRIVATE KEY-----'
  }
  cleanup_gitleaks() { rm -rf "$TMP_G"; }
  BeforeEach 'setup_gitleaks'
  AfterEach 'cleanup_gitleaks'

  correr() { "$PYTHON_ABS" "$PROJECT_ROOT/scripts/gitleaks_archivos.py" --repo "$TMP_G/repo" "$@"; }

  Describe 'con el binario real de gitleaks'
    Skip if 'gitleaks no está instalado' sin_gitleaks

    It 'un repositorio limpio sale con 0 y usa el binario nativo'
      When call correr
      The status should be success
      The output should include 'gitleaks (nativo)'
      The output should include 'sin hallazgos'
      The stderr should be present
    End

    It 'un secreto en un archivo versionado sale con 1 y dice que no se haga commit'
      llave_falsa >"$TMP_G/repo/config.txt"
      When call correr
      The status should eq 1
      The output should include 'gitleaks (nativo)'
      The stderr should include 'No hagas commit'
    End

    It 'un archivo ignorado (como .env) no se copia ni se escanea'
      llave_falsa >"$TMP_G/repo/.env"
      When call correr
      The status should be success
      The output should include 'sin hallazgos'
      The stderr should be present
    End
  End

  It 'sin gitleaks ni Docker sale con 2, explica cómo instalarlo y no lo confunde con un hallazgo'
    vacio="$TMP_G/vacio"
    mkdir -p "$vacio"
    When run env PATH="$vacio" LOCALAPPDATA="$vacio" "$PYTHON_ABS" "$PROJECT_ROOT/scripts/gitleaks_archivos.py" --repo "$TMP_G/repo"
    The status should eq 2
    The stderr should include 'HERRAMIENTA NO DISPONIBLE'
    The stderr should include 'winget install Gitleaks.Gitleaks'
    The stderr should not include 'HAY HALLAZGOS'
  End

  It 'con --modo nativo y sin binario sale con 2'
    vacio="$TMP_G/vacio"
    mkdir -p "$vacio"
    When run env PATH="$vacio" LOCALAPPDATA="$vacio" "$PYTHON_ABS" "$PROJECT_ROOT/scripts/gitleaks_archivos.py" --repo "$TMP_G/repo" --modo nativo
    The status should eq 2
    The stderr should include 'winget install Gitleaks.Gitleaks'
    The stderr should not include 'HAY HALLAZGOS'
  End

  # Corre un fragmento de Python contra el módulo, con un entorno controlado.
  buscar_con_local() {
    PATH="$1" LOCALAPPDATA="$1" "$PYTHON_ABS" -c "
import sys
sys.path.insert(0, sys.argv[1])
import gitleaks_archivos as g
print(g.buscar_gitleaks())" "$PROJECT_ROOT/scripts"
  }
  modo_con_docker_caido() {
    "$PYTHON_ABS" -c "
import sys
from unittest import mock
sys.path.insert(0, sys.argv[1])
import gitleaks_archivos as g
caido = mock.Mock(returncode=1)
with mock.patch.object(g, 'buscar_gitleaks', return_value=None), mock.patch.object(g.shutil, 'which', return_value='/usr/bin/docker'), mock.patch.object(g.subprocess, 'run', return_value=caido):
    try:
        g.elegir_modo('auto')
    except SystemExit as e:
        print('salida', e.code)" "$PROJECT_ROOT/scripts"
  }

  It 'encuentra el binario de winget aunque no esté en el PATH'
    paquete="$TMP_G/local/Microsoft/WinGet/Packages/Gitleaks.Gitleaks_Fuente_abc"
    mkdir -p "$paquete"
    : >"$paquete/gitleaks.exe"
    When call buscar_con_local "$TMP_G/local"
    The status should be success
    The output should include 'Gitleaks.Gitleaks_Fuente_abc'
  End

  It 'encuentra el binario en WinGet/Links'
    mkdir -p "$TMP_G/local/Microsoft/WinGet/Links"
    : >"$TMP_G/local/Microsoft/WinGet/Links/gitleaks.exe"
    When call buscar_con_local "$TMP_G/local"
    The status should be success
    The output should include 'Links'
  End

  It 'con Docker instalado pero el demonio apagado sale con 2, no con 1'
    When call modo_con_docker_caido
    The status should be success
    The output should include 'salida 2'
    The stderr should include 'demonio está apagado'
    The stderr should not include 'HAY HALLAZGOS'
  End

  It 'las imágenes de gitleaks y semgrep se fijan por digest, no solo por etiqueta'
    imagenes_sin_digest() {
      git -C "$PROJECT_ROOT" grep -n -E '(zricethezav/gitleaks|semgrep/semgrep):[0-9v][0-9.]+' -- \
        .github bin scripts skills/ciclo-historia skills/validar-historia plantillas/codigo/README.md |
        grep -v '@sha256:[0-9a-f]\{64\}'
    }
    When call imagenes_sin_digest
    The status should be failure
    The output should eq ''
  End
End
