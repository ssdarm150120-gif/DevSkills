# shellcheck shell=bash

# Pruebas de plantillas/analisis/deriva_grafos.py: deriva entre el grafo del deber ser (documentación) y el de lo
# que es (código). Los grafos de las pruebas son graph.json mínimos con la forma que escribe Graphify 0.9.x, así que
# no hace falta tener graphify instalado; la última prueba usa el graphify real solo si está en el PATH.
Describe 'deriva entre el deber ser y lo que es'
  preparar_deriva() {
    TMP_D="$(mktemp -d)"
    PYTHON_ABS="$(command -v python3 || command -v python)"
    SCRIPT_D="$PROJECT_ROOT/plantillas/analisis/deriva_grafos.py"
    mkdir -p "$TMP_D/codigo/graphify-out" "$TMP_D/documentacion/graphify-out"
    export TMP_D PYTHON_ABS SCRIPT_D
  }
  limpiar_deriva() {
    cd / || true
    rm -rf "$TMP_D"
  }
  BeforeEach 'preparar_deriva'
  AfterEach 'limpiar_deriva'

  deriva() { (cd "$TMP_D" && "$PYTHON_ABS" "$SCRIPT_D" "$@"); }

  # Código: módulo ventas (Pedido en el dominio, con su caso de uso), módulo inventario (Existencia, que el diseño no
  # nombra), una clase de pruebas y una migración (que no cuentan) y el módulo configuracion (infraestructura).
  grafo_codigo() {
    cat >"$TMP_D/codigo/graphify-out/graph.json" <<'JSON'
{"directed": true, "multigraph": false, "graph": {"schema_version": 1, "graphify_version": "0.9.96"},
 "nodes": [
  {"id": "ventas_dominio_pedido_pedido", "label": "Pedido", "_callable_class": true, "_origin": "ast", "file_type": "code", "source_file": "codigo/ventas/dominio/pedido.py", "source_location": "L1"},
  {"id": "ventas_aplicacion_registrar_pedido", "label": "registrar_pedido()", "_origin": "ast", "file_type": "code", "source_file": "codigo/ventas/aplicacion/registrar_pedido.py", "source_location": "L3"},
  {"id": "inventario_dominio_existencia", "label": "Existencia", "_callable_class": true, "_origin": "ast", "file_type": "code", "source_file": "codigo/inventario/dominio/existencia.py", "source_location": "L5"},
  {"id": "ventas_pruebas_falso", "label": "RepositorioFalsoDeCobros", "_callable_class": true, "_origin": "ast", "file_type": "code", "source_file": "codigo/ventas/pruebas/falsos.py", "source_location": "L1"},
  {"id": "ventas_migracion", "label": "Migration", "_callable_class": true, "_origin": "ast", "file_type": "code", "source_file": "codigo/ventas/adaptadores/salida/migraciones/0001_esquema.py", "source_location": "L1"},
  {"id": "configuracion_settings", "label": "ConfiguracionDelSitio", "_callable_class": true, "_origin": "ast", "file_type": "code", "source_file": "codigo/configuracion/dominio/sitio.py", "source_location": "L1"}
 ],
 "links": [], "hyperedges": []}
JSON
  }

  # Deber ser, nivel estructural: encabezados del SRS y del DISEÑO como los escribe `graphify update documentacion`.
  grafo_documentacion() {
    cat >"$TMP_D/documentacion/graphify-out/graph.json" <<'JSON'
{"directed": true, "multigraph": false, "graph": {"schema_version": 1, "graphify_version": "0.9.96"},
 "nodes": [
  {"id": "diseno", "label": "DISENO.md", "_origin": "ast", "file_type": "document", "node_kind": "page", "source_file": "documentacion/DISENO.md", "source_location": "L1"},
  {"id": "diseno_d3", "label": "D.3 Máquinas de estado", "_origin": "ast", "file_type": "document", "node_kind": "heading", "source_file": "documentacion/DISENO.md", "source_location": "L235"},
  {"id": "diseno_d31", "label": "D.3.1 Pedidos (módulo `ventas`)", "_origin": "ast", "file_type": "document", "node_kind": "heading", "source_file": "documentacion/DISENO.md", "source_location": "L239"},
  {"id": "diseno_factura", "label": "Entidad Factura", "_origin": "ast", "file_type": "document", "node_kind": "heading", "source_file": "documentacion/DISENO.md", "source_location": "L250"},
  {"id": "diseno_d1", "label": "D.1 Mapa de módulos, puertos y adaptadores", "_origin": "ast", "file_type": "document", "node_kind": "heading", "source_file": "documentacion/DISENO.md", "source_location": "L89"},
  {"id": "srs_hu", "label": "HU-07 Registrar pedido", "_origin": "ast", "file_type": "document", "node_kind": "heading", "source_file": "documentacion/SRS.md", "source_location": "L346"},
  {"id": "srs_conv", "label": "B.0 Convenciones", "_origin": "ast", "file_type": "document", "node_kind": "heading", "source_file": "documentacion/SRS.md", "source_location": "L318"},
  {"id": "srs_b", "label": "Anexo B. Historias de usuario del MVP", "_origin": "ast", "file_type": "document", "node_kind": "heading", "source_file": "documentacion/SRS.md", "source_location": "L316"}
 ],
 "links": [
  {"source": "diseno_d3", "target": "diseno_d31", "relation": "contains"},
  {"source": "srs_b", "target": "srs_conv", "relation": "contains"}
 ], "hyperedges": []}
JSON
  }

  It 'sin grafos explica cómo generarlos y sale con 3'
    When call deriva
    The status should eq 3
    The stderr should include 'No se midió la deriva'
    The stderr should include 'graphify update codigo'
    The stderr should include 'graphify update documentacion'
    The stderr should include 'solo con permiso del Product Owner'
    The stderr should include 'uv tool install graphifyy'
  End

  It 'sin el grafo del deber ser dice cuál falta y no inventa un reporte'
    grafo_codigo
    When call deriva
    The status should eq 3
    The stderr should include 'el deber ser (documentación)'
    The stderr should not include 'lo que es (código)'
    The output should eq ''
  End

  It 'un grafo que no es JSON de Graphify sale con 2'
    grafo_codigo
    echo '{"no": "es un grafo"}' >"$TMP_D/documentacion/graphify-out/graph.json"
    When call deriva
    The status should eq 2
    The stderr should include "falta la lista 'nodes'"
  End

  It 'reporta lo que el diseño dice y el código no tiene'
    grafo_codigo
    grafo_documentacion
    When call deriva
    The status should eq 0
    The output should include 'nivel estructural (encabezados, sin LLM)'
    The output should include '| D-1 | Entidad Factura | documentacion/DISENO.md L250 |'
    The output should not include '| Entidad Pedido'
    The output should not include 'HU-07 Registrar pedido |'
    The output should not include 'Convenciones |'
    The output should not include 'Mapa de módulos'
  End

  It 'reporta lo que el código tiene y el diseño no dice, sin pruebas, migraciones ni infraestructura'
    grafo_codigo
    grafo_documentacion
    When call deriva
    The status should eq 0
    The output should include '| módulo | inventario | codigo/inventario |'
    The output should include '| clase | Existencia | codigo/inventario/dominio/existencia.py L5 |'
    The output should not include '| módulo | ventas |'
    The output should not include 'RepositorioFalsoDeCobros'
    The output should not include 'Migration'
    The output should not include 'ConfiguracionDelSitio'
  End

  It '--salida escribe el reporte Markdown y resume los conteos'
    grafo_codigo
    grafo_documentacion
    When call deriva --salida documentacion/avance/S01/DERIVA-S01.md
    The status should eq 0
    The output should include 'Reporte de deriva en documentacion/avance/S01/DERIVA-S01.md: 1 del diseño sin código, 2 del código sin diseño'
    The contents of file "$TMP_D/documentacion/avance/S01/DERIVA-S01.md" should include '# Deriva entre el deber ser y lo que es'
  End

  It '--estricto sale con 1 si hay deriva'
    grafo_codigo
    grafo_documentacion
    When call deriva --estricto --salida "$TMP_D/deriva.md"
    The status should eq 1
    The output should include 'Reporte de deriva'
  End

  It '--estricto sale con 0 cuando no hay deriva'
    grafo_codigo
    grafo_documentacion
    # El diseño nombra la factura en el código y el inventario en el diseño: sin deriva.
    "$PYTHON_ABS" - "$TMP_D" <<'PY'
