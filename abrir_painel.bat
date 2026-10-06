@echo off
rem ===========================================================================
rem  busca_voos - abre o painel (duplo clique)
rem
rem  O painel e o app inteiro: monitoramento, rotas, e-mail, agendador e o
rem  botao "Buscar voos agora". O agendador automatico so roda ENQUANTO esta
rem  janela estiver aberta. Ctrl+C ou fechar a janela encerra o painel.
rem
rem  - Se o painel ja estiver aberto, so abre o navegador nele.
rem  - Se faltar o pacote do painel, oferece instalar.
rem  - Opcional: argumentos extras vao para o painel, ex.: abrir_painel.bat --porta 8788
rem ===========================================================================
setlocal
title busca_voos - painel
cd /d "%~dp0"

echo ==========================================================
echo   busca_voos - painel local
echo ==========================================================
echo.

rem --- 0) ja esta rodando? entao so abre o navegador -------------------
if "%~1"=="" (
    netstat -ano | findstr /R /C:":8787 .*LISTENING" >nul 2>&1
    if not errorlevel 1 (
        echo O painel ja esta aberto em http://127.0.0.1:8787
        echo Abrindo o navegador...
        start "" "http://127.0.0.1:8787"
        timeout /t 3 >nul
        exit /b 0
    )
)

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

rem --- 2) nao achou: oferece instalar --------------------------------
if not defined PY (
    set "BASE="
    if exist ".venv\Scripts\python.exe" set "BASE=.venv\Scripts\python.exe"
    if not defined BASE (
        python --version >nul 2>&1
        if not errorlevel 1 set "BASE=python"
    )
    if not defined BASE (
        echo [!] Python nao foi encontrado neste computador.
        echo.
        echo     Instale em https://www.python.org/downloads/ e marque a opcao
        echo     "Add python.exe to PATH" na primeira tela. Depois de instalar,
        echo     de duplo clique neste arquivo de novo.
        echo.
        pause
        exit /b 1
    )
    echo [!] Faltam os pacotes do painel ^(fastapi e uvicorn^).
    echo     Posso instalar agora com: pip install -e ".[web]"
    echo     Precisa de internet e leva alguns minutos.
    echo.
    choice /c SN /m "Instalar agora"
    if errorlevel 2 (
        echo.
        echo Ok, nada foi instalado.
        pause
        exit /b 1
    )
    "%BASE%" -m pip install -e ".[web]"
    if errorlevel 1 (
        echo.
        echo [x] A instalacao falhou. Veja a mensagem acima.
        pause
        exit /b 1
    )
    set "PY=%BASE%"
)
echo Python: %PY%

rem --- 3) config.yaml (o painel le o caminho do banco daqui) ---------
if not exist "config.yaml" (
    copy /y "config.example.yaml" "config.yaml" >nul
    echo Config: config.yaml criado a partir de config.example.yaml
    echo         ajuste rotas e preco_maximo no painel, aba Gestao.
)
echo.

rem --- 4) sobe o painel e abre o navegador ---------------------------
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
