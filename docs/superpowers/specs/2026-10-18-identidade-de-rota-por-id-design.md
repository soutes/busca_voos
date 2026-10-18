# Identidade de Rota por ID (Design)

## Contexto e problema

Hoje a identidade de uma rota e, em todo o sistema, a string `ORIGEM-DESTINO`
(ex.: `FLN-SAO`):

- `config.yaml` -> `models.Rota.id` (propriedade derivada);
- `sources/base.py` grava `Oferta.rota = f"{origem}-{destino}"`;
- colunas `ofertas.rota` e `alertas.rota` no SQLite;
- filtros e agrupamentos do painel (`painel.py`, `web.py`, `painel.html`);
- chave do dicionario `limites` (teto por rota).

Consequencia: duas rotas cadastradas com o mesmo par colidem. Evidencia no banco
trazido de outra maquina (2671 ofertas, 6 alertas, `meta.ciclo=60`):

| Gravado em `rota='FLN-SAO'` | Rota real |
|---|---|
| `data_volta=null`, ida 04/11, R$ 293 | rota "IDA SP" (so ida, teto R$ 300) |
| `data_volta=05/11` e `06/11`, ida 03-04/11, min R$ 590 | rota "Sao Paulo" (ida+volta, teto R$ 500) |

O R$ 293 (que e so ida) aparece no card "MENOR PRECO" das duas rotas, e o teto
500/300 se sobrescreve porque `limites` e indexado pelo par. Os cards, o grafico
"Historico do menor preco da rota", o "retrato de ofertas" e os "alertas
enviados da rota" ficam iguais para rotas distintas do mesmo par.

## Objetivo e criterios de sucesso

- Cada rota cadastrada tem um **ID unico e estavel**, gravado junto de ofertas e
  alertas no banco.
- Os KPIs, o historico do menor preco, o retrato de ofertas e os alertas da rota
  passam a filtrar/agrupar pelo ID.
- Duas rotas com o mesmo `ORIGEM-DESTINO` (1 trecho x 2 trechos, ou qualquer
  duplicata) sao acompanhadas de forma independente, cada uma com a sua serie
  temporal.
- Nenhuma regressao: e-mails com rotulo legivel (`FLN -> SAO`), fontes inalteradas.

## Decisoes

1. **ID automatico e nao editavel.** Base `ORIGEM-DESTINO`; em caso de repeticao,
   sufixo `-2`, `-3`, ... O app gera e grava no `config.yaml`. O usuario nunca
   digita ID. O ID acompanha o par: muda se voce trocar origem/destino (e o
   historico do par antigo fica orfao); trocar datas, teto ou nome **preserva** o
   ID e a serie temporal continua. Isso mantem coerencia com os testes atuais
   (`assert r0["id"] == "FLN-BSB"` apos editar o par).
2. **Trechos importam.** Uma rota pode ser 1 trecho (so ida: sem `janela_volta`)
   ou 2 trechos (ida+volta). Essas duas sao rotas diferentes e nao podem
   compartilhar serie temporal.
3. **Migracao do historico antigo por trecho/janela.** As linhas antigas (sem
   ID) sao atribuidas a rota que casa por par + trecho + janela de datas; empate
   ou ambiquidade cai na primeira rota do par na ordem do arquivo.

## Desenho por camada

### 1. Identidade no `config.yaml`

- Cada item de `rotas` ganha `id: <str>`.
- `carregar_config`: usa o `id` se existir; se faltar, gera pelo criterio acima,
  na ordem do arquivo (deterministico). IDs repetidos no arquivo = `ErroConfig`.
- `listar_rotas_dict` devolve `id` (e o `janela_volta`, que ja denota o trecho).
- `adicionar_rota_config` atribui um `id` livre.
- `atualizar_rota_config`: preserva o `id` da rota editada quando origem e destino
  sao mantidos (datas, teto ou nome mudam a serie, nao a identidade); se origem ou
  destino mudam, o `id` e regerado a partir do novo par (sufixo `-2` se preciso)
  e o historico do par antigo deixa de casar.
- `obter_configuracoes_gestao` / `salvar_configuracoes_gestao` nao podem descartar
  o `id` ao reescrever rotas.
- `config.example.yaml` e README documentam o campo como preenchido sozinho.

### 2. Modelo e banco

- `models.Rota`: campo `id: str = ""`, preenchido em `__post_init__` com
  `f"{origem}-{destino}"` quando vazio (nao quebra construcoes diretas em testes).
- `models.Oferta`: campo `rota_id: str = ""`.
- `db.py`:
  - `_SCHEMA` acrescenta `rota_id TEXT NOT NULL DEFAULT ''` em `ofertas` e
    `alertas`. A coluna `rota` (texto) **continua**, apenas para exibicao.
  - `_garantir_coluna_rota_id`: em bancos existentes, `PRAGMA table_info` e
    `ALTER TABLE ... ADD COLUMN rota_id TEXT NOT NULL DEFAULT ''` (so adiciona).
  - `salvar_ofertas` grava `rota_id`.
  - Dedupe: `_ultimo_alerta`, `deve_alertar` e `registrar_alerta` passam a
    chavear por `rota_id` (mais `data_ida`/`data_volta`). `registrar_alerta`
    recebe `rota_id` como parametro nomeado com default `""`, preservando as
    chamadas posicionais existentes nos testes.
  - `migrar_rota_ids(rotas)`: preenche `rota_id` vazio nas duas tabelas
    (idempotente). Ver secao "Regras da migracao".

