# Reorganizacao de Abas de Rotas e Alertas por Rota Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separar a tela de monitoramento em duas abas ("Rotas Monitoradas" e "Cadastrar Rotas"), implementar navegacao por pills para cada rota com subpagina dedicada (KPIs, edicao, historico e ofertas daquela rota), e garantir que os alertas de e-mail sejam acionados e enviados de forma independente por rota.

**Architecture:**
- Backend: Endpoint PUT /api/rotas/{indice} para alteracao de rotas existentes no config.yaml preservando comentarios; no scheduler.py e emailer.py, agrupamento e envio isolado de alertas por rota para garantir que cada rota acione seu proprio e-mail quando a sua regra de preco for atingida.
- Frontend: Refatoracao do cabecalho e views em painel.html: criacao de view-rotas-monitoradas e view-cadastrar-rotas. Na aba Cadastrar Rotas: Robo de Busca e Formulario Nova Rota. Na aba Rotas Monitoradas: seletor por pills horizontais com rotas cadastradas, subpagina com dados da rota ativa, botao "Alterar rota" com modal/formulario de edicao, KPIs dedicados, grafico de historico isolado daquela rota, tabela de ofertas e alertas daquela rota.
- Sync & Multiplataforma: Sincronizacao de todas as alteracoes nos pacotes vs_win/ e vs_linux/.

**Tech Stack:** Python 3.12+, FastAPI, SQLite3, Vanilla JavaScript (DOM puro, zero CDN, sem framework), CSS nativo, Pytest.

**Spec:** Requisito do usuario: divisao da aba Monitoramento em "Rotas Monitoradas" e "Cadastrar Rotas" (com Robo de busca e Nova Rota), pills de selecao de rotas com subpagina completa por rota, botao de edicao de rota, e ajuste do disparo de alertas por e-mail isolado por rota.

## Global Constraints

- NO EMOJIS: NUNCA utilize emojis em respostas, arquivos de codigo, interfaces de usuario (UI), mensagens de commit, nomes de categorias, comentarios ou qualquer outro lugar em NENHUM projeto. Use icones SVG/Lucide ou texto puro.
- PURE DOM: Zero innerHTML com dados nao confiáveis, zero CDN externa para preservar funcionamento offline e conformidade rigorosa com a Content-Security-Policy existente.
- YAML INTEGRITY: A alteracao de rotas deve preservar comentarios e estrutura do config.yaml existente.

## Review Focus

- PUT /api/rotas/{indice} com indice fora dos limites ou dados invalidos (deve retornar HTTP 400 com mensagem clara).
- Subpagina da rota selecionada no frontend ao carregar sem rotas ou com indice de rota inexistente (deve exibir estado amigavel sem quebrar JS).
- Disparo de alertas por e-mail quando uma rota atinge o teto e outra nao (deve disparar e-mail exclusivo da rota que atingiu).
- Grafico de historico e tabela de ofertas filtrados estritamente pela rota selecionada.
- Sincronizacao completa entre pasta src/ e pastas vs_win/ e vs_linux/.

---

### Task 1: Endpoint de Alteracao de Rota e Disparo de Alertas Isolado por Rota

**Files:**
- Create: `tests/test_rotas_email.py`
- Modify: `src/busca_voos/config.py`
- Modify: `src/busca_voos/web.py`
- Modify: `src/busca_voos/emailer.py`
- Modify: `src/busca_voos/scheduler.py`

**Interfaces:**
- `atualizar_rota_config(caminho: Path | str, indice: int, rota_atualizada: dict) -> list[dict]` em `config.py`
- `PUT /api/rotas/{indice}` em `web.py`
- `construir_email_rota(rota: str | Rota, ofertas: list[Oferta]) -> tuple[str, str]` em `emailer.py`
- Envio por rota no `scheduler.py`: agrupa alertas por rota e envia e-mails independentes por rota atingida

- [ ] **Step 1: Escrever teste automatizado para atualizar rota e envio por rota**

Criar `tests/test_rotas_email.py` testando a funcao `atualizar_rota_config`, o endpoint `PUT /api/rotas/{indice}` e a construcao de e-mail por rota.

