<#
.SYNOPSIS
  Diagnostico de escenas de video en negro en un equipo cliente (solo lectura).

.DESCRIPTION
  No necesita Python ni la app. Lee la coleccion de escenas de OBS Studio
  (instalado o portable), localiza cada fuente de video (ffmpeg_source) e
  imagen (image_source) y comprueba el archivo:
    - existe en ESTE equipo (las escenas importadas desde otra PC traen la
      ruta de la otra PC),
    - no es un marcador de OneDrive "solo en la nube" (OBS no puede leerlo),
    - tamano real en disco,
    - cabecera MP4/MKV valida.
  Despues busca en el ultimo log de OBS errores de apertura/decodificacion y
  de texturas D3D11, y en el log de la app las ultimas lineas relevantes.

.USO (en el equipo cliente, PowerShell normal, sin admin)
  powershell -ExecutionPolicy Bypass -File diagnose_client_media.ps1
  powershell -ExecutionPolicy Bypass -File diagnose_client_media.ps1 -ObsRoot "D:\OBSPortable\obs-studio"

  Pega la salida completa al reportar.
#>
param(
    [string]$ObsRoot = ""
)

$ErrorActionPreference = "Continue"
function Section($t) { ""; "=== $t ==="; }

Section "Equipo"
"Usuario: $env:USERNAME  Equipo: $env:COMPUTERNAME  Fecha: $(Get-Date -Format s)"
"Windows: $((Get-CimInstance Win32_OperatingSystem).Caption) $((Get-CimInstance Win32_OperatingSystem).Version)"
$gpu = Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name
"GPU: $($gpu -join ' | ')"

# --- Localizar OBS: instalado (registro / Program Files) o portable (-ObsRoot / proceso) ---
Section "OBS Studio"
$obsExe = $null
$proc = Get-CimInstance Win32_Process -Filter "Name='obs64.exe'" | Select-Object -First 1
if ($proc) { $obsExe = $proc.ExecutablePath; "obs64.exe en ejecucion: $obsExe" } else { "obs64.exe NO esta en ejecucion" }
if (-not $ObsRoot) {
    if ($obsExe) { $ObsRoot = Split-Path (Split-Path (Split-Path $obsExe)) }
    else {
        foreach ($k in 'HKLM:\SOFTWARE\OBS Studio', 'HKCU:\SOFTWARE\OBS Studio') {
            $v = (Get-ItemProperty $k -ErrorAction SilentlyContinue).'(default)'
            if ($v -and (Test-Path "$v\bin\64bit\obs64.exe")) { $ObsRoot = $v; break }
        }
        if (-not $ObsRoot -and (Test-Path "C:\Program Files\obs-studio\bin\64bit\obs64.exe")) { $ObsRoot = "C:\Program Files\obs-studio" }
    }
}
if ($ObsRoot) {
    $exe = Join-Path $ObsRoot "bin\64bit\obs64.exe"
    $portable = (Test-Path (Join-Path $ObsRoot "portable_mode.txt")) -or (Test-Path (Join-Path $ObsRoot "portable_mode"))
    $ver = if (Test-Path $exe) { (Get-Item $exe).VersionInfo.FileVersion } else { "?" }
    "Raiz: $ObsRoot  version: $ver  portable: $portable"
    $cfg = if ($portable) { Join-Path $ObsRoot "config\obs-studio" } else { Join-Path $env:APPDATA "obs-studio" }
} else {
    "No se encontro OBS. Usa -ObsRoot <carpeta de OBS>."
    $cfg = Join-Path $env:APPDATA "obs-studio"
}
"Config: $cfg"
$pluginDll = @(
    (Join-Path $ObsRoot "obs-plugins\64bit\source-record.dll"),
    (Join-Path $ObsRoot "plugins\source-record\source-record.dll"),
    "$env:ProgramData\obs-studio\plugins\source-record\bin\64bit\source-record.dll",
    "$env:ProgramData\obs-studio\plugins\source-record\source-record.dll"
) | Where-Object { $_ -and (Test-Path $_) }
"Plugin Source Record: " + $(if ($pluginDll) { ($pluginDll | ForEach-Object { "$_ ($((Get-Item $_).Length) bytes)" }) -join ' ; ' } else { "NO encontrado" })

