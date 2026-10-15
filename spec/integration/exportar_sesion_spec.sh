# shellcheck shell=bash

# Pruebas de plantillas/analisis/exportar_sesion.py: enmascara secretos obvios antes de escribir.
# Los "secretos" se arman en tiempo de ejecución y son falsos: el repo de DevSkills también se escanea.
Describe 'exportar_sesion.py'
  preparar_exportacion() {
    TMP_E="$(mktemp -d)"
    PYTHON_ABS="$(command -v python3 || command -v python)"
    export TMP_E PYTHON_ABS
  }
  limpiar_exportacion() { rm -rf "$TMP_E"; }
  BeforeEach 'preparar_exportacion'
  AfterEach 'limpiar_exportacion'

  # Crea una sesión con un mensaje del usuario que pega secretos falsos y exporta.
  exportar_con_secretos() {
    "$PYTHON_ABS" - "$TMP_E" "$PROJECT_ROOT" <<'PY'
import json, pathlib, subprocess, sys
tmp, raiz = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
relleno = "A1b2C3d4E5f6G7h8I9j0"
secretos = {
    "gh": "ghp_" + relleno + "K1L2M3",
    "aws": "AKIA" + "ABCDEFGH12345678",
    "bearer": "Authorization: Bearer " + relleno + relleno,
    "url": "postgres://app:" + "claveSuperSecreta99" + "@db.example:5432/app",
    "asig": "DB_PASSWORD=" + "hunter2hunter2",
    "llave": "-----BEGIN " + "PRIVATE KEY-----\n" + relleno * 3 + "\n-----END " + "PRIVATE KEY-----",
}
texto = "Mira esto:\n" + "\n".join(secretos.values()) + "\nY un texto normal sin secretos."
(tmp / "s.jsonl").write_text(
    json.dumps({"type": "user", "timestamp": "2026-01-01T10:00:00Z", "message": {"content": texto}}) + "\n",
    encoding="utf-8",
)
r = subprocess.run(
    [sys.executable, str(raiz / "plantillas/analisis/exportar_sesion.py"), str(tmp / "s.jsonl"), str(tmp / "o.md"), "Prueba"],
    capture_output=True, text=True, encoding="utf-8",
)
salida = (tmp / "o.md").read_text(encoding="utf-8")
print("rc", r.returncode)
print("aviso" if "se enmascararon" in r.stderr else "sin-aviso")
for nombre, valor in secretos.items():
    parte = valor.split("=")[-1] if nombre == "asig" else valor
    clave = relleno if nombre in ("gh", "bearer", "llave") else parte
    print(nombre, "FILTRADO" if (clave in salida or parte in salida) else "oculto")
print("normal", "conservado" if "Y un texto normal sin secretos." in salida else "perdido")
print("usuario-url", "conservado" if "postgres://app:" in salida else "perdido")
print("variable", "conservada" if "DB_PASSWORD=" in salida else "perdida")
PY
  }

  It 'enmascara llaves privadas, tokens, Authorization, claves en URL y asignaciones, y conserva el resto'
    When call exportar_con_secretos
    The status should be success
    The output should include 'rc 0'
    The output should include 'aviso'
    The output should include 'gh oculto'
    The output should include 'aws oculto'
    The output should include 'bearer oculto'
    The output should include 'url oculto'
    The output should include 'asig oculto'
    The output should include 'llave oculto'
    The output should include 'normal conservado'
    The output should include 'usuario-url conservado'
    The output should include 'variable conservada'
    The output should not include 'FILTRADO'
  End

  It 'un texto sin secretos no se altera ni avisa'
    sin_secretos() {
      "$PYTHON_ABS" - "$TMP_E" "$PROJECT_ROOT" <<'PY'
import json, pathlib, subprocess, sys
tmp, raiz = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
texto = "Hablemos del token de sesión y de la contraseña en general, sin valores."
(tmp / "s.jsonl").write_text(
    json.dumps({"type": "user", "timestamp": "2026-01-01T10:00:00Z", "message": {"content": texto}}) + "\n",
    encoding="utf-8",
)
r = subprocess.run(
    [sys.executable, str(raiz / "plantillas/analisis/exportar_sesion.py"), str(tmp / "s.jsonl"), str(tmp / "o.md"), "Prueba"],
    capture_output=True, text=True, encoding="utf-8",
)
print("aviso" if "se enmascararon" in r.stderr else "sin-aviso")
print("intacto" if texto in (tmp / "o.md").read_text(encoding="utf-8") else "alterado")
PY
    }
    When call sin_secretos
    The output should include 'sin-aviso'
    The output should include 'intacto'
  End
End
