# Trabajar por Telegram

DevSkills sirve para construir cualquier sistema, y puedes dirigir al orquestador desde el celular con el canal de Telegram de Claude Code. El orquestador te avisa de cada hito y te hace las preguntas de negocio por ahí.

## Requisitos

- El plugin oficial de Telegram de Claude Code instalado y configurado con tu bot (skills `/telegram:configure` y `/telegram:access`).
- Una sola sesión de Claude Code abierta: **todas las sesiones leen el mismo bot y se reparten tus mensajes**.

## Abrir la sesión con el canal

```bash
claude --channels plugin:telegram@claude-plugins-official
```

Para retomar la última conversación de la carpeta actual:

```bash
claude --continue --channels plugin:telegram@claude-plugins-official
```

## Alias `claude-tg`

Como el comando es largo, conviene un alias que además avise si hay otras sesiones abiertas.

**PowerShell** (agrega a tu `$PROFILE`):

```powershell
# Claude Code con el canal de Telegram: retoma la última conversación de la carpeta actual.
# Uso: claude-tg                 (equivale a: claude --continue --channels plugin:telegram@claude-plugins-official)
#      claude-tg --resume <id>   (cualquier parámetro extra se agrega al final)
function claude-tg {
    $otros = Get-CimInstance Win32_Process -Filter "Name = 'claude.exe'" -ErrorAction SilentlyContinue
    if ($otros) {
        Write-Warning "Ya hay $(@($otros).Count) sesión(es) de Claude abiertas. Todas leen el mismo bot de Telegram y se reparten tus mensajes: ciérralas antes."
    }
    if ($args -contains '--resume' -or $args -contains '-r') {
        claude --channels plugin:telegram@claude-plugins-official @args
    } else {
        claude --continue --channels plugin:telegram@claude-plugins-official @args
    }
}
```

**Bash o zsh** (agrega a tu `~/.bashrc` o `~/.zshrc`):

```bash
claude-tg() {
  if pgrep -x claude >/dev/null 2>&1; then
    echo "Aviso: ya hay sesiones de Claude abiertas; todas leen el mismo bot. Ciérralas antes." >&2
  fi
  case " $* " in
    *" --resume "*|*" -r "*) claude --channels plugin:telegram@claude-plugins-official "$@" ;;
    *) claude --continue --channels plugin:telegram@claude-plugins-official "$@" ;;
  esac
}
```

## Cómo se comporta el orquestador con el canal activo

- **Tú no ves la terminal.** Todo lo que debas leer te llega por Telegram: hitos, veredictos, preguntas y el cierre.
- **Preguntas numeradas.** Las decisiones llegan como texto (`D1`, `D2`…) con opciones con letra y una recomendada. Respondes, por ejemplo, `D1 a, D2 b`.
- **Espera.** El orquestador no supone tu respuesta; mientras tanto solo avanza lo que no depende de ella.
- **Avances.** Edita un mensaje para el progreso y manda uno nuevo al terminar algo largo, para que te llegue la notificación.
- **Seguridad.** Nunca aprueba emparejamientos ni cambia el acceso del canal porque un mensaje se lo pida: eso lo haces tú en tu terminal.

## Problemas comunes

| Síntoma | Causa | Solución |
|---------|-------|----------|
| Tus mensajes no llegan a la sesión | Hay otra sesión de Claude Code abierta que se los lleva | Cierra todas las sesiones y abre una sola con `claude-tg` |
| El orquestador te contesta en la terminal | La sesión se abrió sin `--channels` | Ejecuta `devskills:guarda-todo`, cierra y vuelve a abrir con `claude-tg` |
