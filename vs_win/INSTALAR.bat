@echo off
rem ===========================================================================
rem  busca_voos - instalacao no Windows
rem  Duplo clique neste arquivo. Faz tudo: ambiente Python, dependencias,
rem  navegador do Playwright, config.yaml, .env e banco vazio.
rem ===========================================================================
setlocal
title busca_voos - instalacao
cd /d "%~dp0"

echo ==========================================================
echo   busca_voos - instalacao no Windows
echo ==========================================================
echo.

rem --- 1) achar um Python 3 ---
set "PY="
py -3 -V >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python -V >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [X] Nao encontrei o Python.
    echo.
    echo     Instale a versao 3.10 ou mais nova de:
    echo         https://www.python.org/downloads/
    echo     e marque a caixa "Add python.exe to PATH" na instalacao.
    echo     Depois rode este arquivo de novo.
    echo.
    pause
    exit /b 1
)
echo Python encontrado:
%PY% -V
echo.

rem --- 2) criar o ambiente isolado ---
if exist ".venv\Scripts\python.exe" (
    echo Ambiente .venv: ja existe, vou reaproveitar.
) else (
    echo Criando o ambiente .venv ...
    %PY% -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo.
        echo [X] Nao consegui criar o .venv. Veja a mensagem acima.
        pause
        exit /b 1
    )
)
set "VPY=%~dp0.venv\Scripts\python.exe"

rem --- 3) garantir o pip dentro do ambiente ---
"%VPY%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo pip ausente no ambiente - tentando instalar ...
    "%VPY%" -m ensurepip --upgrade
)
"%VPY%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [X] O pip nao esta funcionando neste Python.
    echo     No instalador do Python escolha "Repair", ou instale outra
    echo     versao de python.org, e rode este arquivo de novo.
    pause
    exit /b 1
)

rem --- 4) instalar o app e o painel ---
echo.
echo Instalando busca_voos + painel. Na primeira vez demora alguns minutos...
"%VPY%" -m pip install --upgrade pip
"%VPY%" -m pip install -e ".[web]"
if errorlevel 1 (
    echo.
    echo [X] Falhou a instalacao das dependencias. Veja a mensagem acima.
    pause
    exit /b 1
)

rem --- 5) navegador do Playwright (Skyscanner/Trip.com) ---
echo.
echo Baixando o navegador usado pelo Skyscanner/Trip.com - cerca de 150 MB ...
"%VPY%" -m playwright install chromium

rem --- 6) config.yaml, .env e banco ---
echo.
set "PYTHONPATH=%~dp0src"
"%VPY%" -m busca_voos.cli init

echo.
echo ==========================================================
echo   Pronto!
echo ==========================================================
echo   1. edite config.yaml  - rotas, email.de e email.para
echo   2. edite .env         - SMTP_SENHA, se quiser receber e-mail
echo   3. RODAR_CICLO.bat    - uma busca agora
echo   4. ABRIR_PAINEL.bat   - painel no navegador
echo.
pause
endlocal
