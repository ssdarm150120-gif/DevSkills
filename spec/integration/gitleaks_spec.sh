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

  It 'sin gitleaks ni Docker explica cómo instalarlo y no da el escaneo por bueno'
    vacio="$TMP_G/vacio"
    mkdir -p "$vacio"
    When run env PATH="$vacio" "$PYTHON_ABS" "$PROJECT_ROOT/scripts/gitleaks_archivos.py" --repo "$TMP_G/repo" --modo nativo
    The status should be failure
    The stderr should include 'winget install Gitleaks.Gitleaks'
  End
End