# --- Fuentes de video/imagen en la coleccion de escenas ---
Section "Archivos de las fuentes de video / imagen en OBS"
$scenesDir = Join-Path $cfg "basic\scenes"
$collections = Get-ChildItem $scenesDir -Filter *.json -ErrorAction SilentlyContinue
if (-not $collections) { "No hay colecciones en $scenesDir" }
$seen = @{}
foreach ($col in $collections) {
    "-- coleccion: $($col.BaseName)"
    try { $j = Get-Content $col.FullName -Raw -Encoding UTF8 | ConvertFrom-Json } catch { "   (no se pudo leer: $_)"; continue }
    foreach ($src in $j.sources) {
        if ($src.id -notin 'ffmpeg_source', 'image_source') { continue }
        $path = if ($src.id -eq 'ffmpeg_source') { $src.settings.local_file } else { $src.settings.file }
        if (-not $path) { "   [$($src.id)] '$($src.name)': SIN ARCHIVO configurado"; continue }
        $key = "$($src.name)|$path"; if ($seen[$key]) { continue }; $seen[$key] = $true
        $win = $path -replace '/', '\'
        $line = "   [$($src.id)] '$($src.name)'`n      $win"
        if (-not (Test-Path -LiteralPath $win)) {
            $hint = if ($win -match '^[A-Za-z]:\\Users\\([^\\]+)\\' -and $Matches[1] -ne $env:USERNAME) { " (ruta de OTRO usuario/equipo: '$($Matches[1])' - escena importada?)" } else { "" }
            $line += "`n      >>> NO EXISTE en este equipo$hint"
        } else {
            $it = Get-Item -LiteralPath $win
            $attrs = $it.Attributes
            # OneDrive Files On-Demand: un archivo "solo en la nube" lleva Offline (0x1000)
            # y/o RecallOnDataAccess (0x400000). ReparsePoint a secas = sincronizado e
            # hidratado (legible), solo informativo.
            $cloudOnly = (([int]$attrs -band 0x400000) -ne 0) -or (([int]$attrs -band 0x1000) -ne 0)
            $reparse = ($attrs -band [IO.FileAttributes]::ReparsePoint) -ne 0
            $hdr = ""
            try {
                $fs = [IO.File]::OpenRead($win); $b = New-Object byte[] 12; $n = $fs.Read($b, 0, 12); $fs.Close()
                $ascii = -join ($b[0..($n - 1)] | ForEach-Object { if ($_ -ge 32 -and $_ -le 126) { [char]$_ } else { '.' } })
                $hdr = "cabecera='$ascii'"
                if ($it.Extension -match '^\.(mp4|m4v|mov)$' -and $ascii -notmatch 'ftyp') { $hdr += " >>> NO parece MP4 valido" }
            } catch { $hdr = ">>> NO SE PUEDE LEER: $($_.Exception.Message)" }
            $line += "`n      existe, $($it.Length) bytes, attrs=$attrs, $hdr"
            if ($cloudOnly) { $line += "`n      >>> ARCHIVO DE ONEDRIVE 'solo en la nube': OBS no puede leerlo. Clic derecho > 'Conservar siempre en este dispositivo'." }
            elseif ($reparse) { $line += "`n      (sincronizado por OneDrive, hidratado: legible)" }
        }
        $line
    }
}

# --- Log de OBS ---
Section "Ultimo log de OBS: errores de media / decodificacion / texturas"
$logDir = Join-Path $cfg "logs"
$log = Get-ChildItem $logDir -Filter *.txt -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($log) {
    "Log: $($log.FullName)"
    $pat = 'Media Source|ffmpeg_source|MP: |mp_media|Failed to open|avformat|Invalid data|decod|texture|D3D11|hw_decod|source-record|Source Record|obs-websocket'
    Get-Content $log.FullName | Select-String -Pattern $pat | Where-Object { $_ -notmatch 'obs-browser' } | Select-Object -Last 60 | ForEach-Object { "  " + $_.Line }
} else { "No hay logs en $logDir" }

# --- Log de la app ---
Section "Log de OBS Automation Manager (ultimas lineas sobre escenas / errores)"
$appLog = "$env:LOCALAPPDATA\OBS_Automation_Manager\logs\app.log"
if (Test-Path $appLog) {
    "Log: $appLog"
    Get-Content $appLog | Select-String -Pattern 'ERROR|WARNING|Escena creada|apply|media|cursor|Source Record' | Select-Object -Last 40 | ForEach-Object { "  " + $_.Line }
} else { "No existe $appLog" }

Section "Fin"
"Envia esta salida completa junto con el nombre de las escenas que se ven en negro."
