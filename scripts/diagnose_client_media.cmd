@echo off
rem ============================================================================
rem  Diagnostico de escenas de video en negro en un equipo cliente (SOLO LECTURA)
rem  Version CMD para equipos donde PowerShell esta bloqueado. Sin Python.
rem
rem  USO (doble clic, o en cmd):
rem     diagnose_client_media.cmd
rem     diagnose_client_media.cmd "D:\OBSPortable\obs-studio"   (si OBS es portable)
rem
rem  Escribe el informe JUNTO AL SCRIPT: diagnostico_obs_<equipo>.txt
rem  y lo muestra en pantalla. Enviar ese archivo completo.
rem ============================================================================
setlocal EnableExtensions EnableDelayedExpansion

set "OUT=%~dp0diagnostico_obs_%COMPUTERNAME%.txt"
rem Si la carpeta del script no es escribible (p. ej. un zip abierto), usar TEMP
(echo test > "%OUT%") 2>nul || set "OUT=%TEMP%\diagnostico_obs_%COMPUTERNAME%.txt"
set "OBSROOT=%~1"
call :main > "%OUT%" 2>&1
type "%OUT%"
echo.
echo Informe guardado en: %OUT%
echo (Enviar ese archivo completo junto con el nombre de las escenas en negro)
pause
exit /b 0

:main
echo === Equipo ===
echo Usuario: %USERNAME%   Equipo: %COMPUTERNAME%   Fecha: %DATE% %TIME%
ver
echo --- GPU / driver (registro de adaptadores de video) ---
for /f "tokens=2,*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}" /s /v DriverDesc 2^>nul ^| findstr /I "DriverDesc"') do echo   %%B
for /f "tokens=2,*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}" /s /v DriverVersion 2^>nul ^| findstr /I "DriverVersion"') do echo   driver %%B
echo.

echo === OBS Studio ===
rem 1) Raiz pasada como argumento; 2) registro; 3) Program Files
if defined OBSROOT (
    echo Raiz indicada: "%OBSROOT%"
) else (
    for /f "skip=2 tokens=2,*" %%A in ('reg query "HKLM\SOFTWARE\OBS Studio" /ve 2^>nul') do set "OBSROOT=%%B"
    if not defined OBSROOT for /f "skip=2 tokens=2,*" %%A in ('reg query "HKCU\SOFTWARE\OBS Studio" /ve 2^>nul') do set "OBSROOT=%%B"
    if not defined OBSROOT if exist "%ProgramFiles%\obs-studio\bin\64bit\obs64.exe" set "OBSROOT=%ProgramFiles%\obs-studio"
    if not defined OBSROOT if exist "%ProgramFiles(x86)%\obs-studio\bin\64bit\obs64.exe" set "OBSROOT=%ProgramFiles(x86)%\obs-studio"
)
if defined OBSROOT if "!OBSROOT:~-1!"=="\" set "OBSROOT=!OBSROOT:~0,-1!"
if not defined OBSROOT (
    echo No se encontro OBS instalado. Si es portable, ejecutar: diagnose_client_media.cmd "carpeta\de\obs-studio"
    set "CFG=%APPDATA%\obs-studio"
) else (
    echo Raiz OBS: "!OBSROOT!"
    if exist "!OBSROOT!\bin\64bit\obs64.exe" (echo obs64.exe: OK) else (echo obs64.exe: NO ENCONTRADO en esa raiz)
    set "PORTABLE=0"
    if exist "!OBSROOT!\portable_mode.txt" set "PORTABLE=1"
    if exist "!OBSROOT!\portable_mode" set "PORTABLE=1"
    if "!PORTABLE!"=="1" (
        echo Modo: PORTABLE
        set "CFG=!OBSROOT!\config\obs-studio"
    ) else (
        echo Modo: instalado
        set "CFG=%APPDATA%\obs-studio"
    )
)
echo Config: "!CFG!"
tasklist /FI "IMAGENAME eq obs64.exe" /NH 2>nul | find /I "obs64.exe" >nul && (echo obs64.exe en ejecucion: SI) || (echo obs64.exe en ejecucion: NO)
echo.
echo --- Modulo de video de OBS (obs-ffmpeg) y DLLs de FFmpeg ---
rem Si el OBS portable se copio incompleto (zip/OneDrive), faltan estas DLL y TODOS los
rem videos salen en negro aunque imagenes y paginas web funcionen.
if exist "!OBSROOT!\obs-plugins\64bit\obs-ffmpeg.dll" (
    for %%S in ("!OBSROOT!\obs-plugins\64bit\obs-ffmpeg.dll") do echo   obs-ffmpeg.dll: OK ^(%%~zS bytes^)
) else (
    echo   ^>^>^> FALTA obs-plugins\64bit\obs-ffmpeg.dll: OBS no puede reproducir videos. Reinstalar / recopiar OBS completo.
)
set /a NDLL=0
for %%D in ("!OBSROOT!\bin\64bit\avcodec*.dll" "!OBSROOT!\bin\64bit\avformat*.dll" "!OBSROOT!\bin\64bit\avutil*.dll" "!OBSROOT!\bin\64bit\swscale*.dll") do (
    if exist "%%~D" (
        set /a NDLL+=1
        for %%Z in ("%%~D") do (
            echo   %%~nxZ  %%~zZ bytes
            if %%~zZ EQU 0 echo   ^>^>^> %%~nxZ tiene 0 bytes ^(copia incompleta / marcador OneDrive^)
        )
    )
)
if !NDLL! LSS 4 echo   ^>^>^> Faltan DLL de FFmpeg en bin\64bit ^(encontradas: !NDLL! de 4^): OBS no puede decodificar video.
echo.
echo --- Plugin Source Record ---
set "SRFOUND=0"
for %%P in (
    "!OBSROOT!\obs-plugins\64bit\source-record.dll"
    "!OBSROOT!\plugins\source-record\source-record.dll"
    "%ProgramData%\obs-studio\plugins\source-record\bin\64bit\source-record.dll"
    "%ProgramData%\obs-studio\plugins\source-record\source-record.dll"
) do (
    if exist %%P (
        set "SRFOUND=1"
        for %%S in (%%P) do echo   %%~fS  ^(%%~zS bytes^)
    )
)
if "!SRFOUND!"=="0" echo   NO encontrado en las rutas conocidas
echo.

