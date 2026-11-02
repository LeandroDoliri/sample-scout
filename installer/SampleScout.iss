; Instalador de Sample Scout (Inno Setup 6). No se compila a mano:
; tools/build_installer.ps1 prepara build\stage y llama a ISCC con /DAppVersion.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppName "Sample Scout"
; Igual que APP_USER_MODEL_ID en sample_scout/app.py: así la ventana y el acceso directo
; son la misma app en la barra de tareas (anclar funciona bien)
#define AppUserModelID "LeandroDoliri.SampleScout"

[Setup]
AppId={{9E4B2C71-5D3A-4F86-B1C9-7A2E8D0F4B63}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Leandro Doliri
AppPublisherURL=https://github.com/LeandroDoliri/sample-scout
; Carpeta del usuario, sin permisos de administrador: así la app puede actualizarse sola
; (reemplazar sus archivos y correr pip dentro de la instalación)
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=..\dist
OutputBaseFilename=SampleScoutSetup-{#AppVersion}
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\icon.ico
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Al actualizar, reemplazar el Python y la app enteros (evita archivos viejos mezclados con los nuevos)
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\sample_scout"

[Files]
Source: "..\build\stage\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Sin lanzador propio: un .exe sin firmar lo bloquea el Control inteligente de aplicaciones
; de Windows 11. pythonw.exe está firmado por la Python Software Foundation.
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m sample_scout"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; AppUserModelID: "{#AppUserModelID}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m sample_scout"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; AppUserModelID: "{#AppUserModelID}"; Tasks: desktopicon

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-m sample_scout"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; pip y numba crean archivos después de instalar (actualizaciones, cachés): borrar todo.
; La librería (%APPDATA%\SampleScout) no se toca.
Type: filesandordirs; Name: "{app}"
