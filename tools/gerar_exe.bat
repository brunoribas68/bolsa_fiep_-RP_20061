@echo off
chcp 65001 >nul
REM Gera o executavel NOX2Excel.exe a partir do nox2excel.py (rode no Windows, na pasta do script).
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% -m pip install --upgrade pyinstaller pandas openpyxl
%PY% -m PyInstaller --onefile --console --name NOX2Excel --clean --noconfirm ^
    --exclude-module matplotlib --exclude-module scipy --exclude-module IPython ^
    nox2excel.py
echo.
if exist dist\NOX2Excel.exe (
  echo Pronto: dist\NOX2Excel.exe
) else (
  echo Algo deu errado - veja as mensagens acima.
)
pause