import json, sys
from pathlib import Path
raiz = Path(sys.argv[1])
codigo = raiz / "codigo/graphify-out/graph.json"
datos = json.loads(codigo.read_text(encoding="utf-8"))
datos["nodes"].append({"id": "f", "label": "Factura", "_callable_class": True, "file_type": "code",
                       "source_file": "codigo/ventas/dominio/factura.py", "source_location": "L1"})
codigo.write_text(json.dumps(datos), encoding="utf-8")
doc = raiz / "documentacion/graphify-out/graph.json"
datos = json.loads(doc.read_text(encoding="utf-8"))
datos["nodes"].append({"id": "inv", "label": "Módulo 2: Inventario y existencias", "_origin": "ast",
                       "file_type": "document", "node_kind": "heading", "source_file": "documentacion/SRS.md"})
doc.write_text(json.dumps(datos), encoding="utf-8")
PY
    When call deriva --estricto
    The status should eq 0
    The output should include '**Sin deriva detectada.**'
  End

  It 'con nodos de la pasada semántica (LLM) declara el nivel semántico y los compara'
    grafo_codigo
    grafo_documentacion
    "$PYTHON_ABS" - "$TMP_D/documentacion/graphify-out/graph.json" <<'PY'
import json, sys
from pathlib import Path
ruta = Path(sys.argv[1])
datos = json.loads(ruta.read_text(encoding="utf-8"))
datos["nodes"].append({"id": "c1", "label": "Nota de crédito", "file_type": "document", "source_file": "documentacion/DISENO.md"})
ruta.write_text(json.dumps(datos), encoding="utf-8")
PY
    When call deriva
    The status should eq 0
    The output should include 'nivel semántico (con LLM)'
    The output should include '| Nota de crédito | documentacion/DISENO.md |'
  End

  # Éxito (0) = NO hay un Graphify utilizable: falta el binario, su versión no es 0.9.x o superior (otro paquete
  # que también se llame `graphify`), o `graphify update` no funciona sobre un directorio de prueba.
  sin_graphify_compatible() {
    local version mayor menor prueba
    command -v graphify >/dev/null 2>&1 || return 0
    version="$(graphify --version 2>/dev/null | tr -d '\r' | sed -n 's/^graphify \([0-9][0-9]*\)\.\([0-9][0-9]*\)\..*$/\1 \2/p' | head -n 1)"
    [[ -n "$version" ]] || return 0
    read -r mayor menor <<<"$version"
    if [[ "$mayor" -eq 0 && "$menor" -lt 9 ]]; then return 0; fi
    prueba="$(mktemp -d)"
    mkdir -p "$prueba/codigo/ventas"
    printf 'class Pedido:\n    pass\n' >"$prueba/codigo/ventas/pedido.py"
    if (cd "$prueba" && GRAPHIFY_BACKEND=none GRAPHIFY_NO_TIPS=1 graphify update codigo >/dev/null 2>&1) \
      && [[ -f "$prueba/codigo/graphify-out/graph.json" ]]; then
      rm -rf "$prueba"
      return 1
    fi
    rm -rf "$prueba"
    return 0
  }

  It 'con graphify real: los grafos de un proyecto nuevo excluyen sesiones, datos y migraciones'
    Skip if 'no hay un graphify 0.9.x o superior que funcione' sin_graphify_compatible
    proyecto_real() {
      bash "$PROJECT_ROOT/bin/devskills" init "$TMP_D/demo" --nombre "Demo" --slug demo --puerto-base 19100 \
        --correo 'ana@example.invalid' >/dev/null || return 1
      mkdir -p "$TMP_D/demo/documentacion/sesiones"
      printf '# Sesion\n\n## Dato pegado por error\n' >"$TMP_D/demo/documentacion/sesiones/2026-01-01.md"
      cd "$TMP_D/demo" || return 1
      GRAPHIFY_BACKEND=none GRAPHIFY_NO_TIPS=1 graphify update codigo >/dev/null 2>&1 || return 1
      GRAPHIFY_BACKEND=none GRAPHIFY_NO_TIPS=1 graphify update documentacion >/dev/null 2>&1 || return 1
      "$PYTHON_ABS" -c '
import json
doc = json.load(open("documentacion/graphify-out/graph.json", encoding="utf-8"))
cod = json.load(open("codigo/graphify-out/graph.json", encoding="utf-8"))
print("docs=" + ",".join(sorted({n["source_file"] for n in doc["nodes"]})))
print("migraciones=" + str(any("/migraciones/" in n.get("source_file", "") for n in cod["nodes"])))' | tr -d '\r'
      echo "estado=[$(git status --porcelain --untracked-files=all -- codigo/graphify-out documentacion/graphify-out | LC_ALL=C sort | tr '\n' ' ')]"
      "$PYTHON_ABS" documentacion/analisis/deriva_grafos.py --salida "$TMP_D/deriva.md"
    }
    When call proyecto_real
    The status should eq 0
    The line 1 of output should eq 'docs=documentacion/CONTEXTO.md,documentacion/DISENO.md,documentacion/EVALUACION_ALTERNATIVAS.md,documentacion/PLAN.md,documentacion/SRS.md'
    The line 2 of output should eq 'migraciones=False'
    The line 3 of output should eq 'estado=[?? codigo/graphify-out/GRAPH_REPORT.md ?? codigo/graphify-out/graph.json ?? documentacion/graphify-out/GRAPH_REPORT.md ?? documentacion/graphify-out/graph.json ]'
    The output should include 'Reporte de deriva en'
  End
End
