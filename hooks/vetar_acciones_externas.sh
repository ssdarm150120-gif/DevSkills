#!/usr/bin/env bash

# ============================================================================
# DevSkills - Hook PreToolUse (Bash): vetos de acciones hacia afuera para subagentes
# ============================================================================
# Claude Code le pasa por la entrada estándar el evento en JSON. Si la llamada viene
# de un SUBAGENTE (el evento trae "agent_id") y el comando intenta algo que sale del
# equipo o destruye trabajo ajeno, el hook sale con código 2 y Claude Code bloquea la
# llamada, con este mensaje como motivo. El hilo principal (el orquestador, que no
# trae "agent_id") no se toca: sus acciones hacia afuera dependen de la confirmación
# explícita del usuario, que piden las skills.
#
# Vetado para subagentes:
#   git push · git branch -D · gh que escribe (issue, pr, repo, release, workflow,
#   secret, variable, run rerun/cancel/delete, api con método o campos de escritura,
#   auth token/login) · docker push/login · prune de Docker · instalaciones de software
#   (curl o wget a un shell, get-pip, pip --user o --break-system-packages, winget/brew/apt
#   install, npm -g, pip/apt/curl dentro de wsl).
#
# Sin jq: la lectura del JSON es con grep, para no añadir dependencias.
# Límite conocido: es una barrera de patrones, no un análisis completo del shell.
# Un comando que mencione estas palabras sin ejecutarlas (por ejemplo, en un mensaje
# de commit) también se bloquea para el subagente: el commit lo hace el orquestador.
# ============================================================================

set -u

entrada="$(cat)"

# Solo subagentes: el evento trae "agent_id" (con comillas sin escapar, a nivel raíz).
if ! grep -Eq '"agent_id"[[:space:]]*:[[:space:]]*"[^"]+"' <<<"$entrada"; then
  exit 0
fi

# Solo el campo "command" de la herramienta.
comando="$(grep -oE '"command"[[:space:]]*:[[:space:]]*"([^"\\]|\\.)*"' <<<"$entrada" | head -n 1 || true)"
[[ -z "$comando" ]] && exit 0

vetar_instalacion() {
  echo "DevSkills: bloqueado para subagentes (${1}). Ningún agente instala software: si falta una herramienta, detente e infórmalo en tu reporte (nombre y versión); el orquestador se lo pregunta al usuario." >&2
  exit 2
}

vetar() {
  echo "DevSkills: bloqueado para subagentes (${1}). Publicar o destruir es decisión del usuario: deja el comando propuesto en tu reporte y el orquestador lo ejecuta solo con su confirmación explícita." >&2
  exit 2
}

# Un comando git se reconoce como `git` (con o sin opciones como -C ruta) y la palabra clave después.
inicio='(^|[^[:alnum:]_./-])'
fin='([^[:alnum:]_-]|$)'

grep -Eq "${inicio}git([[:space:]]+[^|;&]*)?[[:space:]]push${fin}" <<<"$comando" && vetar "git push"
grep -Eq "${inicio}git([[:space:]]+[^|;&]*)?[[:space:]]branch[[:space:]]+[^|;&]*(-[a-zA-Z]*D|--delete[^|;&]*--force|--force[^|;&]*--delete)" <<<"$comando" && vetar "git branch -D"

grep -Eq "${inicio}gh[[:space:]]+(issue|pr|repo|release|workflow|secret|variable|label|gist|ruleset|codespace|cache|extension|project)[[:space:]]+(create|comment|edit|close|reopen|delete|merge|review|ready|lock|unlock|transfer|pin|unpin|develop|fork|rename|archive|unarchive|sync|set-default|deploy-key|add|remove|set|enable|disable|run|upload|import|install|upgrade|link|unlink|copy|field-create|field-delete|item-add|item-create|item-delete|item-edit|item-archive|mark-template)${fin}" <<<"$comando" && vetar "gh de escritura"
grep -Eq "${inicio}gh[[:space:]]+run[[:space:]]+(rerun|cancel|delete)${fin}" <<<"$comando" && vetar "gh run rerun/cancel/delete"
grep -Eq "${inicio}gh[[:space:]]+auth[[:space:]]+(token|login|refresh|setup-git|logout)${fin}" <<<"$comando" && vetar "gh auth"
grep -Eq "${inicio}gh[[:space:]]+api[[:space:]]" <<<"$comando" && \
  grep -Eq "(-X|--method)[[:space:]=]*(POST|PUT|PATCH|DELETE)|[[:space:]](-f|-F|--field|--raw-field|--input)[[:space:]=]" <<<"$comando" && vetar "gh api de escritura"

grep -Eq "${inicio}docker([[:space:]]+[^|;&]*)?[[:space:]](push|login)${fin}" <<<"$comando" && vetar "docker push/login"
grep -Eq "${inicio}docker[[:space:]]+(system|volume|network|image|container|builder)[[:space:]]+prune${fin}" <<<"$comando" && vetar "docker prune"

# Instalaciones de software: nadie instala nada sin que el usuario lo autorice (lo pregunta el orquestador).
grep -Eq "${inicio}(curl|wget)[[:space:]][^;&]*\|[[:space:]]*(sudo[[:space:]]+)?(ba|z|da)?sh${fin}" <<<"$comando" && vetar_instalacion "curl o wget hacia un shell"
grep -Eq "${inicio}(curl|wget)[[:space:]][^|;&]*get-pip" <<<"$comando" && vetar_instalacion "descarga de get-pip"
grep -Eq "${inicio}python[0-9.]*[[:space:]]+[^|;&]*get-pip" <<<"$comando" && vetar_instalacion "get-pip"
grep -Eq "${inicio}winget[[:space:]]+(install|upgrade)${fin}" <<<"$comando" && vetar_instalacion "winget install"
grep -Eq "${inicio}brew[[:space:]]+(install|reinstall|upgrade|tap)${fin}" <<<"$comando" && vetar_instalacion "brew install"
grep -Eq "${inicio}apt(-get)?[[:space:]]+([^|;&]*[[:space:]])?install${fin}" <<<"$comando" && vetar_instalacion "apt install"
grep -Eq "${inicio}npm[[:space:]]+(i|install|add)[[:space:]]+([^|;&]*[[:space:]])?(-g|--global)${fin}" <<<"$comando" && vetar_instalacion "npm install -g"
grep -Eq "${inicio}pip[0-9.]*[[:space:]]+install[[:space:]]+[^|;&]*(--user|--break-system-packages)" <<<"$comando" && vetar_instalacion "pip install fuera de un venv"
grep -Eq "${inicio}wsl([[:space:]]+[^|;&]*)?[[:space:]](pip[0-9.]*|apt(-get)?|curl|wget|sudo)${fin}" <<<"$comando" && vetar_instalacion "instalación dentro de WSL"

exit 0
