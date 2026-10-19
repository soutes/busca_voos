#!/usr/bin/env bash
# ===========================================================================
#  busca_voos - instalar como servico systemd (roda 24/7, sozinho)
#
#  Uso (de dentro da pasta do projeto):
#    bash instalar_servico.sh              # so o monitor de voos
#    bash instalar_servico.sh --painel     # monitor + painel web (127.0.0.1:8787)
#    bash instalar_servico.sh --parar      # para e desativa os servicos
#
#  Preenche usuario, caminhos e porta automaticamente — nao precisa abrir
#  nenhum arquivo para editar. Os servicos comecam sozinhos no boot e
#  reiniciam sozinhos se cairem.
# ===========================================================================
set -euo pipefail
cd "$(dirname "$0")"
DIR="$(pwd)"

MONITOR="busca-voos"
PAINEL="busca-voos-painel"
CLI="$DIR/.venv/bin/busca-voos"
USER_NAME="${SUDO_USER:-$(id -un)}"

modo="${1:-monitor}"

if [ "$modo" = "--parar" ]; then
    echo "== parando e desativando os servicos"
    sudo systemctl disable --now "$PAINEL" 2>/dev/null || true
    sudo systemctl disable --now "$MONITOR" 2>/dev/null || true
    echo "Pronto. (Os arquivos ficaram em /etc/systemd/system/; para remover de vez:"
    echo "  sudo rm /etc/systemd/system/busca-voos*.service && sudo systemctl daemon-reload )"
    exit 0
fi

echo "== 1/4 conferindo a instalacao"
if [ ! -x "$CLI" ]; then
    echo "[X] Nao achei $CLI"
    echo "    Rode primeiro:  bash instalar.sh   (ou bash instalar_no_linux.sh)"
    exit 1
fi
if [ ! -f "$DIR/config.yaml" ]; then
    echo "[X] Nao achei config.yaml em $DIR — rode 'bash instalar.sh' antes."
    exit 1
fi
command -v systemctl >/dev/null 2>&1 || {
    echo "[X] Este Linux nao usa systemd. Use a opcao tmux/nohup do guia."
    exit 1
}
"$CLI" --help >/dev/null
echo "    ok. ($DIR)"

echo
echo "== 2/4 criando o servico do monitor ($MONITOR)"
sudo tee "/etc/systemd/system/$MONITOR.service" >/dev/null <<EOF
[Unit]
Description=busca_voos - monitor de passagens aereas
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$DIR
EnvironmentFile=-$DIR/.env
ExecStart=$CLI run --config $DIR/config.yaml
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
EOF
echo "    ok."

if [ "$modo" = "--painel" ]; then
    echo
    echo "== 3/4 criando o servico do painel web ($PAINEL, 127.0.0.1:8787)"
    sudo tee "/etc/systemd/system/$PAINEL.service" >/dev/null <<EOF
[Unit]
Description=busca_voos - painel web do historico (somente leitura)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$DIR
EnvironmentFile=-$DIR/.env
ExecStart=$CLI painel --config $DIR/config.yaml --host 127.0.0.1 --porta 8787
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    echo "    ok."
else
    echo
    echo "== 3/4 painel web pulado (use --painel se quiser ele de rodape tambem)"
fi

echo
echo "== 4/4 ligando os servicos"
sudo systemctl daemon-reload
sudo systemctl enable --now "$MONITOR"
[ "$modo" = "--painel" ] && sudo systemctl enable --now "$PAINEL"

echo
echo "=========================================================="
echo "  Pronto! Tudo rodando 24/7 (comeca sozinho no boot)"
echo "=========================================================="
echo "Status do monitor : sudo systemctl status $MONITOR"
echo "Logs ao vivo      : journalctl -u $MONITOR -f"
if [ "$modo" = "--painel" ]; then
    echo "Painel web        : http://127.0.0.1:8787"
    echo "Status do painel  : sudo systemctl status $PAINEL"
fi
echo "Parar tudo        : bash instalar_servico.sh --parar"
echo "Reiniciar         : sudo systemctl restart $MONITOR"
echo "Apos 'bash atualizar.sh': sudo systemctl restart $MONITOR"
echo "=========================================================="
