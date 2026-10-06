# busca_voos no Linux — comece aqui

Monitor de passagens aéreas: procura as rotas/datas que você definir em
`config.yaml`, em várias fontes, e manda um e-mail quando o preço cair.
Roda bem como serviço (systemd), 24/7. Tem também um painel web com o
histórico de preços.

## 1. Instalar (uma vez só)

```bash
cd vs_linux
bash instalar.sh
```

O script cria o `.venv`, instala o app + painel, baixa o navegador do
Playwright (~150 MB), cria `config.yaml`, `.env` e o banco vazio. Se faltar algo
no sistema, ele diz o comando `apt` exato.

> Alternativa: `chmod +x instalar.sh && ./instalar.sh`

## 2. Configurar

- **`config.yaml`** — `rotas:` (`origem`/`destino` com código IATA, janelas de
  data e `preco_maximo`), `email.de` (quem envia) e `email.para` (quem recebe).
- **`.env`** — `SMTP_SENHA=` com uma **senha de app** do Gmail
  (https://myaccount.google.com/apppasswords). A senha normal da conta não
  funciona. Sem isso o app só registra no log.

## 3. Usar

```bash
.venv/bin/busca-voos testar google_flights --origem FLN --destino RIO --ida 2026-12-20
.venv/bin/busca-voos uma --sem-email     # um ciclo, sem enviar e-mail
.venv/bin/busca-voos uma                 # um ciclo, com e-mail
.venv/bin/busca-voos email-teste         # valida o SMTP
.venv/bin/busca-voos painel --abrir      # painel no navegador (127.0.0.1:8787)
```

## 4. Rodar 24/7 (systemd)

```bash
sudo cp systemd/busca-voos.service /etc/systemd/system/
sudo nano /etc/systemd/system/busca-voos.service   # ajuste User e os caminhos
sudo systemctl daemon-reload
sudo systemctl enable --now busca-voos
journalctl -u busca-voos -f                        # acompanhar
```

Se o painel tiver de rodar junto, crie uma unidade própria com
`ExecStart=.../busca-voos painel --host 127.0.0.1 --porta 8787`
(o painel não tem autenticação; não exponha em rede aberta).

## 5. Docker (opcional)

O `Dockerfile` roda o monitor em container. Cuidados: ele instala só o app
(sem o painel) e o volume do banco precisa existir como **arquivo** antes de
subir, senão o Docker cria um diretório no lugar.

```bash
docker build -t busca-voos .
touch dados.sqlite3                                # evita o volume virar pasta
docker run -d --name busca-voos --env-file .env \
  -v "$PWD/config.yaml:/app/config.yaml:ro" \
  -v "$PWD/dados.sqlite3:/app/dados.sqlite3" \
  busca-voos
```

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| `skyscanner: anti-bot (DataDome)` | IP de servidor bloqueado: use `navegador.proxy` ou `canal: chrome` |
| `skiplagged: pagina sem precos` | o fallback com navegador já tenta; confira com `--debug` |
| `google_flights: nenhum resultado parseado` | o Google mudou o HTML — veja a tabela do `README.md` |
| Fonte bloqueada não derruba nada | cada fonte é isolada; o ciclo segue com as outras |
| Painel diz "Banco ... nao existe ainda" | rode `.venv/bin/busca-voos uma --sem-email` uma vez |
| Banco criado na pasta errada | `banco:` é relativo à pasta de onde você roda o comando |

O `README.md` (nesta pasta) tem a referência completa de configuração, a lista
de fontes e a seção **Bloqueios**.
