# ============================================================================
# DevSkills - Instalador para PowerShell (Windows)
# ============================================================================
# Equivalente a install.sh: copia agentes y skills a ~/.claude con el prefijo
# "devskills-", deja la carga útil en una carpeta propia, instala el CLI
# `devskills` (Bash, con un lanzador .cmd para PowerShell/cmd; requiere Git Bash)
# y registra cada archivo en un manifiesto para uninstall.ps1 / uninstall.sh.
#
# Uso: powershell -ExecutionPolicy Bypass -File install.ps1 [-Si] [-Forzar]
# Variables: CLAUDE_CONFIG_DIR, DEVSKILLS_BIN_DIR, DEVSKILLS_SHARE_DIR
# ============================================================================

[CmdletBinding()]
param(
    [switch]$Si,
    [switch]$Forzar
)

$ErrorActionPreference = 'Stop'
$Utf8SinBom = New-Object System.Text.UTF8Encoding($false)

function Convertir-Portable([string]$Ruta) { return ($Ruta -replace '\\', '/') }

$Origen = Split-Path -Parent $MyInvocation.MyCommand.Path
$Inicio = if ($env:HOME) { $env:HOME } else { $env:USERPROFILE }
$ClaudeDir = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $Inicio '.claude' }
$BinDir = if ($env:DEVSKILLS_BIN_DIR) { $env:DEVSKILLS_BIN_DIR } else { Join-Path $Inicio 'bin' }
$ShareDir = if ($env:DEVSKILLS_SHARE_DIR) { $env:DEVSKILLS_SHARE_DIR } else { Join-Path $Inicio 'bin\lib\devskills' }
$Manifiesto = Join-Path $ShareDir 'manifiesto.txt'
$Marca = Join-Path $ShareDir '.devskills'

# Las rutas se escriben dentro de las skills y del CLI instalados y en el manifiesto (una por linea).
# Se rechazan las que no se pueden incrustar sin riesgo: caracteres de control y `$`, comillas dobles o
# acento grave, que un shell interpretaria al correr los comandos de las skills.
function Validar-Ruta([string]$Nombre, [string]$Ruta) {
    if ($Ruta -match '[\x00-\x1F\x7F]') {
        [Console]::Error.WriteLine("$Nombre lleva un salto de linea o un caracter de control; elige otra ruta.")
        exit 2
    }
    if ($Ruta.Contains('$') -or $Ruta.Contains('"') -or $Ruta.Contains('`')) {
        [Console]::Error.WriteLine("$Nombre ($Ruta) lleva dolar, comillas dobles o acento grave, que no se pueden incrustar con seguridad en las skills; elige otra ruta.")
        exit 2
    }
}
Validar-Ruta 'La carpeta de la carga util' $ShareDir
Validar-Ruta 'La carpeta del CLI' $BinDir
Validar-Ruta 'La carpeta de Claude' $ClaudeDir
Validar-Ruta 'La carpeta de origen' $Origen

$Plugin = Get-Content -Raw -Encoding UTF8 (Join-Path $Origen '.claude-plugin\plugin.json') | ConvertFrom-Json
$Version = $Plugin.version

Write-Host ""
Write-Host "  DevSkills $Version - Instalador" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Agentes y skills: $ClaudeDir"
Write-Host "  CLI: $BinDir\devskills"
Write-Host "  Carga util: $ShareDir"
Write-Host ""

if ((Test-Path $ShareDir) -and -not (Test-Path $Marca)) {
    Write-Error "$ShareDir existe y no es una instalacion de DevSkills. No lo toco."
    exit 1
}

$Propios = @()
if (Test-Path $Manifiesto) {
    $Propios = @(Get-Content -Encoding UTF8 $Manifiesto | Where-Object { $_ })
    if (-not $Si) {
        if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
            $respuesta = Read-Host "DevSkills ya esta instalado. Reinstalar? (s/N)"
            if ($respuesta -notin @('s', 'S')) { Write-Host "Cancelado."; exit 0 }
        } else {
            Write-Host "DevSkills ya esta instalado; reinstalando..." -ForegroundColor Yellow
        }
    }
}

