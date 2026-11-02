<#
Publica la versión de VERSION como release de GitHub: compila el instalador y el paquete de
actualización y los sube. Las instalaciones existentes ven la versión nueva al abrir la app.

Uso (desde la raíz del repo, con main al día con origin, VERSION ya subido y la entrada
"## [X.Y.Z]" escrita en CHANGELOG.md):
    powershell -ExecutionPolicy Bypass -File tools\release.ps1 [-Notes "Qué cambió"]

Las notas del release salen de esa sección de CHANGELOG.md; -Notes las reemplaza.

Sube dos assets al release vX.Y.Z:
    SampleScoutSetup.exe            sin versión en el nombre: el README enlaza
                                    releases/latest/download/SampleScoutSetup.exe
    SampleScout-update-X.Y.Z.zip    el paquete que usa la actualización desde la app
#>
param(
    [string]$Notes   # por defecto, la sección de la versión en CHANGELOG.md
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    $version = (Get-Content VERSION -Raw).Trim()
    $tag = "v$version"

    if (git status --porcelain) { throw 'Hay cambios sin commitear: commitealos antes de publicar.' }
    if ((git rev-parse --abbrev-ref HEAD) -ne 'main') { throw 'Publicá desde main.' }
    git fetch -q origin main
    if ((git rev-parse HEAD) -ne (git rev-parse origin/main)) { throw 'main no coincide con origin/main: hacé push (o pull) primero.' }
    # Sin "gh release view": en PowerShell 5.1 su stderr ("release not found") corta el script
    $existing = gh release list --limit 200 --json tagName --jq '.[].tagName'
    if ($LASTEXITCODE) { throw 'No se pudo consultar GitHub con gh (¿gh auth login?).' }
    if ($existing -contains $tag) { throw "El release $tag ya existe: subí el número en VERSION." }

    if (-not $Notes) {
        # Todo lo que hay entre "## [X.Y.Z]" y el siguiente "## [" de CHANGELOG.md
        $changelog = Get-Content CHANGELOG.md -Raw -Encoding UTF8
        $pattern = '(?ms)^## \[' + [regex]::Escape($version) + '\][^\r\n]*\r?\n(.*?)(?=^## \[|\z)'
        $match = [regex]::Match($changelog, $pattern)
        if (-not $match.Success -or -not $match.Groups[1].Value.Trim()) {
            throw "Falta la entrada ## [$version] en CHANGELOG.md."
        }
        $Notes = $match.Groups[1].Value.Trim()
    }

    & "$PSScriptRoot\build_installer.ps1" -Version $version
    Copy-Item "dist\SampleScoutSetup-$version.exe" 'dist\SampleScoutSetup.exe' -Force

    $assets = @('dist\SampleScoutSetup.exe', "dist\SampleScout-update-$version.zip")
    # Por archivo y no por --notes: así los saltos de línea y acentos llegan intactos
    $notesFile = Join-Path $env:TEMP "sample-scout-notes-$version.md"
    [IO.File]::WriteAllText($notesFile, $Notes, (New-Object Text.UTF8Encoding $false))
    gh release create $tag @assets --target main --title "Sample Scout $version" --notes-file $notesFile
    if ($LASTEXITCODE) { throw 'Falló gh release create' }
    Remove-Item $notesFile -ErrorAction SilentlyContinue
    git fetch -q --tags
    Write-Host "Publicado: Sample Scout $version"
} finally {
    Pop-Location
}
