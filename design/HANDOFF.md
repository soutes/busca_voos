# Handoff · buscavoos Soft UI (temas escuro e claro)

Redesign do painel local do busca_voos (`src/busca_voos/painel.html`, servido pelo FastAPI em `web.py`).
Fonte da verdade visual: o design system "busca_voos Soft UI" (artefato) e os arquivos desta pasta.

## 1. O que tem nesta pasta

| Caminho | O que é |
|---|---|
| `css/tokens.css` | Todas as variáveis (cores, sombras, espaçamentos, raios, fontes) nos dois temas + `@font-face` locais |
| `css/busca-voos.css` | Todos os componentes, classes com prefixo `bv-` |
| `fonts/*.woff2` | Montserrat 400–800 e JetBrains Mono 400/500/700 (licença OFL), para funcionar offline |
| `telas/*.html` | 5 telas de referência abríveis no navegador, com botão de tema (canto inferior direito) |
| `../assets/*.svg` | Logos oficiais: lockup escuro, lockup claro, símbolo, ícone de app |

Abra `telas/TelaMonitoramento.html` no navegador: é o alvo visual. Copie a marcação de lá.

## 2. Decisão técnica: CSS puro com variáveis (sem Tailwind)

- O painel é **um arquivo HTML servido pelo FastAPI, sem etapa de build**. CSS com variáveis roda direto, sem Node.
- **Os temas são só troca de variáveis**: `<html data-theme="light">` muda tudo. Nada de classes duplicadas `dark:`.
- **Neumorfismo depende de sombras compostas** (`--soft-raised`, `--soft-inset`). Em Tailwind isso viraria `shadow-[...]` arbitrário repetido em todo lugar.
- **O JavaScript continua vanilla.** As tabelas e cards já são gerados por template string; só mudam as classes.
- **Quando Tailwind valeria a pena:** se o painel virar um front separado (React/Next) no SaaS. Nesse caso, os tokens deste arquivo viram o `theme.extend` do Tailwind, sem perder nada.

## 3. Como ligar no app

1. Criar `src/busca_voos/static/` e copiar `css/` e `fonts/` para lá (mantendo `static/css` e `static/fonts`). Copiar também os 4 SVGs de `assets/` para `static/img/`.
2. Em `web.py`: `app.mount("/static", StaticFiles(directory=Path(__file__).with_name("static")), name="static")`.
3. No `<head>` do `painel.html`: remover o `<style>` antigo e usar `<link rel="stylesheet" href="/static/css/tokens.css">` + `<link rel="stylesheet" href="/static/css/busca-voos.css">`.
4. `<body class="bv-app">`. Favicon: `/static/img/busca-voos-app-icon.svg`.
5. Garantir que o pacote inclui `static/` (pyproject: `include`/package data) e o Dockerfile copia a pasta.

## 4. Temas

- Padrão: **escuro**. Claro via `document.documentElement.dataset.theme = 'light'`.
- Botão de tema no cabeçalho, à direita das abas: `button.bv-btn.bv-btn--icon` com ícone de sol/lua e `aria-label="Alternar tema"`.
- Guardar a escolha em `localStorage` (`bv-tema`) dentro de try/catch. Aplicar no `<head>` antes de pintar, para não piscar:
  `<script>try{var t=localStorage.getItem('bv-tema');if(t)document.documentElement.dataset.theme=t}catch(e){}</script>`
- Primeiro acesso sem escolha: pode seguir `prefers-color-scheme`.

## 5. Tokens

### Cores

