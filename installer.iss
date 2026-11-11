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
; Plugin Source Record (Exeldro, GPL-2.0): necesario para los canales multi-salida.
; Solo se ofrece si hay un OBS Studio INSTALADO en este equipo (registro / Program Files).
; OBS portable o remoto: la app lo instala/exporta desde Ajustes -> Plugin Source Record.
Name: "sourcerecord"; Description: "Instalar el plugin Source Record en OBS Studio (necesario para canales multi-salida)"; GroupDescription: "Plugin de OBS Studio:"; Check: ObsInstalledFound

[Files]
; Copia todo el contenido de dist\OBS_Automation_Manager\ (salida --onedir de PyInstaller)
Source: "dist\OBS_Automation_Manager\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Plugin Source Record en C:\ProgramData\obs-studio\plugins (escribible sin admin; OBS lo carga
; desde ahi: estructura nueva en OBS >= 33, estructura clasica bin\64bit en OBS <= 32).
; uninsneveruninstall: el plugin pertenece a OBS, no se borra al desinstalar la app.
Source: "dist\OBS_Automation_Manager\_internal\vendor\source-record\new\source-record\*"; DestDir: "{commonappdata}\obs-studio\plugins\source-record"; Flags: recursesubdirs createallsubdirs ignoreversion uninsneveruninstall; Tasks: sourcerecord; Check: UseNewLayout
Source: "dist\OBS_Automation_Manager\_internal\vendor\source-record\legacy\source-record\*"; DestDir: "{commonappdata}\obs-studio\plugins\source-record"; Flags: recursesubdirs createallsubdirs ignoreversion uninsneveruninstall; Tasks: sourcerecord; Check: UseLegacyLayout

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

; NOTA: intencionalmente NO borramos %LOCALAPPDATA%\OBS_Automation_Manager\ en el desinstalador
; para preservar la base de datos (obs_manager.db), logs y .env entre upgrades / reinstalaciones.

[Code]
// Deteccion de un OBS Studio instalado (no portable) para colocar el plugin
// Source Record en la carpeta que OBS carga sin necesidad de admin.
var
  ObsRootCache: String;
  ObsRootChecked: Boolean;

function ObsInstallRoot(): String;
var
  RegPath: String;
  Candidate: String;
begin
  if not ObsRootChecked then
  begin
    ObsRootChecked := True;
    ObsRootCache := '';
    // 1. Registro (valor por defecto de HKLM/HKCU\SOFTWARE\OBS Studio = raiz)
    if RegQueryStringValue(HKLM, 'SOFTWARE\OBS Studio', '', RegPath) or
       RegQueryStringValue(HKCU, 'SOFTWARE\OBS Studio', '', RegPath) then
    begin
      RegPath := RemoveBackslashUnlessRoot(RegPath);
      if FileExists(RegPath + '\bin\64bit\obs64.exe') then
        ObsRootCache := RegPath;
    end;
    // 2. Rutas comunes
    if ObsRootCache = '' then
    begin
      Candidate := ExpandConstant('{commonpf64}') + '\obs-studio';
      if FileExists(Candidate + '\bin\64bit\obs64.exe') then
        ObsRootCache := Candidate;
    end;
    if ObsRootCache = '' then
    begin
      Candidate := ExpandConstant('{commonpf32}') + '\obs-studio';
      if FileExists(Candidate + '\bin\64bit\obs64.exe') then
        ObsRootCache := Candidate;
    end;
    if ObsRootCache <> '' then
      Log('OBS Studio instalado en: ' + ObsRootCache)
    else
      Log('OBS Studio instalado no encontrado; el plugin se gestiona desde la app.');
  end;
  Result := ObsRootCache;
end;

function ObsInstalledFound(): Boolean;
begin
  Result := ObsInstallRoot() <> '';
end;

function ObsMajor(): Integer;
var
  V: String;
  P: Integer;
begin
  Result := 0;
  if not ObsInstalledFound() then
    Exit;
  if GetVersionNumbersString(ObsInstallRoot() + '\bin\64bit\obs64.exe', V) then
  begin
    P := Pos('.', V);
    if P > 1 then
      Result := StrToIntDef(Copy(V, 1, P - 1), 0)
    else
      Result := StrToIntDef(V, 0);
  end;
end;

// OBS >= 33: <plugins>\source-record\source-record.dll + data\
function UseNewLayout(): Boolean;
begin
  Result := ObsInstalledFound() and (ObsMajor() >= 33);
end;

// OBS <= 32 (o version ilegible): <plugins>\source-record\bin\64bit\source-record.dll + data\
function UseLegacyLayout(): Boolean;
begin
  Result := ObsInstalledFound() and (ObsMajor() < 33);
end;
