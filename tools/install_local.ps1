<#
Instala (o desinstala) Sample Scout en esta PC sin el Setup de Inno.

Hace falta en PCs con el Control inteligente de aplicaciones de Windows 11 activado: ese control
bloquea los .exe sin firma digital, incluido el Setup, pero no Python (firmado) ni este script.
Instala lo mismo que el Setup, en la misma carpeta, y lo registra en "Agregar o quitar programas".

Uso (desde la raíz del repo, después de tools\build_installer.ps1 -NoSetup):
    powershell -ExecutionPolicy Bypass -File tools\install_local.ps1 [-NoDesktop]
    powershell -ExecutionPolicy Bypass -File tools\install_local.ps1 -Uninstall
#>
param(
    [switch]$NoDesktop,
    [switch]$Uninstall
)
$ErrorActionPreference = 'Stop'

$name = 'Sample Scout'
$appId = 'LeandroDoliri.SampleScout'   # mismo AppUserModelID que la app y el Setup
$dest = Join-Path $env:LOCALAPPDATA "Programs\$name"
$regKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\SampleScout'
$shortcuts = @(
    (Join-Path ([Environment]::GetFolderPath('Programs')) "$name.lnk"),
    (Join-Path ([Environment]::GetFolderPath('Desktop')) "$name.lnk")
)

function Stop-App {
    # pythonw/python de la instalación (la app o un proceso de análisis)
    Get-Process python, pythonw -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($dest, [StringComparison]::OrdinalIgnoreCase) } |
        Stop-Process -Force
    Start-Sleep -Milliseconds 500
}

if ($Uninstall) {
    Stop-App
    $shortcuts | Where-Object { Test-Path $_ } | Remove-Item -Force
    if (Test-Path $regKey) { Remove-Item $regKey -Force }
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
    Write-Host "$name desinstalado. Tu librería (%APPDATA%\SampleScout) se conserva."
    return
}

$stage = Join-Path (Split-Path $PSScriptRoot -Parent) 'build\stage'
if (-not (Test-Path "$stage\python\pythonw.exe")) {
    throw "No existe build\stage. Generalo primero: powershell -ExecutionPolicy Bypass -File tools\build_installer.ps1 -NoSetup"
}
$version = (Get-Content "$stage\VERSION" -Raw).Trim()

Stop-App
# Python y la app se reemplazan enteros (igual que [InstallDelete] del Setup)
foreach ($dir in 'python', 'sample_scout') {
    if (Test-Path "$dest\$dir") { Remove-Item "$dest\$dir" -Recurse -Force }
}
New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item "$stage\*" $dest -Recurse -Force
Copy-Item $PSCommandPath "$dest\uninstall.ps1" -Force

# Accesos directos a pythonw.exe (firmado), con el ícono de la app
$shell = New-Object -ComObject WScript.Shell
foreach ($path in $shortcuts) {
    if ($NoDesktop -and $path -like "$([Environment]::GetFolderPath('Desktop'))*") { continue }
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = "$dest\python\pythonw.exe"
    $lnk.Arguments = '-m sample_scout'
    $lnk.WorkingDirectory = $dest
    $lnk.IconLocation = "$dest\icon.ico,0"
    $lnk.Description = 'Librería de samples que se ordena sola'
    $lnk.Save()
}

# Entrada en "Agregar o quitar programas"
New-Item $regKey -Force | Out-Null
$size = [int]((Get-ChildItem $dest -Recurse -File | Measure-Object Length -Sum).Sum / 1KB)
$values = @{
    DisplayName     = $name
    DisplayVersion  = $version
    Publisher       = 'Leandro Doliri'
    DisplayIcon     = "$dest\icon.ico"
    InstallLocation = $dest
    UninstallString = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$dest\uninstall.ps1`" -Uninstall"
}
foreach ($k in $values.Keys) { Set-ItemProperty $regKey $k $values[$k] }
Set-ItemProperty $regKey EstimatedSize $size -Type DWord
Set-ItemProperty $regKey NoModify 1 -Type DWord
Set-ItemProperty $regKey NoRepair 1 -Type DWord

Write-Host "$name $version instalado en $dest (AppUserModelID $appId)"
