@echo off
rem ===========================================================================
rem  busca_voos - abre o painel local do historico de passagens
rem  Duplo clique neste arquivo. Ctrl+C (ou fechar a janela) encerra o painel.
rem  O painel e somente leitura: nao dispara buscas nem envia e-mail.
rem ===========================================================================
setlocal
title busca_voos - painel
cd /d "%~dp0"

echo ==========================================================
echo   busca_voos - painel local do historico
echo ==========================================================
echo.

rem --- 1) escolhe um Python que tenha fastapi + uvicorn ---------------
set "PY="
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import fastapi, uvicorn" >nul 2>&1
    if not errorlevel 1 set "PY=.venv\Scripts\python.exe"
)
if not defined PY (
    python -c "import fastapi, uvicorn" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [!] Nenhum Python com "fastapi" e "uvicorn" foi encontrado.
    echo.
    echo     Instale as dependencias do painel com:
    echo         .venv\Scripts\python.exe -m pip install -e ".[web]"
    echo.
    echo     O resto do app - uma/run/testar/email-teste - continua
    echo     funcionando sem essas dependencias.
    echo.
    pause
    exit /b 1
)
echo Python: %PY%

rem --- 2) config.yaml (o painel le o caminho do banco daqui) ---------
if not exist "config.yaml" (
    copy /y "config.example.yaml" "config.yaml" >nul
    echo Config: config.yaml criado a partir de config.example.yaml
    echo         ajuste rotas e preco_maximo quando quiser
)
echo.

rem --- 3) sobe o painel e abre o navegador ---------------------------
set "PYTHONPATH=%~dp0src"
"%PY%" -m busca_voos.cli painel --abrir %*
set "CODIGO=%ERRORLEVEL%"

echo.
if not "%CODIGO%"=="0" (
    echo [x] O painel terminou com erro ^(codigo %CODIGO%^). Veja a mensagem acima.
) else (
    echo Painel encerrado.
)
echo Pressione qualquer tecla para fechar esta janela...
pause >nul
endlocal
