# busca_voos ✈️

> **AI Dev Tools Zoomcamp 2026 — Módulo 4: DevOps, Observabilidade e Resposta a Incidentes com IA**  
> Monitor inteligente de passagens aéreas instrumentado com **OpenTelemetry (Métricas, Logs, Traces)**, painel **Grafana**, alertas de impacto e **Agente de Auto-Cura (Incident Responder)** para seletores de scraping.
> 
> 📄 **Relatório Técnico:** [`docs/operations-and-security-report.md`](docs/operations-and-security-report.md)

---

Monitor de passagens aéreas que roda como serviço: busca continuamente as rotas/datas que você definir em `config.yaml`, em várias fontes, grava o histórico e **alerta sobre oportunidades e falhas operacionais**.

Fontes atuais (fases 1–2):

| Fonte | Método | Observações |
|---|---|---|
| `google_flights` | HTTP com token `tfs` (sem navegador) | Mais estável/leve; depende do HTML do Google |
| `skiplagged` | API interna `packed.js`; fallback Playwright | API antiga e simples; fallback caso mude |
| `skyscanner` | Playwright (anti-detecção) | DataDome pode bloquear; ver "Bloqueios" |
| `trip_com` | Playwright | Resultados chegam via XHR; pausa extra |

Planejadas (fase 3, já aceitas no config mas ainda sem implementação):
`kayak`, `latam`, `gol`, `azul`. O registro `src/busca_voos/sources/__init__.py`
já as lista; ao ativar antes de existir código, o app avisa e pula.

## Duas pastas prontas para enviar

O projeto tem duas cópias autocontidas, uma por sistema. Mande **a pasta
inteira** e o amigo não precisa de mais nada:

| Pasta | Para quem | Comece por |
|---|---|---|
| `vs_win/` | Windows | duplo clique em `INSTALAR.bat` |
| `vs_linux/` | Linux (servidor, systemd) | `bash instalar.sh` |

Cada uma leva o código, o `pyproject.toml`, os arquivos de exemplo e um
`LEIA-ME.md` próprio. O resto desta página vale para as duas — no Windows,
troque `.venv/bin/busca-voos` por `.venv\Scripts\python.exe -m busca_voos.cli`.

> São **cópias**: se você mudar o código na raiz, recopie `src/` e `README.md`
> para as duas pastas antes de enviar.

## Instalação (Linux)

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip
cd busca_voos
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/playwright install chromium
# se o Chromium reclamar de bibliotecas do sistema:
sudo .venv/bin/playwright install-deps chromium

cp config.example.yaml config.yaml
cp .env.example .env
nano config.yaml   # rotas, fontes, e-mail, agenda
nano .env          # SMTP_SENHA (senha de app do Gmail)
```

> **Atalho**: `.venv/bin/busca-voos init` faz esses dois `cp` (sem sobrescrever
> nada que já exista), cria o banco vazio e mostra os próximos passos.

> **Segurança**: use uma **senha de app** do Gmail
> (https://myaccount.google.com/apppasswords). Se você já deixou uma senha em
> código algum dia (o script antigo tinha uma!), **revogue-a** na conta Google.

## Instalação (Windows)

Na pasta `vs_win/`, tudo por duplo clique:

| Arquivo | O que faz |
|---|---|
| `INSTALAR.bat` | cria o `.venv`, instala app + painel, baixa o Chromium e roda o `init` |
| `RODAR_CICLO.bat` | uma busca agora (`--sem-email` para testar sem enviar e-mail) |
| `RODAR_DAEMON.bat` | busca de hora em hora — deixe a janela aberta |
| `ABRIR_PAINEL.bat` | painel no navegador |

Os mesmos passos na mão (PowerShell), se preferir:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[web]"
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m busca_voos.cli init
.\.venv\Scripts\python.exe -m busca_voos.cli uma --sem-email
```

Precisa de Python 3.10+ (python.org, marcando **"Add python.exe to PATH"**).
Para 24/7 use o **Agendador de Tarefas** apontando para `RODAR_DAEMON.bat` com o
disparador "Ao fazer logon" — o `systemd/busca-voos.service` é só para Linux.

## Uso

```bash
# primeiro uso: cria config.yaml, .env e o banco; não sobrescreve o que existe
.venv/bin/busca-voos init

# teste rápido de uma fonte, sem banco e sem e-mail:
.venv/bin/busca-voos testar skiplagged --origem FLN --destino RIO \
    --ida 2026-12-20 --volta 2027-01-02

# um ciclo completo (rotas do config), alerta só no log:
.venv/bin/busca-voos uma --sem-email

# valida o SMTP:
.venv/bin/busca-voos email-teste

# modo daemon (é isso que roda no systemd):
.venv/bin/busca-voos run

# painel web do histórico (veja "Painel web" abaixo):
.venv/bin/busca-voos painel
```

