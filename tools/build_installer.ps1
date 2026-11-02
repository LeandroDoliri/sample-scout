<#
Genera dist\SampleScoutSetup-<versión>.exe y dist\SampleScout-update-<versión>.zip.

Uso (desde la raíz del repo):
    powershell -ExecutionPolicy Bypass -File tools\build_installer.ps1 [-Version 0.2.0] [-Clean] [-NoSetup]

Arma build\stage con todo lo que se instala:
    python\        Python "embeddable" oficial x64 + pip + requirements.txt (pip sigue funcionando
                   para que la actualización desde la app pueda instalar dependencias nuevas)
    sample_scout\  el paquete de la app (el ._pth agrega la carpeta de la instalación al path,
                   así que los accesos directos abren "python\pythonw.exe -m sample_scout")
    icon.ico, VERSION, RUNTIME, requirements.txt
y lo empaqueta con Inno Setup (installer\SampleScout.iss). No hay lanzador .exe propio porque,
sin firma digital, el Control inteligente de aplicaciones de Windows 11 lo bloquea. Por la misma
razón, en una PC con ese control activado el Setup tampoco arranca: ahí se usa
tools\install_local.ps1.

El .zip es el paquete que la app baja del release de GitHub para actualizarse sola (ver
sample_scout\updater.py): solo los archivos de la app, más un manifest.json con la versión,
el sha256 de cada archivo y min_runtime (el valor de RUNTIME). RUNTIME se sube a mano cuando
cambia el Python de forma que la app nueva lo necesite: las instalaciones con un RUNTIME menor no
se actualizan desde el .zip y la app les pide el instalador completo.

Es x64 aunque la PC sea ARM64: numba y soxr (dependencias de librosa) no publican paquetes para
Windows ARM64, y el Python x64 corre emulado sin problema.

Necesita Inno Setup 6 (winget install JRSoftware.InnoSetup). Las descargas se guardan en
build\downloads y se reutilizan; -Clean las borra para bajar versiones nuevas.
#>
param(
    [string]$Version,   # por defecto, el contenido de VERSION
    [string]$PythonVersion = '3.14.6',
    [switch]$Clean,
    [switch]$NoSetup   # solo armar build\stage y el .zip (para tools\install_local.ps1), sin Inno Setup
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest es muy lento con la barra de progreso

$root = Split-Path $PSScriptRoot -Parent
$build = Join-Path $root 'build'
$downloads = Join-Path $build 'downloads'
$stage = Join-Path $build 'stage'
if (-not $Version) { $Version = (Get-Content "$root\VERSION" -Raw).Trim() }

if ($Clean -and (Test-Path $build)) { Remove-Item $build -Recurse -Force }
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force $downloads, $stage | Out-Null

function Get-File($url, $name) {
    $path = Join-Path $downloads $name
    if (-not (Test-Path $path)) {
        Write-Host "Descargando $url"
        Invoke-WebRequest $url -OutFile "$path.part"
        Move-Item "$path.part" $path
    }
    return $path
}

function Find-Iscc {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    $found = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $found) { throw 'No se encontró Inno Setup 6. Instalalo con: winget install JRSoftware.InnoSetup' }
    return $found
}
if (-not $NoSetup) { $iscc = Find-Iscc }

# --- Python embebido + dependencias ---
Write-Host "== Python $PythonVersion"
$pyZip = Get-File "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" "python-$PythonVersion-embed-amd64.zip"
Expand-Archive $pyZip "$stage\python"
# El Python embebido ignora site-packages salvo que se active "import site" en su ._pth, y solo
# ve las rutas que lista: ".." es la carpeta de la instalación, donde está sample_scout\
$pth = Get-ChildItem "$stage\python" -Filter 'python*._pth' | Select-Object -First 1
$lines = (Get-Content $pth.FullName) -replace '^#\s*import site', 'import site'
$lines = @($lines | Where-Object { $_ -ne 'import site' }) + '..' + 'import site'
$lines | Set-Content $pth.FullName -Encoding ascii