### 3. Coleta (agendador e fontes)

- **Fontes inalteradas**: continuam devolvendo `Oferta.rota = ORIGEM-DESTINO`.
- Em `scheduler.ciclo()`, logo apos `fonte.buscar(...)`, carimba
  `oferta.rota_id = rota.id` em cada oferta antes de `banco.salvar_ofertas`.
- Dedupe e alerta usam `rota.id`.
- E-mail mantem o rotulo legivel: `construir_email_rota(f"{origem}-{destino}", ...)`,
  sem o sufixo do ID no assunto.

### 4. Consultas e API

- `painel.py`: CTE `ULTIMAS` particiona por `fonte, rota_id, data_ida, data_volta`;
  `resumo` agrupa por `rota_id` (cada item de `por_rota` expoe `rota_id` e o texto
  `rota`); `contar_ofertas`, `listar_ofertas`, `historico` e `listar_alertas`
  filtram por `rota_id`; `filtros` devolve `rotas` como ids distintos (o select
  `f-rota` esta oculto hoje, mas fica coerente).
- `web.py`: `/api/filtros` devolve `limites` indexado pelo **id**;
  `/api/ofertas`, `/api/alertas` e `/api/historico` aceitam `rota_id`;
  adicionar/editar/remover rota reconstroem `limites` usando `r["id"]`.
- `cli.py`: monta `limites` (passado a `servir`) com chave = id da rota.

### 5. Tela (`painel.html`)

- O estado da rota ativa passa a ser o **id** (`estado.rotaId`); as pills e o
  `f-rota` usam o id como valor e exibem `ORIGEM -> DESTINO` (+ nome) como rotulo.
- KPIs, grafico, retrato de ofertas e alertas consultam por `rota_id`; o teto
  (`limites`) vem por id.
- Nas tabelas, a celula de rota mostra o par e, quando houver, o nome da rota
  (para desempatar as duas `FLN->SAO`).

### 6. Execucao da migracao

- Roda no inicio de `ciclo()` e na subida do painel (`criar_app`), best-effort.
- E aditiva e idempotente; nao apaga nem reescreve historico. A observacao
  "somente leitura" do painel vale para os endpoints de leitura; a migracao so
  adiciona coluna e preenche vazios.

## Regras da migracao

Para cada linha (`ofertas` e `alertas`) com `rota_id` vazio:

1. `candidatas` = rotas cujo `f"{origem}-{destino}"` == `linha.rota`.
   - Vazio -> mantem `rota_id` vazio (rota removida do config; a linha nao
     aparece em nenhuma rota).
2. Filtra por trecho:
   - `linha.data_volta IS NULL` -> apenas rotas sem `janela_volta` (so ida).
   - `linha.data_volta IS NOT NULL` -> apenas rotas com `janela_volta`.
3. Filtra por janela:
   - `data_ida` dentro de `[min(datas_ida), max(datas_ida)]` da rota;
   - se houver `data_volta` e a rota tiver `datas_volta`, `data_volta` dentro de
     `[min(datas_volta), max(datas_volta)]`.
4. Escolha:
   - exatamente uma -> essa rota;
   - mais de uma -> a primeira na ordem do config (deterministico);
   - nenhuma apos os filtros -> a primeira candidata por par (fallback);
   - nenhuma candidata -> mantem vazio.

Exemplo (banco atual): `FLN-SAO` com `volta=null` vai para a rota so-ida
(R$ 293); `FLN-SAO` com `volta=05/11` ou `06/11` vai para a rota ida+volta.

## Testes

- `config`: id gerado, unico com duplicatas (`FLN-SAO`, `FLN-SAO-2`), preservado
  no update, novo no add, `ErroConfig` em id repetido explicito.
- Migracao: separa o R$ 293 so-ida da tarifa ida+volta; `rota_id` vazio em linha
  orfa; idempotente (rodar duas vezes nao muda nada).
- `db`: schema com `rota_id`; dedupe por `rota_id` (duas rotas do mesmo par nao
  se suprimem com janelas de dedupe diferentes).
- `painel`: `resumo`/`historico`/`listar_ofertas`/`listar_alertas` por `rota_id`;
  duas rotas do mesmo par devolvem numeros distintos.
- `web`: `/api/filtros` com `limites` por id; endpoints aceitam `rota_id`.
- Ajustar testes que hoje esperam `limites["FLN-GIG"]` (passam a esperar por id).

## Restricoes

- SEM EMOJIS em nenhum arquivo/texto/mensagem.
- DOM PURO no front: sem `innerHTML` com dado nao confiavel, sem CDN.
- Integridade do YAML: editar rotas preserva comentarios e estrutura.
- Sincronizar `src/` -> `vs_win/` e `vs_linux/` (copias byte a byte, como hoje).
- Retrocompatibilidade de assinaturas publicas usadas nos testes existentes.

## Pendencias

- `config.yaml` com as 4 rotas (o desta maquina so tem 2: `FLN-RIO` e a
  `FLN-SAO` ida+volta). Necessario para a migracao separar as duas `FLN-SAO`;
  sem ele a separacao fica para quando o config completo estiver presente.

## Fora de escopo

- Renomear/remover a coluna `rota`; mexer nas fontes; mudar o assunto dos
  e-mails; suportar mais de dois trechos.
