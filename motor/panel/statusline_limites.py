"""
Status line mínima de Claude Code que además guarda los límites del plan para el panel.

Claude Code le pasa por stdin el JSON documentado de la status line (code.claude.com/docs/en/statusline). De ahí se
usan solo estos campos:

  rate_limits.five_hour.used_percentage / resets_at   (ventana de 5 h; solo Pro y Max, después de la 1.ª respuesta)
  rate_limits.seven_day.used_percentage / resets_at   (ventana semanal)
  session_id y cost.total_cost_usd                    (costo de la sesión, calculado por Claude Code a precio de lista)

y se escriben en <datos>/panel/estado/limites.json (escritura atómica; <datos> es DEVSKILLS_DATOS o ~/.devskills). No lee credenciales, no llama a ningún endpoint y no
guarda contenido de mensajes. Imprime una línea corta, p. ej. "5 h: 23 % (14:20) · semana: 41 %".

Activarlo (no se activa solo): `devskills motor enganchar` escribe la `statusLine` en el settings.json de usuario de
Claude Code con la ruta y el Python de ESTE equipo (muestra el diff, pide confirmación y respalda). Si ya tienes otra
status line: `devskills motor enganchar --envolver "<tu comando>"`; el comando envuelto recibe el mismo JSON por stdin
y su salida se imprime antes que los límites. Quitarla: `devskills motor enganchar --quitar`.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import rutas  # noqa: E402

# PANEL_LIMITES solo para pruebas (otra carpeta de estado); por omisión, el estado del panel principal.
DESTINO = Path(os.environ.get("PANEL_LIMITES") or rutas.panel_estado() / "limites.json")
DIAS_COSTO = 35


def leer(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def escribir_atomico(ruta, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f"{ruta.name}.{os.getpid()}.tmp")
    try:
        with open(temporal, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporal, ruta)
    finally:
        try:
            temporal.unlink()
        except OSError:
            pass


def ventana(rl, nombre):
    v = rl.get(nombre) if isinstance(rl, dict) else None
    if isinstance(v, dict) and isinstance(v.get("used_percentage"), (int, float)) and isinstance(v.get("resets_at"), (int, float)):
        return {"used_percentage": float(v["used_percentage"]), "resets_at": float(v["resets_at"])}
    return None


def actualizar(entrada, ahora):
    """Mezcla lo nuevo con lo guardado: varias sesiones abiertas escriben el mismo archivo."""
    d = leer(DESTINO)
    rl = entrada.get("rate_limits")
    nuevos = {k: ventana(rl, k) for k in ("five_hour", "seven_day")}
    guardados = d.get("rate_limits") if isinstance(d.get("rate_limits"), dict) else {}
    d["rate_limits"] = {k: (nuevos[k] or guardados.get(k)) for k in nuevos}
    d["rate_limits"] = {k: v for k, v in d["rate_limits"].items() if v and v["resets_at"] > ahora}
    if any(nuevos.values()):
        d["capturado"] = ahora
    # Costo por hora: delta del total de la sesión desde la última vez (un /clear reinicia el total a 0).
    sid = entrada.get("session_id")
    costo = (entrada.get("cost") or {}).get("total_cost_usd") if isinstance(entrada.get("cost"), dict) else None
    if isinstance(sid, str) and isinstance(costo, (int, float)) and costo >= 0:
        sesiones = d.get("sesiones") if isinstance(d.get("sesiones"), dict) else {}
        previo = (sesiones.get(sid) or {}).get("costo_usd", 0.0)
        delta = costo - previo if costo >= previo else costo
        if delta > 0:
            hora = time.strftime("%Y-%m-%dT%H", time.localtime(ahora))
            horas = d.get("usd_por_hora") if isinstance(d.get("usd_por_hora"), dict) else {}
            horas[hora] = round(float(horas.get(hora, 0.0)) + delta, 6)
            corte = time.strftime("%Y-%m-%dT%H", time.localtime(ahora - DIAS_COSTO * 86400))
            d["usd_por_hora"] = {k: v for k, v in horas.items() if k >= corte}
        sesiones[sid[:80]] = {"costo_usd": float(costo), "visto": ahora}
        d["sesiones"] = {k: v for k, v in sesiones.items()
                         if isinstance(v, dict) and v.get("visto", 0) > ahora - DIAS_COSTO * 86400}
    escribir_atomico(DESTINO, d)
    return d


def linea(d, ahora):
    partes = []
    for clave, rotulo in (("five_hour", "5 h"), ("seven_day", "semana")):
        v = (d.get("rate_limits") or {}).get(clave)
        if v and v["resets_at"] > ahora:
            texto = f"{rotulo}: {v['used_percentage']:.0f} %"
            if clave == "five_hour":
                texto += time.strftime(" (%H:%M)", time.localtime(v["resets_at"]))
            else:
                texto += time.strftime(" (%d/%m %H:%M)", time.localtime(v["resets_at"]))
            partes.append(texto)
    return " · ".join(partes)


def main(argv):
    crudo = sys.stdin.read()
    previo = ""
    if "--envolver" in argv and argv.index("--envolver") + 1 < len(argv):
        try:
            r = subprocess.run(argv[argv.index("--envolver") + 1], input=crudo.encode("utf-8"), shell=True,
                               capture_output=True, timeout=10)
            previo = r.stdout.decode("utf-8", errors="replace").rstrip("\n")
        except (OSError, subprocess.TimeoutExpired):
            previo = ""
    try:
        entrada = json.loads(crudo or "{}")
    except ValueError:
        entrada = {}
    ahora = time.time()
    try:
        d = actualizar(entrada if isinstance(entrada, dict) else {}, ahora)
    except OSError:
        d = {}
    salida = " | ".join(x for x in (previo, linea(d, ahora)) if x)
    # Siempre UTF-8 (en Windows la consola usaría cp1252 y "·" llegaría corrupto a Claude Code).
    sys.stdout.buffer.write((salida + "\n").encode("utf-8"))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