Opções comuns: `--config caminho.yaml`, `--fontes skiplagged,google_flights`
(sobrepõe o config), `--sem-email`, `--debug`.

### Primeiro uso e o banco

Não existe passo de migration: as tabelas nascem sozinhas na primeira vez que um
ciclo roda ou quando você chama `init`. O schema usa `CREATE TABLE IF NOT EXISTS`,
então rodar de novo nunca apaga nada.

| Situação | O que acontece |
|---|---|
| `busca-voos init` | cria `config.yaml`, `.env` e um banco **vazio** (pronto para o painel) |
| `busca-voos uma` / `run` | cria o banco se faltar e já grava o ciclo 1 |
| Só `busca-voos painel` | **não** cria nada: o painel é somente leitura e avisa que o banco não existe |

O arquivo fica no caminho da chave `banco` do config (`dados.sqlite3` por padrão)
e é **relativo à pasta de onde você roda o comando** — por isso o serviço systemd
define `WorkingDirectory` e o Docker usa `WORKDIR /app`. Para deixar o banco
pronto em 1 segundo, sem tocar na rede: `busca-voos uma --sem-email --fontes kayak`
(fonte ainda não implementada é pulada de propósito).

## Painel web (histórico)

O daemon grava tudo em SQLite; o painel só **lê** esse banco, então pode ficar
aberto enquanto os ciclos rodam (nada é disparado nem enviado por ali).

```bash
.venv/bin/pip install -e ".[web]"     # fastapi + uvicorn (extras opcionais)
.venv/bin/busca-voos painel           # http://127.0.0.1:8787
.venv/bin/busca-voos painel --porta 8788 --abrir
```

No **Windows**, dê duplo clique em `abrir_painel.bat`: ele escolhe um Python que
tenha `fastapi`/`uvicorn`, cria o `config.yaml` se ainda não existir, sobe o
painel e abre o navegador. Fechar a janela (ou Ctrl+C) encerra o painel.

O que a tela mostra: menor preço, último ciclo, ofertas do retrato mais recente
de cada combinação (fonte, rota, ida, volta), melhor preço por rota, alertas já
enviados e o gráfico de preço mínimo por dia. Filtros por rota, fonte, janela de
ida, preço máximo e ordenação; o selo verde compara o preço com o
`preco_maximo` da rota no `config.yaml`.

Rotas da API (JSON, mesmo servidor): `/api/resumo`, `/api/filtros`,
`/api/ofertas`, `/api/alertas`, `/api/historico`; documentação automática em
`/api/docs`. Por padrão o servidor escuta só em `127.0.0.1` — para expor na rede
use `--host 0.0.0.0` consciente de que **não há autenticação**.

## systemd (deixar rodando 24/7)

```bash
sudo cp systemd/busca-voos.service /etc/systemd/system/
sudo nano /etc/systemd/system/busca-voos.service   # ajuste User e caminhos
sudo systemctl daemon-reload
sudo systemctl enable --now busca-voos
journalctl -u busca-voos -f                        # acompanhar logs
```

## Docker (alternativa)

```bash
docker build -t busca-voos .
docker run -d --name busca-voos --env-file .env \
  -v "$PWD/config.yaml:/app/config.yaml:ro" \
  -v "$PWD/dados.sqlite3:/app/dados.sqlite3" \
  busca-voos
```

## Como funciona

```
config.yaml ──> scheduler (ciclo: rotas × fontes)
                  ├── fontes HTTP: google_flights (tfs), skiplagged (API)
                  ├── fontes Playwright: skyscanner, trip_com
                  ├── janelas de datas viram pares (ida, volta), com rodízio
                  │   entre ciclos (agenda.max_combinacoes_por_ciclo)
                  └── SQLite: ofertas, alertas, dedupe
e-mail HTML (rota, datas, preço, fonte, link) quando preço <= preco_maximo
```

### Janelas de datas

Uma rota com `janela_ida: {de, ate}` e `janela_volta: {de, ate}` gera todos os
pares (ida, volta) válidos; cada ciclo testa um subconjunto (`max_combinacoes_por_ciclo`)
girando entre ciclos, então tudo acaba sendo coberto. Para só ida, omita
`janela_volta`. Para datas específicas, use listas: `janela_ida: [2026-12-20, 2026-12-22]`.

### Política de alerta (anti-spam)

E-mail dispara quando o **melhor preço do par (ida, volta) ≤ `preco_maximo`** da
rota e uma destas condições: (1) primeira vez para aquela fonte+datas; (2) já
passaram `dedupe_horas` desde o último alerta; (3) o preço caiu ≥ `queda_realerta_pct`
em relação ao último alerta.

