@echo off
rem ===========================================================================
rem  busca_voos - abre o painel local do historico
rem  Duplo clique. Ctrl+C (ou fechar a janela) encerra o painel.
rem  O painel e somente leitura: nao busca precos nem envia e-mail.
rem ===========================================================================
setlocal
title busca_voos - painel
cd /d "%~dp0"

set "PY="
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import fastapi, uvicorn" >nul 2>&1
    if not errorlevel 1 set "PY=%~dp0.venv\Scripts\python.exe"
)
if not defined PY (
    python -c "import fastapi, uvicorn" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [X] Falta a parte web do painel ^(fastapi/uvicorn^).
    echo.
    echo     Duplo clique em INSTALAR.bat primeiro, ou rode:
    echo         .venv\Scripts\python.exe -m pip install -e ".[web]"
    echo.
    pause
    exit /b 1
)

set "PYTHONPATH=%~dp0src"

rem o painel precisa do config e do banco: init cria o que faltar
if not exist "config.yaml" (
    echo Primeira vez: criando config.yaml, .env e o banco ...
    "%PY%" -m busca_voos.cli init
    echo.
)

"%PY%" -m busca_voos.cli painel --abrir %*
echo.
echo Painel encerrado. Pressione qualquer tecla para fechar...
pause >nul
endlocal
