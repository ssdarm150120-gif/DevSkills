# shellcheck shell=bash

# Pruebas del porcentaje de avance de plantillas/analisis (porcentaje.py, plan_sprints.py y el tablero HTML).
Describe 'porcentaje de avance'
  preparar_plan() {
    TMP_P="$(mktemp -d)"
    PYTHON_ABS="$(command -v python3 || command -v python)"
    export TMP_P PYTHON_ABS
  }
  limpiar_plan() { rm -rf "$TMP_P"; }
  BeforeEach 'preparar_plan'
  AfterEach 'limpiar_plan'

  formato() {
    PYTHONPATH="$PROJECT_ROOT/plantillas/analisis" "$PYTHON_ABS" -c \
      'import sys; from porcentaje import formatear_porcentaje as f; print(f(int(sys.argv[1]), int(sys.argv[2])))' "$1" "$2" | tr -d '\r'
  }

  Describe 'formatear_porcentaje'
    Parameters
      0 327 '0 %'
      3 327 '0.9 %'
      1 327 '0.3 %'
      1 5000 '<0.1 %'
      9 100 '9.0 %'
      33 327 '10 %'
      1 3 '33 %'
      326 327 '99 %'
      327 327 '100 %'
      0 0 '0 %'
    End
    It "$1 de $2 se muestra como $3"
      When call formato "$1" "$2"
      The output should eq "$3"
    End
  End

  # Proyecto mínimo: 327 puntos en total, 3 de ellos en Listo.
  generar_plan() {
    local doc="$TMP_P/documentacion"
    mkdir -p "$doc/analisis" "$doc/avance"
    cp "$PROJECT_ROOT"/plantillas/analisis/*.py "$PROJECT_ROOT/plantillas/analisis/plan_sprints_plantilla.html" "$doc/analisis/"
    cp "$PROJECT_ROOT/plantillas/documentacion/SRS.md" "$PROJECT_ROOT/plantillas/documentacion/PLAN.md" "$doc/"
    cat >"$doc/analisis/plan_entregas.json" <<'JSON'
{"inicio": "2026-01-05", "velocidad": 400, "dias_sprint": 14,
 "habilitadores": {"EN-01": {"titulo": "Uno", "ref": "D.1"}, "EN-02": {"titulo": "Dos", "ref": "D.2"}},
 "entregas": [{"num": "0", "nombre": "Cimientos", "objetivo": "Probar", "items": [["EN-01", 3], ["EN-02", 324]]}]}
JSON
    echo '{"EN-01": {"estado": "Listo", "fecha": "2026-01-06"}}' >"$doc/avance/estado_backlog.json"
    (cd "$TMP_P" && "$PYTHON_ABS" documentacion/analisis/plan_sprints.py >/dev/null) || return 1
  }

  It 'PLAN.md muestra 0.9 % y no 0 % cuando 3 de 327 puntos están terminados'
    generar_plan
    When call cat "$TMP_P/documentacion/PLAN.md"
    The output should include '**Terminados:** 3 (0.9 %)'
    The output should include '| 3 (0.9 %) |'
    The output should include '**3 (0.9 %)**'
    The output should not include '(0 %)'
  End

  It 'el tablero HTML trae la misma regla que porcentaje.py'
    generar_plan
    When call cat "$TMP_P/documentacion/plan_sprints.html"
    The output should include 'const porcentaje = (hechos, total) =>'
    The output should include "decimas === 0 ? '<0.1 %'"
    The output should include 'porcentaje(listos, total)'
    The output should not include 'Math.round(listos / total * 100)'
  End

  It 'la función del tablero devuelve lo mismo que porcentaje.py'
    Skip if 'no hay node' ! command -v node >/dev/null 2>&1
    comparar_js() {
      PLAN_HTML="$PROJECT_ROOT/plantillas/analisis/plan_sprints_plantilla.html" node -e '
        const fs = require("fs");
        const html = fs.readFileSync(process.env.PLAN_HTML, "utf8");
        const inicio = html.indexOf("const porcentaje = ");
        const fin = html.indexOf("};", inicio) + 2;
        const porcentaje = eval("(" + html.slice(inicio, fin).replace("const porcentaje = ", "").replace(/;$/, "") + ")");
        for (const [h, t] of [[0,327],[3,327],[1,327],[1,5000],[9,100],[33,327],[1,3],[326,327],[327,327],[0,0]]) console.log(h, t, porcentaje(h, t));
      '
    }
    When call comparar_js
    The output should include '3 327 0.9 %'
    The output should include '1 5000 <0.1 %'
    The output should include '33 327 10 %'
    The output should include '326 327 99 %'
    The output should include '327 327 100 %'
  End
End
