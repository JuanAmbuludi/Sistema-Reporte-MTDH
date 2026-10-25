@echo off
cd /d "%~dp0"
if "%~1"=="" (
  echo Uso: ACTUALIZAR_DATOS.bat "C:\ruta\con\los\insumos"
  echo Para consultar solo la web: python scripts\update_history.py --web
  exit /b 1
)
python scripts\update_history.py --entrada "%~1" --web
if errorlevel 1 (
  echo Actualizacion cancelada. Revise el mensaje anterior.
  exit /b 1
)
echo Bases validadas y actualizadas. Revise git diff antes de subir nuevos insumos.
