; Inno Setup script — OBS Automation Manager
; Instalador per-user (NO requiere admin / UAC).
; Compilar con:
;   ISCC.exe /DMyAppVersion=1.2.3 /DMyAppVersionNumeric=1.2.3 installer.iss
; Para prereleases:
;   ISCC.exe /DMyAppVersion=1.2.3-test /DMyAppVersionNumeric=1.2.3 installer.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

; VersionInfoVersion (Windows file metadata) requiere formato numerico x.y.z[.w].
; Si no se pasa por CLI, se deriva del MyAppVersion asumiendo que no tiene sufijo.
#ifndef MyAppVersionNumeric
  #define MyAppVersionNumeric MyAppVersion
#endif

#define MyAppName        "OBS Automation Manager"
#define MyAppPublisher   "Division de Ingenieria - ACP"
#define MyAppExeName     "OBS_Automation_Manager.exe"
#define MyAppId          "{{7B4E9C2A-3F1D-4A5B-8C6E-2D9F1A0B4E5C}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersionNumeric}

; Instalación per-user, sin admin:
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; {autopf} = %LOCALAPPDATA%\Programs en modo per-user (sin admin)
DefaultDirName={autopf}\OBS_Automation_Manager
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto

; Nombre del instalador de salida incluye la versión
OutputDir=Output
OutputBaseFilename=OBS_Automation_Manager_Setup_v{#MyAppVersion}

SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copia todo el contenido de dist\OBS_Automation_Manager\ (salida --onedir de PyInstaller)
Source: "dist\OBS_Automation_Manager\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

; NOTA: intencionalmente NO borramos %LOCALAPPDATA%\OBS_Automation_Manager\ en el desinstalador
; para preservar la base de datos (obs_manager.db), logs y .env entre upgrades / reinstalaciones.