| Token | Escuro | Claro | Uso |
|---|---|---|---|
| `--base` | `#16181e` | `#e6e9ef` | Fundo da página E de todo card/botão/campo |
| `--base-deep` | `#101216` | `#dde1e8` | Poços de dados: gráfico, cabeçalho de tabela, código |
| `--shade` | `#0b0c0f` | `#b9bfca` | Cor da sombra (só dentro de sombras) |
| `--line` | `#252932` | `#d3d8e0` | Linha fina entre linhas de tabela |
| `--ink` | `#f8fafc` | `#12151b` | Texto principal, valores |
| `--ink-2` | `#a3b0c2` | `#475569` | Texto secundário, células |
| `--ink-3` | `#7f8da3` | `#566173` | Rótulos, placeholders, meta |
| `--accent` | `#f7941d` | `#f7941d` | Laranja LUAS como preenchimento (botão principal, switch ligado, gráfico) |
| `--on-accent` | `#0a0b0e` | `#12151b` | Texto sobre laranja (nunca branco) |
| `--accent-text` | `#f7941d` | `#9a4d00` | Laranja como texto (aba ativa, links, menor preço) |
| `--accent-soft` | laranja 14% | laranja 18% | Fundo de badge laranja, hover de linha |
| `--success` | `#34d399` | `#03684b` | Preço dentro do teto, ciclo concluído, ativo |
| `--danger` | `#f87171` | `#b91c1c` | Excluir, erro (só texto/ícone) |
| `--focus` | `#f7941d` | `#9a4d00` | Anel de foco 2px |
| `--brand-yellow` | `#fbbf24` | `#fbbf24` | Só no quadro de exploração de logos. Não usar na UI |

Todos os pares de texto passam 4,5:1 nos dois temas.

### Sombras (sem realce claro: uma sombra escura só)

| Token | Escuro | Claro | Onde |
|---|---|---|---|
| `--soft-raised` | `8px 8px 18px #0b0c0f` | `8px 8px 18px #b9bfca` | Cards, KPIs |
| `--soft-raised-sm` | `4px 4px 10px #0b0c0f` | `4px 4px 10px #b9bfca` | Botões, badges, knob |
| `--soft-inset` | `inset 6px 6px 12px #0b0c0f` | `inset 6px 6px 12px #b9bfca` | Poços: gráfico, ajuda, fonte selecionada |
| `--soft-inset-sm` | `inset 3px 3px 6px …` | `inset 3px 3px 6px …` | Campos, trilho do switch, botão pressionado |
| `--accent-glow` | `0 6px 18px rgba(247,148,29,.32)` | igual | Só botão principal e switch ligado |

### Tipografia, espaço, raio

- Sans `Montserrat`: título 22/28 800 · KPI 28/34 700 · seção 16/22 700 · corpo 14/21 500 · pequeno 12.5/18 500.
- Mono `JetBrains Mono`: rótulo 11/14 500 maiúsculas +0.08em · dados 13/18 500 · preço 15/20 700.
- Espaço: 4, 8, 12, 16, 20, 24, 32, 40 (`--space-1`…`--space-10`). Card padding 24; gap entre cards 24; entre seções 32.
- Raio: 10 (campos) · 14 (botões, tabelas) · 22 (cards) · 999 (badges, switch, abas).

## 6. Mapa: painel atual → componentes novos

Manter **todos os IDs e chamadas de API**. Só troca marcação/classes.