- [ ] **Step 2: Executar teste para verificar falha**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_rotas_email.py -v`
Expected: FAIL (funcoes ainda nao implementadas)

- [ ] **Step 3: Implementar `atualizar_rota_config` em `src/busca_voos/config.py`**

Adicionar validacao de dados da rota atualizada (origem, destino, janela_ida, janela_volta, preco_maximo, nome) e substituicao da rota no indice correspondente preservando comentarios do YAML.

- [ ] **Step 4: Implementar endpoint `PUT /api/rotas/{indice}` em `src/busca_voos/web.py`**

Expor rota PUT que recebe JSON, chama `atualizar_rota_config` e atualiza `limites[f"{origem}-{destino}"] = preco_maximo`.

- [ ] **Step 5: Implementar construcao e envio de alerta isolado por rota em `src/busca_voos/emailer.py` e `src/busca_voos/scheduler.py`**

Adicionar `construir_email_rota` com assunto específico da rota (ex: `busca_voos - FLN -> RIO por R$ 750 (google_flights)`) e, no `scheduler.py`, agrupar alertas por `melhor.rota` e enviar e-mail por rota para cada rota que tiver alertas qualificados.

- [ ] **Step 6: Executar teste para verificar sucesso**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_rotas_email.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tests/test_rotas_email.py src/busca_voos/config.py src/busca_voos/web.py src/busca_voos/emailer.py src/busca_voos/scheduler.py
git commit -m "feat(rotas): adicionar edicao de rotas via PUT e envio de alertas isolado por rota"
```

---

### Task 2: Separacao das Abas "Rotas Monitoradas" e "Cadastrar Rotas" no Frontend

**Files:**
- Modify: `src/busca_voos/painel.html`

**Interfaces:**
- Abas no header: `#tab-rotas-monitoradas`, `#tab-cadastrar-rotas`, `#tab-gestao`
- `#view-cadastrar-rotas`: Robô de Busca (status, agendador, botao buscar agora) + Slot Nova Rota (formulario de cadastro)
- `#view-rotas-monitoradas`: Seletor por pills (`#pills-rotas`), subpagina da rota ativa com dados da rota, botao "Alterar rota" (`#b-alterar-rota`), modal/painel de edicao, KPIs filtrados da rota, grafico de historico da rota, ofertas e alertas da rota.

- [ ] **Step 1: Ajustar estrutura HTML do header e secoes principais**

Em `src/busca_voos/painel.html`:
- Substituir a aba unica "Monitoramento" pelas abas "Rotas Monitoradas" e "Cadastrar Rotas".
- Criar a secao `#view-cadastrar-rotas` contendo o card "Robô de busca" e o bloco "Nova rota".
- Criar a secao `#view-rotas-monitoradas` contendo a navegacao em pills (`#pills-rotas`) e o container da subpagina da rota ativa.

- [ ] **Step 2: Implementar subpagina da rota e componente de navegacao por pills**

- Renderizar pills horizontais dinâmicos conforme rotas cadastradas.
- Ao clicar em uma pill, definir rota ativa e atualizar:
  - Header da rota: titulo `ORIGEM -> DESTINO`, janelas de datas formatadas, preco teto.
  - Botao "Alterar rota" que abre formulario de edicao pre-preenchido (com campos de origem, destino, datas e preco teto).
  - Chamada `PUT /api/rotas/{indice}` ao salvar alteracao.
  - KPIs exclusivos da rota ativa (menor preco atual, total de cotacoes, ultima checagem).
  - Grafico de historico de precos filtrado exclusivamente para a rota ativa.
  - Tabela de ofertas recentes e alertas enviados filtrados para a rota ativa.

- [ ] **Step 3: Testar navegacao e edicao no navegador**

Iniciar servidor temporario e validar via script de teste ou chamada HTTP que a pagina carrega sem erros de sintaxe ou CSP.

- [ ] **Step 4: Commit**

```bash
git add src/busca_voos/painel.html
git commit -m "feat(painel): separar abas Rotas Monitoradas e Cadastrar Rotas com subpaginas em pills"
```

---

### Task 3: Sincronizacao dos Pacotes vs_win/ e vs_linux/ e Verificacao Final

**Files:**
- Modify: `vs_win/src/busca_voos/...`
- Modify: `vs_linux/src/busca_voos/...`

**Interfaces:**
- Todos os arquivos modificados em `src/busca_voos` replicados fielmente em `vs_win/src/busca_voos` e `vs_linux/src/busca_voos`.

- [ ] **Step 1: Copiar arquivos atualizados para vs_win e vs_linux**

Copiar `config.py`, `web.py`, `scheduler.py`, `emailer.py`, `painel.html` para as arvores `vs_win/` e `vs_linux/`.

- [ ] **Step 2: Executar testes de regressao e testes unitarios**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_rotas_email.py tests/test_aeroportos_backend.py tests/test_intervalo_agendador.py tests/test_limites_de_busca.py -v`
Expected: Todos passando com sucesso.

- [ ] **Step 3: Commit**

```bash
git add vs_win/ vs_linux/
git commit -m "chore(sync): sincronizar atualizacoes de rotas e alertas com vs_win e vs_linux"
```
