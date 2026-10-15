# ============================================================================
# DevSkills - Desinstalador para PowerShell (Windows)
# ============================================================================
# Quita EXACTAMENTE lo que registró el instalador en su manifiesto (agentes,
# skills y CLI) y la carpeta de la carga útil. No toca nada más.
# Uso: powershell -ExecutionPolicy Bypass -File uninstall.ps1
# ============================================================================

$ErrorActionPreference = 'Stop'

$Inicio = if ($env:HOME) { $env:HOME } else { $env:USERPROFILE }
$ShareDir = if ($env:DEVSKILLS_SHARE_DIR) { $env:DEVSKILLS_SHARE_DIR } else { Join-Path $Inicio 'bin\lib\devskills' }
$Manifiesto = Join-Path $ShareDir 'manifiesto.txt'

Write-Host ""
Write-Host "  DevSkills - Desinstalador" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $Manifiesto) -or -not (Test-Path (Join-Path $ShareDir '.devskills'))) {
    Write-Host "DevSkills no esta instalado con el instalador (no existe $Manifiesto)." -ForegroundColor Yellow
    Write-Host "  Si lo instalaste como plugin: /plugin uninstall devskills@devskills-local"
    exit 0
}

$quitados = 0
foreach ($archivo in Get-Content -Encoding UTF8 $Manifiesto) {
    if (-not $archivo) { continue }
    # Solo se quita lo que tiene aspecto de DevSkills: un manifiesto alterado no borra archivos ajenos.
    $nombreArchivo = Split-Path -Leaf $archivo
    if (-not ((($archivo -replace '\\', '/') -like '*/devskills-*') -or $nombreArchivo -eq 'devskills' -or $nombreArchivo -eq 'devskills.cmd')) { continue }
    if (Test-Path -PathType Leaf -LiteralPath $archivo) {
        [IO.File]::Delete($archivo)
        $quitados++
    }
    # Borra carpetas que quedaron vacías, subiendo solo hasta la raíz de la skill (skills/devskills-<nombre>).
    $dir = Split-Path -Parent $archivo
    $raiz = $null
    if (($archivo -replace '\\', '/') -match '^(.*/skills/devskills-[^/]+)/.+') { $raiz = $Matches[1] }
    while ($raiz -and $dir -and ((($dir -replace '\\', '/') -eq $raiz) -or (($dir -replace '\\', '/').StartsWith("$raiz/"))) -and (Test-Path -LiteralPath $dir) -and -not (Get-ChildItem -Force -LiteralPath $dir)) {
        [IO.Directory]::Delete($dir)
        $dir = Split-Path -Parent $dir
    }
}

[IO.Directory]::Delete($ShareDir, $true)
Write-Host "Quitados $quitados archivos y $ShareDir." -ForegroundColor Green
Write-Host ""
Write-Host "Nota: los proyectos creados con 'devskills init' no se tocan."
Write-Host ""
