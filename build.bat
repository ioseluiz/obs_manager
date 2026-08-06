@echo off
echo ============================================
echo  Generando ejecutable OBS Automation Manager
echo ============================================

REM Activar entorno virtual
call venv\Scripts\activate.bat

REM Limpiar compilaciones anteriores
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Generar el ejecutable (modo --onedir; el spec ya define COLLECT)
pyinstaller OBS_Automation_Manager.spec

echo.
echo ============================================
echo  Listo. La app esta en: dist\OBS_Automation_Manager\
echo  Exe principal: dist\OBS_Automation_Manager\OBS_Automation_Manager.exe
echo ============================================
pause