| Hoje (`painel.html`) | Vira | Referência |
|---|---|---|
| `h1 ✈️ busca_voos` + `#painel-versao` | `.bv-header` > `.bv-brand` com o lockup SVG inline + `.bv-badge--flat` da versão | topo de qualquer tela |
| `#tab-painel`, `#tab-gestao` (`.tab-btn`) | `nav.bv-tabs` > `button.bv-tab` (`.is-active`) com ícones, sem emoji | cabeçalho |
| `#cards` (5 KPIs gerados por JS) | `.bv-grid--kpi` > 5× `.bv-kpi` (menor preço com `.bv-kpi--accent`) | KPIs |
| `#sec-rotas` (tabela de rotas + form) | Card "Rotas monitoradas" à esquerda do `.bv-grid--main` | Monitoramento |
| `#form-rotas` (`#r-origem`…`#r-preco`, `#b-add-rota`) | `.bv-well` "Nova rota" com `.bv-field` em grade de 4 colunas | Monitoramento |
| `#lista-rotas-card` | `.bv-table` com rota, janelas, teto e botão ícone excluir `.bv-btn--danger` | Monitoramento |
| `#painel-cron` (`#cron-ativo`, `#cron-horas`, `#cron-contagem`), `#b-ciclo`, `#status-ciclo` | Card "Robô de busca" à direita: `.bv-switch` + `.bv-select` + `.bv-badge` + botão `.bv-btn--primary.bv-btn--lg` + `.bv-status` | Monitoramento / Ciclo rodando |
| `#diagnostico-ciclo` | `.bv-status` + `.bv-progress` dentro do card Robô | Ciclo rodando |
| Filtros `#f-rota`…`#f-auto`, `#b-atualizar`, `#b-limpar` | `.bv-well` "Explorar ofertas" com `.bv-form`; Atualizar = Aplicar (primário), Limpar = botão ícone × | Monitoramento |
| `#grafico` | Card "Histórico do menor preço" com `.bv-chart` (SVG inline: grade, linha teto tracejada verde, área, pontos) | Monitoramento |
| `#rotas` (melhor preço por rota) | Card "Melhor preço por rota" com `.bv-well` e preço grande | Monitoramento |
| `#ofertas` | `.bv-table` com `.bv-price` (`--hit` quando ≤ teto), `.bv-route`, `.bv-airline`, link "Abrir" | Monitoramento |
| `#alertas` | `.bv-table` com status `.bv-badge--success` "enviado" | Monitoramento |
| `#view-gestao` cards | `.bv-grid--main`: e-mail à esquerda; Agendamento + "Seus dados ficam aqui" à direita; Plataformas embaixo; barra Salvar | Gestão |
| `#btn-ajuda-email`, `#painel-ajuda-email` | botão `.bv-btn--sm` (fica `.is-pressed` aberto) + `.bv-help` com `.bv-steps` e `.bv-providers` | Gestão |
| `#cfg-email-*`, `#badge-senha-status`, `#b-testar-email` | `.bv-field` + `.bv-input-wrap` com ícones; badge `.bv-badge--success`; switch TLS | Gestão |
| `#cfg-fonte-*` (`.card-fonte-check`) | `label.bv-source` (marcado = afundado + tick laranja) | Gestão |
| `#cfg-cron-*` | Card "Agendamento" | Gestão |
| `#b-salvar-cfg` | Barra `.bv-card` com status "alterações não salvas" + Descartar + Salvar (primário) | Gestão |
| `.rodape` | `.bv-footer` com "feito por luas ai.s" | todas |

## 7. Estados

- **Primeiro uso** (sem rotas): KPIs com "—"/"0", estado vazio `.bv-empty` no card de rotas, form destacado com botão primário, botão Buscar desabilitado, 3 passos de onboarding.
- **Ciclo rodando**: badge `.bv-badge--accent.bv-badge--live` "Buscando", `.bv-progress` com combinações feitas/total, botão "Buscando voos…" desabilitado, linhas novas com badge "novo".
- **Erro de fonte**: `.bv-status--danger` com o motivo (ex.: captcha do Skyscanner) sem parar o ciclo.
- **Hover**: elevados sobem 1px e o texto vira `--accent-text`. **Pressionado**: `--soft-inset-sm`. **Desabilitado**: afundado, texto `--ink-3`.
- **Foco**: `outline: 2px solid var(--focus); outline-offset: 3px` em tudo que é clicável.

## 8. Regras de conteúdo

- Sem emoji na interface: usar os ícones de traço (estilo Lucide, 1.8px). Pode usar o pacote `lucide` (ou copiar os SVGs inline das telas).
- Português simples: "Robô de busca", "Preço teto", "Agendador automático".
- Dinheiro `R$ 1.485,00`; datas `27/12/2026` ou `27/12`; rotas `FLN → RIO`.
- Verde sempre com palavra ("≤ teto", "ativo", "enviado"); laranja só na ação principal de cada card.

## 9. Responsivo

- ≥ 1100px: layout das telas desktop.
- 700–1100px: `.bv-grid--kpi` em 3 colunas; `.bv-grid--main` e `.bv-grid--2` em 1 coluna.
- < 700px: seguir `telas/TelaMobile.html` (KPI de menor preço em destaque, 2 KPIs, card do robô, ofertas em cards, abas embaixo). Tabelas largas rolam na horizontal dentro de `.bv-table-wrap`.

## 10. Checklist de aceite

- [ ] Nenhuma API, ID ou comportamento JS quebrado (rodar os testes em `tests/`).
- [ ] As 5 telas batem com `telas/*.html` nos dois temas.
- [ ] Troca de tema funciona e persiste; sem piscar ao recarregar.
- [ ] Funciona offline (fontes locais, nenhum CDN).
- [ ] Foco visível em tudo; contraste ok no tema claro.
- [ ] Nenhum emoji restante na UI.
