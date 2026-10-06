@echo off
rem ===========================================================================
rem  busca_voos - atualizacao automatizada (Windows)
rem  Duplo clique para atualizar o aplicativo sem perder seus dados.
rem  Preserva: dados.sqlite3, config.yaml, .env e credenciais (.segredo.key).
rem ===========================================================================
setlocal
title busca_voos - Atualizador
cd /d "%~dp0"

echo ==========================================================
echo   busca_voos - Atualizacao do Sistema
echo ==========================================================
echo.
echo Seus dados, rotas cadastradas, banco de dados e credenciais
echo criptografadas serao 100%% preservados durante a atualizacao.
echo.

rem --- 1) git pull se estiver num repositorio Git -------------------------
where git >nul 2>&1
if not errorlevel 1 (
    if exist ".git" (
        echo [1/3] Baixando novidades do repositorio...
        git pull
        if errorlevel 1 (
            echo [!] Falha ao puxar atualizacoes via Git. Continuando...
        ) else (
            echo [OK] Codigo-fonte atualizado com sucesso.
        )
    ) else (
        echo [1/3] Pasta .git nao encontrada. Pulando git pull.
    )
) else (
    echo [1/3] Git nao localizado no PATH. Pulando git pull.
)
echo.

rem --- 2) atualiza dependencias no ambiente Python -------------------------
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)

if defined PY (
    echo [2/3] Atualizando dependencias e instalacao (%PY%)...
    "%PY%" -m pip install --upgrade pip >nul 2>&1
    "%PY%" -m pip install -e ".[web]"
    if errorlevel 1 (
        echo [!] Ocorreu um alerta ao instalar dependencias.
    ) else (
        echo [OK] Dependencias instaladas e atualizadas.
    )
) else (
    echo [!] Python nao encontrado. Execute 'python -m pip install -e ".[web]"' manualmente.
)
echo.

rem --- 3) confere navegador Playwright -------------------------------------
if defined PY (
    echo [3/3] Verificando navegadores Playwright...
    "%PY%" -m playwright install chromium
)
echo.

echo ==========================================================
echo   Atualizacao concluida com sucesso!
echo ==========================================================
echo Voce pode abrir o painel normalmente executando abrir_painel.bat
echo.
pause
endlocal
