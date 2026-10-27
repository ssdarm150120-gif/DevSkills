# shellcheck shell=bash

Describe 'devskills enrutamiento'
  devskills() {
    bash "$PROJECT_ROOT/bin/devskills" "$@"
  }

  # Proyecto DevSkills mínimo: solo lo que el CLI mira (CONTEXTO.md y, según la prueba, pruebas, CI, lint y SRS).
  preparar_proyecto() {
    PROY="$(mktemp -d)"
    mkdir -p "$PROY/documentacion"
    : >"$PROY/documentacion/CONTEXTO.md"
    export PROY
  }
  limpiar_proyecto() {
    cd / || true
    rm -rf "$PROY"
  }
  BeforeEach 'preparar_proyecto'
  AfterEach 'limpiar_proyecto'

  archivo() { echo "$PROY/.devskills/enrutamiento.json"; }

  # Lee el JSON con Python para probar que es JSON válido y no solo texto parecido.
  leer_json() {
    local py
    for py in python3 python; do
      if "$py" -c 'import sys; sys.exit(0)' >/dev/null 2>&1; then
        "$py" - "$(archivo)" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    d = json.load(f)
print((d["activo"], d["version"], len(d["tabla"]), d["tabla"]["angel-fixer-excepcion"], d["escalamiento"]))
print((sorted({v["modelo"] for v in d["tabla"].values()}), sorted({v["esfuerzo"] for v in d["tabla"].values()}),
       d["actualizado"][:2], d["actualizado"][-1]))
PY
        return
      fi
    done
    return 1
  }

  Describe 'estado'
    It 'sin archivo dice que está inactivo y que cada agente usa su frontmatter'
      When call devskills enrutamiento estado "$PROY"
      The status should be success
      The output should include 'inactivo'
      The output should include 'frontmatter'
      The path "$(archivo)" should not be exist
    End

    It 'sin acción muestra el estado'
      When call devskills enrutamiento "$PROY"
      The status should be success
      The output should include 'Enrutamiento de modelos: inactivo'
    End

    It 'rechaza una opción desconocida'
      When call devskills enrutamiento estado --inventada
      The status should eq 2
      The stderr should include 'Opción desconocida'
    End

    It '--forzar solo aplica a activar'
      When call devskills enrutamiento desactivar "$PROY" --forzar
      The status should eq 2
      The stderr should include '--forzar solo aplica'
    End
  End

  Describe 'activar'
    It 'crea el archivo con la tabla por omisión y lo muestra'
      When call devskills enrutamiento activar "$PROY"
      The status should be success
      The output should include 'Creé .devskills/enrutamiento.json'
      The output should include 'desarrollo: sonnet / medium'
      The output should include 'qa-cierre-sprint: opus / high'
      The output should include 'verificador-final: sonnet / high'
      The output should include 'analista-arquitecto: opus / medium'
      The output should include 'registrar-avance: haiku / low'
      The path "$(archivo)" should be file
    End

    It 'deja un JSON válido con el formato que lee el orquestador'
      leer_tabla() {
        devskills enrutamiento activar "$PROY" >/dev/null
        leer_json | tr -d '\r' # el Python de Windows termina las líneas con CRLF
      }
      When call leer_tabla
      The status should be success
      The line 1 of output should eq "(True, 1, 12, {'modelo': 'opus', 'esfuerzo': 'high'}, {'max_reintentos': 1, 'orden': ['esfuerzo', 'modelo']})"
      The line 2 of output should eq "(['haiku', 'opus', 'sonnet'], ['high', 'low', 'medium'], '20', 'Z')"
    End

    It 'no sobrescribe una tabla existente: la reactiva y conserva los ajustes'
      reactivar() {
        devskills enrutamiento activar "$PROY" >/dev/null
        devskills enrutamiento desactivar "$PROY" >/dev/null
        # ajuste local de la tabla (regla 5: un fallo se volvió regla)
        sed 's/"desarrollo": {"modelo": "sonnet", "esfuerzo": "medium"}/"desarrollo": {"modelo": "sonnet", "esfuerzo": "high"}/' "$(archivo)" >"$PROY/tmp.json"
        mv "$PROY/tmp.json" "$(archivo)"
        devskills enrutamiento activar "$PROY"
      }
      When call reactivar
      The status should be success
      The output should include 'Reactivé'
      The output should include 'desarrollo: sonnet / high'
      The contents of file "$(archivo)" should include '"activo": true'
    End

    It 'con --forzar vuelve a la tabla por omisión'
      forzar() {
        devskills enrutamiento activar "$PROY" >/dev/null
        sed 's/"mecanico": {"modelo": "haiku"/"mecanico": {"modelo": "opus"/' "$(archivo)" >"$PROY/tmp.json"
        mv "$PROY/tmp.json" "$(archivo)"
        devskills enrutamiento activar "$PROY" --forzar
      }
      When call forzar
      The status should be success
      The output should include 'mecanico: haiku / low'
      The output should not include 'mecanico: opus'
    End

    It 'fuera de un proyecto DevSkills no crea nada'
      sin_proyecto() {
        rm -f "$PROY/documentacion/CONTEXTO.md"
        devskills enrutamiento activar "$PROY"
      }
      When call sin_proyecto
      The status should be failure
      The stderr should include 'no es un proyecto DevSkills'
      The path "$(archivo)" should not be exist
    End

    It 'rechaza reactivar un archivo ilegible sin --forzar'
      ilegible() {
        mkdir -p "$PROY/.devskills"
        echo '{"otra": 1}' >"$(archivo)"
        devskills enrutamiento activar "$PROY"
      }
      When call ilegible
      The status should be failure
      The stderr should include 'no tiene "activo"'
      The contents of file "$(archivo)" should eq '{"otra": 1}'
    End

    It 'avisa si git no ignora .devskills/'
      sin_ignorar() {
        git -C "$PROY" init -q
        devskills enrutamiento activar "$PROY"
      }
      When call sin_ignorar
      The status should be success
      The output should include "git no ignora .devskills/"
    End

    It 'no avisa si .devskills/ está en el .gitignore'
      ignorado() {
        git -C "$PROY" init -q
        echo '.devskills/' >"$PROY/.gitignore"
        devskills enrutamiento activar "$PROY"
      }
      When call ignorado
      The status should be success
      The output should not include "git no ignora"
    End
  End

  Describe 'desactivar'
    It 'apaga el enrutamiento sin borrar la tabla'
      apagar() {
        devskills enrutamiento activar "$PROY" >/dev/null
        devskills enrutamiento desactivar "$PROY"
        devskills enrutamiento estado "$PROY"
      }
      When call apagar
      The status should be success
      The output should include 'Desactivé'
      The output should include 'desactivado'
      The contents of file "$(archivo)" should include '"activo": false'
      The contents of file "$(archivo)" should include '"qa-excepcion": {"modelo": "opus", "esfuerzo": "high"}'
    End

    It 'sin archivo no hace nada y no falla'
      When call devskills enrutamiento desactivar "$PROY"
      The status should be success
      The output should include 'ya está inactivo'
      The path "$(archivo)" should not be exist
    End
  End

  Describe 'evaluar'
    It 'sin pruebas no lo recomienda'
      When call devskills enrutamiento evaluar "$PROY"
      The status should be success
      The output should include 'Veredicto: no recomendado'
      The output should include 'sin pruebas no hay cascada segura'
    End

    It 'con pruebas pero sin CI, lint ni Gherkin da parcial con sus motivos'
      solo_pruebas() {
        mkdir -p "$PROY/codigo/pruebas"
        : >"$PROY/codigo/pruebas/test_algo.py"
        devskills enrutamiento evaluar "$PROY"
      }
      When call solo_pruebas
      The status should be success
      The output should include 'Veredicto: parcial'
      The output should include 'Comando de pruebas: no lo deduje'
      The output should include 'CI: no hay workflow'
      The output should include 'Tipos y lint: no encontré'
      The output should include 'SRS con Gherkin'
    End

    It 'con pruebas y su comando, CI, tipos y lint y Gherkin lo recomienda'
      completo() {
        mkdir -p "$PROY/codigo/pruebas" "$PROY/.github/workflows"
        : >"$PROY/codigo/pruebas/test_algo.py"
        printf '%s\n' '[tool.pytest.ini_options]' '[tool.mypy]' '[tool.ruff]' >"$PROY/codigo/pyproject.toml"
        : >"$PROY/codigo/.importlinter"
        echo 'name: CI' >"$PROY/.github/workflows/ci.yml"
        printf '%s\n' 'Característica: Ingreso' '  Escenario: Ingreso correcto' >"$PROY/documentacion/SRS.md"
        devskills enrutamiento evaluar "$PROY"
      }
      When call completo
      The status should be success
      The output should include 'Comando de pruebas: cd codigo && pytest'
      The output should include 'mypy (codigo), ruff (codigo), import-linter (codigo)'
      The output should include 'SRS con escenarios Gherkin'
      The output should include 'Veredicto: recomendado'
    End
  End

  Describe 'doctor'
    It 'dentro de un proyecto muestra el estado del enrutamiento'
      doctor_en_proyecto() {
        devskills enrutamiento activar "$PROY" >/dev/null
        cd "$PROY" && devskills doctor
      }
      When call doctor_en_proyecto
      The status should be success
      The output should include 'Enrutamiento de modelos: activo'
    End

    It 'fuera de un proyecto no lo menciona'
      doctor_fuera() { cd "$PROY/documentacion" && devskills doctor; }
      When call doctor_fuera
      The status should be success
      The output should not include 'Enrutamiento de modelos'
    End
  End

  It 'la ayuda lista el comando'
    When call devskills help
    The status should be success
    The output should include 'devskills enrutamiento'
  End
End