## Bloqueios (realidade de scraping)

- **Skyscanner/Kayak** usam DataDome/Cloudflare: em IP de servidor, podem exibir
  captcha. Mitigações suportadas no config: `navegador.proxy` (proxy residencial),
  `navegador.canal: chrome` (Chrome real), `headless: false` (para debug).
  Quando uma fonte é bloqueada, o app registra o erro e **continua com as outras**.
- **Google Flights** pode pedir consentimento/captcha em IP de datacenter; o
  token `tfs` evita navegador, mas se o Google mudar o markup, a fonte volta
  lista vazia e o log avisa.
- Fonte com problema não derruba o app: cada fonte é isolada.

## Configuração — referência rápida

Ver `config.example.yaml` (comentado) para tudo. Resumo:

```yaml
fontes:
  google_flights: { ativo: true }
  skiplagged:     { ativo: true }
  skyscanner:     { ativo: true }
  trip_com:       { ativo: true }
  kayak:          { ativo: false }   # fase 3
rotas:
  - origem: FLN
    destino: RIO
    janela_ida:   { de: 2026-12-20, ate: 2026-12-26 }
    janela_volta: { de: 2027-01-02, ate: 2027-01-06 }
    preco_maximo: 900
    # fontes: [skiplagged, google_flights]   # opcional por rota
email:
  host: smtp.gmail.com
  porta: 587
  tls: true
  de: buscavoopy@gmail.com
  para: [soutes@gmail.com]
agenda:
  intervalo_minutos: 60
navegador:
  headless: true
  # proxy: http://usuario:senha@host:porta
  # canal: chrome
```

## Estrutura do código

```
busca_voos/
├── vs_win/                    # pacote autocontido p/ Windows (INSTALAR.bat, RODAR_*.bat)
├── vs_linux/                  # pacote autocontido p/ Linux (instalar.sh, systemd/)
├── config.example.yaml        # config comentado (copie para config.yaml)
├── .env.example               # SMTP_SENHA (copie para .env)
├── abrir_painel.bat           # Windows: duplo clique abre o painel
├── pyproject.toml
├── Dockerfile
├── systemd/busca-voos.service
├── spikes/                    # scripts de investigação (não fazem parte do app)
│   ├── teste_painel.py        # teste de fumaça da API do painel (+ fixtures p/ JS)
│   └── teste_painel_js.mjs    # renderiza a página num DOM mínimo (node)
└── src/busca_voos/
    ├── cli.py                 # busca-voos init|uma|run|testar|email-teste|painel
    ├── config.py              # carga/validação do YAML + .env
    ├── models.py              # Rota, Oferta
    ├── combos.py              # janelas de datas -> pares (ida, volta) + rodízio
    ├── db.py                  # SQLite: ofertas, alertas, dedupe, ciclos
    ├── emailer.py             # e-mail HTML
    ├── scheduler.py           # ciclo + daemon
    ├── painel.py              # leitura (somente-leitura) do SQLite p/ o painel
    ├── web.py                 # app FastAPI + endpoints /api/*
    ├── painel.html            # a tela (HTML/CSS/JS puro, sem CDN)
    └── sources/
        ├── base.py            # contrato FonteBase + erros
        ├── extracao.py        # normalização de preço/cia a partir de texto
        ├── navegador.py       # Playwright com disfarce básico
        ├── google_flights.py  # HTTP + token tfs (protobuf)
        ├── skiplagged.py      # API packed.js + fallback navegador
        ├── skyscanner.py      # Playwright
        ├── trip_com.py        # Playwright
        └── __init__.py        # REGISTRO (inclui kayak/latam/gol/azul = fase 3)
```

## Solução de problemas

| Sintoma no log | Causa provável | O que fazer |
|---|---|---|
| `google_flights: nenhum resultado parseado` | Google mudou o markup | Ajustar seletor em `sources/google_flights.py` |
| `skyscanner: anti-bot (DataDome)` | IP bloqueado | Proxy residencial ou `canal: chrome` |
| `skiplagged: pagina sem precos` | API/mudança de markup | Fallback navegador já tenta; conferir com `--debug` |
| `E-mail nao enviado: SMTP_SENHA ausente` | `.env` vazio | Criar senha de app e preencher |
| `painel: precisa de dependencias extras` | faltam fastapi/uvicorn | `pip install -e ".[web]"` |
| `Nao consegui abrir http://...: porta em uso` | já há um painel rodando | use `--porta 8788` |
| Painel mostra "Banco ... nao existe ainda" | nenhum ciclo rodou | rode `busca-voos uma --sem-email` |
| Banco criado na pasta errada | `banco:` é relativo ao cwd | rode o comando da pasta do projeto, ou use caminho absoluto |