@echo off
chcp 65001 >nul
REM Duplo clique: converte todos os .nox desta pasta.
REM Ou arraste arquivos .nox / pastas sobre este arquivo.
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python nao encontrado. Instale em https://www.python.org/downloads/
  echo e marque a opcao "Add python.exe to PATH" na instalacao.
  pause
  exit /b
)
%PY% "%~dp0nox2excel.py" %*
echo.
pause
