 @echo off
  echo ============================================
  echo  Generando ejecutable OBS Automation Manager
  echo ============================================

  REM Activar entorno virtual
  call venv\Scripts\activate.bat

  REM Limpiar compilaciones anteriores
  if exist build rmdir /s /q build
  if exist dist rmdir /s /q dist

  REM Generar el ejecutable
  pyinstaller ^
    --onefile ^
    --windowed ^
    --icon=app_icon.ico ^
    --add-data "app_icon.ico;." ^
    --name="OBS_Automation_Manager" ^
    main.py

  echo.
  echo ============================================
  echo  Listo. El ejecutable esta en: dist\
  echo ============================================
  pause