$py = "$stage\python\python.exe"
$getPip = Get-File 'https://bootstrap.pypa.io/get-pip.py' 'get-pip.py'
& $py $getPip --no-warn-script-location --disable-pip-version-check
if ($LASTEXITCODE) { throw 'Falló la instalación de pip' }
# El ._pth impide que pip vea el entorno de compilación aislado: si alguna dependencia viene solo
# como código fuente, se compila con el setuptools local (--no-build-isolation)
& $py -m pip install --no-warn-script-location --disable-pip-version-check setuptools wheel
if ($LASTEXITCODE) { throw 'Falló la instalación de setuptools' }
& $py -m pip install --no-warn-script-location --disable-pip-version-check --no-build-isolation -r "$root\requirements.txt"
if ($LASTEXITCODE) { throw 'Falló pip install -r requirements.txt' }

# --- La app ---
Write-Host '== App'
Copy-Item "$root\icon.ico", "$root\VERSION", "$root\RUNTIME", "$root\requirements.txt" $stage
New-Item -ItemType Directory -Force "$stage\sample_scout" | Out-Null
Get-ChildItem "$root\src\sample_scout" -Filter '*.py' | Copy-Item -Destination "$stage\sample_scout"
& $py -c "import PySide6.QtMultimedia, librosa, soundfile, sample_scout.app as a; print('dependencias OK, versión', a.__version__)"
if ($LASTEXITCODE) { throw 'La app no importa en el Python embebido' }

# --- Paquete de actualización (se sube al release junto con el Setup) ---
# Se arma con System.IO.Compression y no con Compress-Archive: el de PowerShell 5.1 guarda las
# rutas con "\" y el manifest las nombra con "/". RUNTIME no va: describe la instalación, no la app.
Write-Host '== Paquete de actualización'
New-Item -ItemType Directory -Force "$root\dist" | Out-Null
$files = @('icon.ico', 'VERSION', 'requirements.txt') +
    (Get-ChildItem "$stage\sample_scout" -File | ForEach-Object { 'sample_scout/' + $_.Name })
$hashes = [ordered]@{}
foreach ($f in $files) { $hashes[$f] = (Get-FileHash (Join-Path $stage $f) -Algorithm SHA256).Hash.ToLower() }
$manifest = [ordered]@{
    version     = $Version
    min_runtime = [int](Get-Content "$root\RUNTIME" -Raw).Trim()
    files       = $hashes
} | ConvertTo-Json -Depth 3
$updateZip = "$root\dist\SampleScout-update-$Version.zip"
if (Test-Path $updateZip) { Remove-Item $updateZip -Force }
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($updateZip, 'Create')
try {
    foreach ($f in $files) {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, (Join-Path $stage $f), $f) | Out-Null
    }
    $writer = New-Object System.IO.StreamWriter($zip.CreateEntry('manifest.json').Open(), (New-Object System.Text.UTF8Encoding $false))
    $writer.Write($manifest)
    $writer.Dispose()
} finally {
    $zip.Dispose()
}
Write-Host "Listo: $updateZip"

# Precompilar ahorra tiempo en el primer arranque (después del zip: el paquete no lleva .pyc)
& $py -m compileall -q "$stage\python\Lib\site-packages" "$stage\sample_scout" | Out-Null

if ($NoSetup) { Write-Host "Listo: $stage"; return }

# --- Instalador ---
Write-Host '== Inno Setup'
& $iscc /Q "/DAppVersion=$Version" "$root\installer\SampleScout.iss"
if ($LASTEXITCODE) { throw 'Falló Inno Setup' }

$setup = Get-Item "$root\dist\SampleScoutSetup-$Version.exe"
Write-Host ("Listo: {0} ({1:N0} MB)" -f $setup.FullName, ($setup.Length / 1MB))
