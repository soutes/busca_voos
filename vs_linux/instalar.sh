#!/usr/bin/env bash
# ===========================================================================
#  busca_voos - instalacao no Linux
#  Uso:  bash instalar.sh
#  Faz tudo: ambiente Python, dependencias + painel, navegador do Playwright,
#  config.yaml, .env e banco vazio. Nao sobrescreve o que ja existe.
# ===========================================================================
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

echo "== 0/5 conferindo o Python"
command -v "$PY" >/dev/null 2>&1 || {
    echo "[X] Python 3 nao encontrado. Instale com:"
    echo "    sudo apt update && sudo apt install -y python3-venv python3-pip"
    exit 1
}
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "[X] Precisa de Python 3.10 ou mais novo (encontrado: $("$PY" -V 2>&1))"
    exit 1
fi
"$PY" -V

echo
echo "== 1/5 criando o ambiente .venv"
[ -d .venv ] || "$PY" -m venv .venv || {
    echo "[X] Falhou criar o .venv. Em Debian/Ubuntu: sudo apt install -y python3-venv"
    exit 1
}
.venv/bin/python -m pip install --upgrade pip

echo
echo "== 2/5 instalando busca_voos + painel (pode demorar na primeira vez)"
.venv/bin/python -m pip install -e ".[web]"

echo
echo "== 3/5 baixando o navegador do Playwright (Skyscanner/Trip.com, ~150 MB)"
if ! .venv/bin/python -m playwright install chromium; then
    echo "[!] Nao consegui baixar o navegador. Skyscanner/Trip.com vao falhar,"
    echo "    mas as fontes HTTP (google_flights, skiplagged) continuam funcionando."
    echo "    Em Debian/Ubuntu tente: sudo .venv/bin/playwright install-deps chromium"
fi

echo
echo "== 4/5 criando config.yaml, .env e o banco"
.venv/bin/busca-voos init

echo
echo "== 5/5 pronto"
cat <<'FIM'
Proximos passos:
  1. edite config.yaml  -> rotas, preco_maximo, email.de e email.para
  2. edite .env         -> SMTP_SENHA (senha de app do Gmail), se quiser e-mail
  3. teste uma fonte    -> .venv/bin/busca-voos testar google_flights \
                              --origem FLN --destino RIO --ida 2026-12-20
  4. um ciclo           -> .venv/bin/busca-voos uma --sem-email
  5. painel             -> .venv/bin/busca-voos painel --abrir

Para rodar 24/7 como servico (systemd):
  sudo cp systemd/busca-voos.service /etc/systemd/system/
  sudo nano /etc/systemd/system/busca-voos.service   # ajuste User e caminhos
  sudo systemctl daemon-reload && sudo systemctl enable --now busca-voos
  journalctl -u busca-voos -f
FIM