# Plan de instalación: origen, destino, tipo, nombre.
$Plan = @()
foreach ($agente in Get-ChildItem (Join-Path $Origen 'agents') -Filter '*.md') {
    $nombre = $agente.BaseName
    $Plan += [pscustomobject]@{ Origen = $agente.FullName; Destino = (Join-Path $ClaudeDir "agents\devskills-$nombre.md"); Tipo = 'agente'; Nombre = $nombre }
}
foreach ($dirSkill in Get-ChildItem (Join-Path $Origen 'skills') -Directory) {
    $nombre = $dirSkill.Name
    foreach ($archivo in Get-ChildItem $dirSkill.FullName -Recurse -File) {
        $relativo = $archivo.FullName.Substring($dirSkill.FullName.Length).TrimStart('\', '/')
        $Plan += [pscustomobject]@{ Origen = $archivo.FullName; Destino = (Join-Path $ClaudeDir "skills\devskills-$nombre\$relativo"); Tipo = 'skill'; Nombre = $nombre }
    }
}
$Plan += [pscustomobject]@{ Origen = (Join-Path $Origen 'bin\devskills'); Destino = (Join-Path $BinDir 'devskills'); Tipo = 'cli'; Nombre = 'devskills' }
$Plan += [pscustomobject]@{ Origen = ''; Destino = (Join-Path $BinDir 'devskills.cmd'); Tipo = 'lanzador'; Nombre = 'devskills.cmd' }

$Choques = @($Plan | Where-Object { (Test-Path -LiteralPath $_.Destino) -and ($Propios -notcontains (Convertir-Portable $_.Destino)) } | ForEach-Object { $_.Destino })
if ($Choques.Count -gt 0 -and -not $Forzar) {
    Write-Host "Estos archivos existen y no los instalo DevSkills:" -ForegroundColor Yellow
    $Choques | ForEach-Object { Write-Host "   $_" }
    if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        $respuesta = Read-Host "Sobrescribirlos? (s/N)"
        if ($respuesta -notin @('s', 'S')) { Write-Host "Cancelado: no se instalo nada."; exit 1 }
    } else {
        Write-Error "Cancelado: no se instalo nada. Usa -Forzar si de verdad quieres sobrescribirlos."
        exit 1
    }
}

# Carga útil: se reemplaza completa (es nuestra, lo garantiza la marca).
if (Test-Path -LiteralPath $ShareDir) { [IO.Directory]::Delete($ShareDir, $true) }
New-Item -ItemType Directory -Force $ShareDir | Out-Null
foreach ($elemento in '.claude-plugin', 'agents', 'skills', 'plantillas', 'scripts', 'bin', 'motor', 'LICENSE', 'README.md', 'CHANGELOG.md') {
    $ruta = Join-Path $Origen $elemento
    if (Test-Path $ruta) { Copy-Item -Recurse -Force $ruta $ShareDir }
}
New-Item -ItemType File -Force $Marca | Out-Null
if (Test-Path (Join-Path $Origen '.git')) {
    [IO.File]::WriteAllText((Join-Path $ShareDir '.origen'), (Convertir-Portable $Origen) + "`n", $Utf8SinBom)
}
$SharePortable = Convertir-Portable $ShareDir

function Adaptar([string]$Texto, [string]$Nombre, [string]$DirSkill) {
    $Texto = $Texto.Replace('${CLAUDE_PLUGIN_ROOT}', $SharePortable)
    $Texto = [regex]::Replace($Texto, 'devskills:([a-z])', 'devskills-$1')
    $Texto = [regex]::Replace($Texto, "(?m)^name: $([regex]::Escape($Nombre))\r?$", "name: devskills-$Nombre")
    if ($DirSkill) { $Texto = $Texto.Replace('${CLAUDE_SKILL_DIR}', "$SharePortable/skills/$DirSkill") }
    return $Texto
}

