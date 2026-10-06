@echo off
rem ===========================================================================
rem  busca_voos - modo daemon: busca de hora em hora, sem parar
rem  Deixe esta janela aberta. Ctrl+C encerra.
rem  Para rodar sozinho no Windows, aponte o Agendador de Tarefas para este
rem  arquivo, com o disparador "Ao fazer logon".
rem ===========================================================================
setlocal
title busca_voos - monitor
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [X] O ambiente ainda nao foi criado. Duplo clique em INSTALAR.bat primeiro.
    pause
    exit /b 1
)

set "PYTHONPATH=%~dp0src"
echo Monitor rodando. O intervalo vem de agenda.intervalo_minutos no config.yaml.
echo Deixe esta janela aberta. Ctrl+C encerra.
echo.

".venv\Scripts\python.exe" -m busca_voos.cli run %*

echo.
echo Monitor encerrado. Pressione qualquer tecla para fechar...
pause >nul
endlocal
