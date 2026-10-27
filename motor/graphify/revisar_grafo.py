"""Revisa los archivos de un grafo de Graphify antes de versionarlos.

Busca literales que no deben salir del equipo: correos, IPs, cadenas de
conexión, contraseñas, tokens y rutas absolutas del usuario. Imprime cada
hallazgo con su contexto y sale con código 1 si encontró algo.

Uso:
    python revisar_grafo.py <carpeta graphify-out> [--permitir REGEX ...]

`--permitir` acepta expresiones que se consideran falsos positivos conocidos
(por ejemplo, un dominio de ejemplo en la documentación).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PATRONES = {
    "correo": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}",
    "ipv4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "url_con_credenciales": r"[a-z][a-z0-9+.-]*://[^\s/:@\"']+:[^\s/@\"']+@",
    "cadena_conexion": r"(?i)\b(?:server|data source|user id|uid|pwd|password|initial catalog|database)\s*=\s*[^;\"'\s]+;",
    "url_bd": r"(?i)\b(?:mysql|postgres(?:ql)?|mssql|sqlserver|mongodb(?:\+srv)?|redis|hana|amqp)://[^\s\"']+",
    "asignacion_secreto": r"(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|token|client_secret)\b\s*[:=]\s*[\"'][^\"']{4,}[\"']",
    "token_github": r"\b(?:ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{20,}",
    "token_openai_anthropic": r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}",
    "aws_key": r"\bAKIA[0-9A-Z]{16}\b",
    "jwt": r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "slack": r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    "llave_privada": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "host_interno": r"(?i)\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:local|internal|corp|lan|intranet)\b",
    "ruta_usuario": r"(?i)[a-z]:[\\/]+users[\\/]+[^\\/\"'\s]+|/home/[^/\"'\s]+",
    "ruta_worktree": r"-wt-graphify",
}

ARCHIVOS = ("graph.json", "GRAPH_REPORT.md", "graph.html")


def revisar(carpeta: Path, permitidos: list[re.Pattern]) -> int:
    total = 0
    for nombre in ARCHIVOS:
        ruta = carpeta / nombre
        if not ruta.is_file():
            continue
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        # graph.html incrusta bibliotecas JS (vis-network): solo se revisan
        # los datos del grafo, que son los mismos de graph.json.
        for clave, patron in PATRONES.items():
            vistos: set[str] = set()
            for m in re.finditer(patron, texto):
                valor = m.group(0)
                if valor in vistos or any(p.search(valor) for p in permitidos):
                    continue
                if clave == "ipv4" and _no_es_ip(valor):
                    continue
                vistos.add(valor)
                ini = max(0, m.start() - 60)
                ctx = texto[ini:m.end() + 60].replace("\n", " ")
                print(f"[{nombre}] {clave}: {valor!r}\n    ...{ctx}...")
                total += 1
    return total


def _no_es_ip(valor: str) -> bool:
    partes = [int(p) for p in valor.split(".")]
    if any(p > 255 for p in partes):
        return True
    # Versiones de paquetes (1.2.3.4) y similares con ceros iniciales son ruido.
    return partes[0] == 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    carpeta = Path(sys.argv[1])
    permitidos: list[re.Pattern] = []
    if "--permitir" in sys.argv:
        idx = sys.argv.index("--permitir")
        permitidos = [re.compile(p) for p in sys.argv[idx + 1:]]
    n = revisar(carpeta, permitidos)
    print(f"Hallazgos: {n}")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
