#!/usr/bin/env bash
# ===========================================================================
#  busca_voos - atualizacao automatizada (Linux / macOS)
#  Uso: bash atualizar.sh
#  Preserva: dados.sqlite3, config.yaml, .env e credenciais (.segredo.key).
# ===========================================================================
set -euo pipefail
cd "$(dirname "$0")"

echo "=========================================================="
echo "  busca_voos - Atualizacao do Sistema"
echo "=========================================================="
echo
echo "Seus dados, rotas cadastradas, banco de dados e credenciais"
echo "criptografadas serao 100% preservados durante a atualizacao."
echo

# 1) git pull se estiver num repositorio Git
if command -v git >/dev/null 2>&1 && [ -d .git ]; then
    echo "== 1/3 Baixando novidades do repositorio Git..."
    git pull || echo "[!] Falha ao puxar atualizacoes via Git. Continuando..."
else
    echo "== 1/3 Git nao detectado ou repositorio nao e Git. Pulando git pull."
fi

# 2) atualiza dependencias no .venv
PY="python3"
if [ -f ".venv/bin/python" ]; then
    PY=".venv/bin/python"
fi

echo
echo "== 2/3 Atualizando dependencias do pacote busca_voos ($PY)..."
"$PY" -m pip install --upgrade pip >/dev/null 2>&1 || true
"$PY" -m pip install -e ".[web]"

# 3) navegadores Playwright
echo
echo "== 3/3 Verificando navegadores do Playwright..."
"$PY" -m playwright install chromium || echo "[!] Playwright: se necessario, instale dependencias do sistema."

echo
echo "=========================================================="
echo "  Atualizacao concluida com sucesso!"
echo "=========================================================="
echo "Para reiniciar o servico systemd (se aplicavel):"
echo "  sudo systemctl restart busca-voos"
echo "Ou inicie o painel via:"
echo "  $PY -m busca_voos.cli painel --abrir"
echo
