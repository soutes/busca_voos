@echo off
rem ===========================================================================
rem  busca_voos - faz UM ciclo de busca agora (todas as rotas e fontes)
rem  Aceita as mesmas opcoes do CLI. Ex.: RODAR_CICLO.bat --sem-email
rem ===========================================================================
setlocal
title busca_voos - um ciclo
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [X] O ambiente ainda nao foi criado. Duplo clique em INSTALAR.bat primeiro.
    pause
    exit /b 1
)

set "PYTHONPATH=%~dp0src"
echo Uma busca agora. Pode levar alguns minutos ^(varias fontes, com pausas^).
echo Ctrl+C cancela. Para testar sem enviar e-mail: RODAR_CICLO.bat --sem-email
echo.

".venv\Scripts\python.exe" -m busca_voos.cli uma %*

echo.
echo Ciclo terminado. Pressione qualquer tecla para fechar...
pause >nul
endlocal