echo === Archivos de las fuentes de video / imagen en OBS ===
set "SCENES=!CFG!\basic\scenes"
if not exist "!SCENES!\*.json" (
    echo No hay colecciones de escenas en "!SCENES!"
) else (
    for %%J in ("!SCENES!\*.json") do call :scancollection "%%~J"
)
echo.

echo === Ultimo log de OBS: media / decodificacion / texturas (sin obs-browser) ===
set "LOGDIR=!CFG!\logs"
set "LOG="
for /f "delims=" %%F in ('dir /b /o-d "!LOGDIR!\*.txt" 2^>nul') do (
    if not defined LOG set "LOG=!LOGDIR!\%%F"
)
if not defined LOG (
    echo No hay logs en "!LOGDIR!"
) else (
    echo Log: "!LOG!"
    findstr /I /C:"Media Source" /C:"ffmpeg_source" /C:"MP: " /C:"mp_media" /C:"Failed to open" /C:"avformat" /C:"Invalid data" /C:"decod" /C:"texture" /C:"D3D11" /C:"hw_decod" /C:"source-record" /C:"Source Record" /C:"VBV" /C:"Available Video Adapters" /C:"Adapter 0" /C:"Loading up D3D11" /C:"Failed to load" /C:"LoadLibrary" /C:"obs-ffmpeg" /C:"Loaded Modules" /C:"Skipping module" /C:"not found" "!LOG!" | findstr /V /C:"obs-browser"
)
echo.

echo === Log de OBS Automation Manager (errores / escenas / media) ===
set "APPLOG=%LOCALAPPDATA%\OBS_Automation_Manager\logs\app.log"
if exist "!APPLOG!" (
    echo Log: "!APPLOG!"
    findstr /C:"ERROR" /C:"WARNING" /C:"Escena creada" /C:"apply" /C:"media" /C:"cursor" /C:"Source Record" /C:"arrancando" "!APPLOG!" > "%TEMP%\_applog_filtrado.txt"
    rem Solo las ultimas ~40 lineas
    for /f %%C in ('type "%TEMP%\_applog_filtrado.txt" ^| find /C /V ""') do set /a SKIP=%%C-40
    if !SKIP! LSS 0 set SKIP=0
    more +!SKIP! "%TEMP%\_applog_filtrado.txt"
    del "%TEMP%\_applog_filtrado.txt" 2>nul
) else (
    echo No existe "!APPLOG!"
)
echo.
echo === Fin ===
exit /b 0

rem ----------------------------------------------------------------------------
rem :scancollection "ruta\coleccion.json"
rem   Lineas tipo:  "local_file": "C:/ruta/video.mp4",   o   "file": "C:/ruta/img.png",
rem   Con la comilla como delimitador: token1 = sangria, token2 = clave,
rem   token3 = ": ", token4 = ruta. Fuera de bloques ( ) para poder usar la
rem   comilla como delimitador sin problemas de escape.
rem ----------------------------------------------------------------------------
:scancollection
echo -- coleccion: %~n1
set "LINES=%TEMP%\_obs_media_lines.txt"
findstr /R /C:"local_file" /C:".file.: " "%~1" > "%LINES%" 2>nul
for /f usebackq^ tokens^=4^ delims^=^" %%L in ("%LINES%") do call :checkfile "%%L"
del "%LINES%" 2>nul
goto :eof

rem ----------------------------------------------------------------------------
rem :checkfile "ruta tal cual aparece en el JSON (con / )"
rem ----------------------------------------------------------------------------
:checkfile
set "P=%~1"
set "P=!P:/=\!"
rem Solo valores con pinta de ruta (evita falsos positivos de otras claves *file*)
echo !P! | findstr /C:"\\" >nul || goto :eof
echo   !P!
if "!P!"=="" (
    echo      SIN ARCHIVO configurado
    goto :eof
)
if not exist "!P!" (
    echo      ^>^>^> NO EXISTE en este equipo
    echo !P! | findstr /I /C:"C:\Users\%USERNAME%\" >nul
    if errorlevel 1 (
        echo !P! | findstr /I /C:"\Users\" >nul && echo      ^(la ruta es de OTRO usuario o equipo: escena importada?^)
    )
    goto :eof
)
for %%S in ("!P!") do echo      existe, %%~zS bytes, fecha %%~tS
rem attrib: O = sin conexion / U = no fijado (OneDrive solo en la nube), P = fijado, L = reparse
for /f "delims=" %%T in ('attrib "!P!" 2^>nul') do set "ATTR=%%T"
set "ATTRCODES=!ATTR:~0,21!"
echo      atributos: [!ATTRCODES!]
echo !ATTRCODES! | findstr /C:"O" >nul && echo      ^>^>^> ARCHIVO DE ONEDRIVE SOLO EN LA NUBE ^(sin conexion^): OBS no puede leerlo. Clic derecho ^> "Conservar siempre en este dispositivo"
echo !ATTRCODES! | findstr /C:"U" >nul && echo      ^(OneDrive: no fijado; si se "libera espacio" dejara de leerse^)
goto :eof
