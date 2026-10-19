#!/usr/bin/env bash
# ===========================================================================
#  busca_voos - instalacao completa no Linux (Debian/Ubuntu/derivados)
#
#  Como usar:
#    1. copie a pasta do projeto para o Linux (scp, git clone ou o zip)
#    2. copie ESTE arquivo para dentro da pasta do projeto
#    3. rode:  bash instalar_no_linux.sh
#
#  Faz tudo: confere o Python, cria o .venv, instala o app + painel web,
#  baixa o navegador do Playwright, cria config.yaml, .env e o banco vazio.
#  Nao sobrescreve nada que ja exista (config, .env, banco, credenciais).
# ===========================================================================
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

echo "=========================================================="
echo "  busca_voos - instalacao no Linux"
echo "=========================================================="
echo

echo "== 1/6 conferindo o Python (precisa ser 3.10+)"
command -v "$PY" >/dev/null 2>&1 || {
    echo "[X] Python 3 nao encontrado. Instale com:"
    echo "      sudo apt update && sudo apt install -y python3-venv python3-pip"
    exit 1
}
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "[X] Precisa de Python 3.10 ou mais novo (encontrado: $("$PY" -V 2>&1))"
    exit 1
fi
"$PY" -V
echo "    ok."

echo
echo "== 2/6 criando o ambiente virtual .venv"
if [ ! -d .venv ]; then
    "$PY" -m venv .venv || {
        echo "[X] Falhou criar o .venv. Em Debian/Ubuntu:"
        echo "      sudo apt install -y python3-venv"
        exit 1
    }
fi
.venv/bin/python -m pip install --upgrade pip
echo "    ok."

echo
echo "== 3/6 instalando busca_voos + painel web (pode demorar na 1a vez)"
.venv/bin/python -m pip install -e ".[web]"
echo "    ok."

echo
echo "== 4/6 baixando o navegador do Playwright (~150 MB)"
echo "    (necessario para Skyscanner/Trip.com; as fontes HTTP funcionam sem ele)"
if .venv/bin/python -m playwright install chromium; then
    echo "    ok."
else
    echo "[!] Nao consegui baixar o navegador. Skyscanner/Trip.com vao falhar,"
    echo "    mas google_flights e skiplagged continuam funcionando."
    echo "    Se ele reclamar de bibliotecas do sistema, rode:"
    echo "      sudo .venv/bin/playwright install-deps chromium"
fi

echo
echo "== 5/6 criando config.yaml, .env e o banco de dados"
.venv/bin/busca-voos init

echo
echo "== 6/6 instalacao concluida!"
cat <<'FIM'
----------------------------------------------------------
PROXIMOS PASSOS
----------------------------------------------------------
1) Edite o config.yaml  -> rotas, datas, preco_maximo, email.de e email.para
     nano config.yaml

2) Edite o .env         -> SMTP_SENHA com uma senha de app do Gmail
     nano .env           (https://myaccount.google.com/apppasswords)

3) Teste uma fonte (sem banco e sem e-mail):
     .venv/bin/busca-voos testar google_flights --origem FLN --destino RIO --ida 2026-12-20

4) Rode um ciclo completo (sem enviar e-mail):
     .venv/bin/busca-voos uma --sem-email

5) (opcional) Valide o e-mail:
     .venv/bin/busca-voos email-teste

6) Abra o painel web (http://127.0.0.1:8787):
     .venv/bin/busca-voos painel --abrir

----------------------------------------------------------
RODAR 24/7 COMO SERVICO (systemd)
----------------------------------------------------------
     sudo cp systemd/busca-voos.service /etc/systemd/system/
     sudo nano /etc/systemd/system/busca-voos.service   # ajuste User e caminhos
     sudo systemctl daemon-reload
     sudo systemctl enable --now busca-voos
     journalctl -u busca-voos -f                        # acompanhar os logs
----------------------------------------------------------
FIM
