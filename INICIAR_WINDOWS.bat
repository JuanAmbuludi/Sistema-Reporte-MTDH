@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto error
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto error
.venv\Scripts\python.exe -m streamlit run app.py
goto end
:error
echo No se pudo iniciar. Comprueba que Python 3.12 esta instalado y revisa el mensaje anterior.
pause
:end
endlocal
