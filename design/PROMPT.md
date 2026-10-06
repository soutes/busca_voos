Quero aplicar um redesign visual (soft UI / neumorfismo, temas escuro e claro) no painel do projeto busca_voos, SEM mudar comportamento nem API.

Contexto do projeto:
- Painel: `src/busca_voos/painel.html` (HTML único com <style> e <script> inline), servido pelo FastAPI em `src/busca_voos/web.py` (rota "/").
- Stack: Python + Poetry + FastAPI, JS vanilla. Sem build de front. Roda local e precisa funcionar offline.

Material do design (já está no repositório):
- `design/HANDOFF.md`: especificação completa. LEIA INTEIRO ANTES DE COMEÇAR, principalmente a seção 6 (mapa do painel atual → componentes novos).
- `design/css/tokens.css` e `design/css/busca-voos.css`: CSS pronto (variáveis + componentes com prefixo `bv-`). Use como está; não reescreva os componentes.
- `design/fonts/`: fontes locais (Montserrat, JetBrains Mono).
- `design/telas/*.html`: 5 telas de referência (Monitoramento, Gestão, Primeiro uso, Ciclo rodando, Mobile). São o alvo visual: copie a marcação e as classes delas.
- `assets/*.svg`: logos oficiais (lockup escuro/claro, símbolo, ícone de app).

Decisão técnica (não mude): CSS puro com variáveis + JS vanilla. Nada de Tailwind, React ou CDN.

O que fazer, em etapas, me mostrando o diff de cada uma:
1. Servir estáticos: criar `src/busca_voos/static/{css,fonts,img}` com os arquivos de `design/` e `assets/`, montar `StaticFiles` em `/static` no `web.py`, garantir que o pacote/Dockerfile incluem a pasta.
2. No `painel.html`: trocar o `<style>` antigo pelos dois `<link>`, `<body class="bv-app">`, favicon com o ícone de app, script anti-piscar do tema no `<head>` e botão de tema no cabeçalho (HANDOFF seção 4).
3. Reescrever a marcação estática das duas abas (Monitoramento e Gestão) seguindo `design/telas/`, MANTENDO todos os `id` existentes e os `name`/`value` dos campos.
4. Atualizar as funções JS que geram HTML (KPIs em `#cards`, tabelas de rotas/ofertas/alertas, melhor preço, gráfico em `#grafico`, status do ciclo, badges de senha e cron) para emitir as classes novas. Lógica e chamadas `fetch` intactas.
5. Implementar os estados: primeiro uso (sem rotas), ciclo rodando (progresso + botão desabilitado + "novo"), erro de fonte.
6. Remover todos os emojis da UI e usar os ícones SVG das telas.
7. Rodar os testes (`poetry run pytest`) e me passar o checklist da seção 10 do HANDOFF marcado.

Regras:
- Não altere endpoints, nomes de campos, IDs nem a lógica do robô.
- Se algum elemento do painel atual não tiver par no HANDOFF, me pergunte antes de inventar.
- Trabalhe numa branch nova (ex.: `feat/soft-ui`) e não faça merge.
- Eu estou aprendendo: para cada etapa, explique em linguagem simples o que mudou e por quê.