$Nuevos = @()
foreach ($e in $Plan) {
    New-Item -ItemType Directory -Force (Split-Path -Parent $e.Destino) | Out-Null
    switch ($e.Tipo) {
        'agente' {
            $texto = [IO.File]::ReadAllText($e.Origen, $Utf8SinBom)
            [IO.File]::WriteAllText($e.Destino, (Adaptar $texto $e.Nombre ''), $Utf8SinBom)
        }
        'skill' {
            if ($e.Origen -like '*.md') {
                $texto = [IO.File]::ReadAllText($e.Origen, $Utf8SinBom)
                [IO.File]::WriteAllText($e.Destino, (Adaptar $texto $e.Nombre $e.Nombre), $Utf8SinBom)
            } else {
                Copy-Item -Force $e.Origen $e.Destino
            }
        }
        'cli' {
            $texto = [IO.File]::ReadAllText($e.Origen, $Utf8SinBom) -replace "`r`n", "`n"
            $texto = [regex]::Replace($texto, '(?m)^DEVSKILLS_HOME=.*$', ('DEVSKILLS_HOME="${DEVSKILLS_HOME:-$(printf ''%s'' ''' + $SharePortable.Replace("'", "'\''") + ''')}"'))
            $texto = [regex]::Replace($texto, '(?m)^VERSION=.*$', ('VERSION="${DEVSKILLS_VERSION:-' + $Version + '}"'))
            [IO.File]::WriteAllText($e.Destino, $texto, $Utf8SinBom)
        }
        'lanzador' {
            $cmd = "@echo off`r`nwhere bash >nul 2>nul`r`nif errorlevel 1 (`r`n  echo devskills necesita Git Bash en el PATH: https://git-scm.com/download/win`r`n  exit /b 1`r`n)`r`nbash `"%~dp0devskills`" %*`r`n"
            [IO.File]::WriteAllText($e.Destino, $cmd, (New-Object System.Text.ASCIIEncoding))
        }
    }
    $Nuevos += (Convertir-Portable $e.Destino)
}

# Quita lo que la instalación anterior puso y esta ya no trae.
# Solo toca entradas con aspecto de DevSkills (devskills-*, o el CLI): un manifiesto alterado no borra archivos ajenos.
foreach ($viejo in $Propios) {
    $nombreViejo = Split-Path -Leaf $viejo
    if (-not (($viejo -like '*/devskills-*') -or $nombreViejo -eq 'devskills' -or $nombreViejo -eq 'devskills.cmd')) { continue }
    if ($Nuevos -notcontains $viejo) {
        if (Test-Path -LiteralPath $viejo) { [IO.File]::Delete($viejo) }
        $dir = Split-Path -Parent $viejo
        # Solo sube hasta la raíz de la skill (skills/devskills-<nombre>), nunca por encima.
        $raiz = $null
        if (($viejo -replace '\\', '/') -match '^(.*/skills/devskills-[^/]+)/.+') { $raiz = $Matches[1] }
        while ($raiz -and $dir -and ((($dir -replace '\\', '/') -eq $raiz) -or (($dir -replace '\\', '/').StartsWith("$raiz/"))) -and (Test-Path -LiteralPath $dir) -and -not (Get-ChildItem -Force -LiteralPath $dir)) {
            [IO.Directory]::Delete($dir)
            $dir = Split-Path -Parent $dir
        }
    }
}
[IO.File]::WriteAllText($Manifiesto, (($Nuevos -join "`n") + "`n"), $Utf8SinBom)

Write-Host "DevSkills $Version instalado ($($Nuevos.Count) archivos registrados en $Manifiesto)." -ForegroundColor Green
Write-Host ""
if (($env:PATH -split ';') -notcontains $BinDir) {
    Write-Host "$BinDir no esta en tu PATH. Agregalo (una vez):" -ForegroundColor Yellow
    Write-Host "  [Environment]::SetEnvironmentVariable('PATH', `"$BinDir;`" + [Environment]::GetEnvironmentVariable('PATH','User'), 'User')"
    Write-Host ""
}
Write-Host "Para empezar:"
Write-Host "  devskills doctor"
Write-Host "  devskills init C:\proyectos\mi-sistema --nombre `"Mi sistema`""
Write-Host "  Motor grafico (opcional): devskills motor iniciar ; devskills motor enganchar ; devskills panel"
Write-Host "  En Claude Code, los agentes y skills se llaman devskills-<nombre> (por ejemplo, /devskills-ciclo HU-01)."
Write-Host ""
