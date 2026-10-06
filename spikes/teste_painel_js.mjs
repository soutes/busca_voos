/**
 * Executa o JS do painel num DOM minimo, usando as respostas reais que
 * `spikes/teste_painel.py` gravou em `spikes/_saida_painel/`.
 * Verifica o que o teste de API nao alcanca: se a pagina realmente renderiza.
 *
 * Uso: python spikes/teste_painel.py && node spikes/teste_painel_js.mjs
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const spikes = path.dirname(fileURLToPath(import.meta.url));
const projeto = path.dirname(spikes);
const base = path.join(spikes, "_saida_painel");
const ler = (n) => JSON.parse(readFileSync(path.join(base, n), "utf8"));

const payloads = {
  "/api/filtros": ler("filtros.json"),
  "/api/resumo": ler("resumo.json"),
  "/api/ofertas": ler("ofertas.json"),
  "/api/alertas": ler("alertas.json"),
  "/api/historico": ler("historico.json"),
  "/api/rotas": ler("rotas.json"),
  "/api/ciclo/status": ler("ciclo_status.json"),
  "/api/aeroportos": ler("aeroportos.json"),
  "/api/cron": ler("cron.json"),
  "/api/configuracoes": ler("configuracoes.json"),
  "/api/versao": ler("versao.json"),
};

const falhas = [];
const checar = (nome, cond, extra = "") => {
  console.log((cond ? "  OK    " : "  FALHOU") + " " + nome + (cond ? "" : `  -> ${JSON.stringify(extra)}`));
  if (!cond) falhas.push(nome);
};

// ------------------------------- DOM minimo -------------------------------
class No {
  constructor(tag) {
    this.tagName = tag;
    this.attrs = {};
    this.children = [];
    this._texto = "";
    this.className = "";
    this.value = "";
    this.disabled = false;
    this.checked = false;
    this.style = {};
    this.handlers = {};
    const self = this;
    this.classList = {
      add: (c) => { if (!self.className.split(/\s+/).includes(c)) self.className = (self.className + " " + c).trim(); },
      remove: (c) => { self.className = self.className.split(/\s+/).filter((x) => x !== c).join(" "); },
      contains: (c) => self.className.split(/\s+/).includes(c),
      toString: () => self.className,
    };
  }
  get textContent() { return this._texto + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this._texto = String(v); this.children = []; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === "class") this.className = String(v); }
  getAttribute(k) { return this.attrs[k] ?? null; }
  append(...nos) { for (const n of nos) if (n !== null && n !== undefined) this.children.push(n); }
  appendChild(n) { this.children.push(n); return n; }
  removeChild(n) { this.children = this.children.filter((c) => c !== n); return n; }
  get firstChild() { return this.children[0] ?? null; }
  addEventListener(tipo, fn) { (this.handlers[tipo] ||= []).push(fn); }
  get innerText() { return this.textContent; }
}

const IDS = ["aviso", "cards", "grafico", "rotas", "ofertas", "alertas", "c-hist", "c-rotas",
  "c-ofertas", "c-alertas", "f-rota", "f-fonte", "f-de", "f-ate", "f-preco", "f-ordem",
  "f-limite", "f-auto", "b-atualizar", "b-limpar",
  // Rotas monitoradas e ciclo
  "c-rotas-cfg", "lista-rotas-card", "aviso-rotas", "form-rotas",
  "r-origem", "r-destino", "r-ida-de", "r-ida-ate", "r-volta-de", "r-volta-ate", "r-preco",
  "b-add-rota", "b-ciclo", "status-ciclo",
  // Catalogo de aeroportos e diagnostico
  "lista-aeroportos", "selo-origem", "selo-destino", "diagnostico-ciclo",
  // Agendador cron
  "painel-cron", "cron-ativo", "cron-horas", "cron-contagem",
  // Navegacao por abas
  "painel-versao", "tab-painel", "tab-gestao", "view-painel", "view-gestao",
  // Aba de gestao
  "aviso-gestao", "btn-ajuda-email", "painel-ajuda-email", "btn-fechar-ajuda",
  "preset-email", "cfg-email-host", "cfg-email-porta", "cfg-email-tls",
  "cfg-email-de", "cfg-email-para", "cfg-email-senha", "badge-senha-status", "b-testar-email",
  "cfg-fonte-google-flights", "cfg-fonte-trip-com", "cfg-fonte-skyscanner", "cfg-fonte-skiplagged",
  "cfg-cron-ativo", "cfg-cron-horas", "cfg-cron-status", "b-salvar-cfg",
  // Redesign soft UI
  "b-tema", "badge-buscando", "progresso-ciclo", "progresso-contagem", "progresso-detalhe",
  "legenda-grafico", "onboarding", "well-nova-rota", "status-cfg", "b-descartar", "c-fontes"];
const registro = Object.fromEntries(IDS.map((id) => [id, new No("div")]));
for (const id of ["f-rota", "f-fonte", "f-ordem", "f-limite", "cron-horas", "preset-email", "cfg-cron-horas"]) registro[id].tagName = "select";
registro["lista-aeroportos"].tagName = "datalist";
for (const id of ["cron-ativo", "cfg-email-tls", "cfg-fonte-google-flights", "cfg-fonte-trip-com", "cfg-fonte-skyscanner", "cfg-fonte-skiplagged", "cfg-cron-ativo"]) {
  registro[id].tagName = "input";
  registro[id].attrs["type"] = "checkbox";
}
for (const id of ["cfg-email-host", "cfg-email-porta", "cfg-email-de", "cfg-email-para", "cfg-email-senha"]) {
  registro[id].tagName = "input";
}
for (const id of ["tab-painel", "tab-gestao", "btn-ajuda-email", "btn-fechar-ajuda", "b-testar-email", "b-salvar-cfg"]) {
  registro[id].tagName = "button";
}
registro["tab-painel"].className = "bv-tab is-active";
registro["tab-gestao"].className = "bv-tab";
for (const id of ["badge-buscando", "progresso-ciclo", "onboarding"]) registro[id].hidden = true;
registro["view-gestao"].style = { display: "none" };
registro["view-painel"].style = { display: "block" };
registro["painel-ajuda-email"].style = { display: "none" };

const document = {
  createElement: (t) => new No(t),
  createElementNS: (_ns, t) => new No(t),
  getElementById: (id) => registro[id] ?? null,
};
const janela = { location: { origin: "http://127.0.0.1:8799" } };

const chamadas = [];
const fetchFalso = async (url, init = {}) => {
  const rota = String(url).split("?")[0];
  chamadas.push(String(url));
  const metodo = (init.method || "GET").toUpperCase();
  if (metodo === "POST" && rota === "/api/rotas") {
    return { ok: true, status: 200, statusText: "OK", json: async () => ({ ok: true, rotas: payloads["/api/rotas"].rotas }) };
  }
  if (metodo === "DELETE" && rota.startsWith("/api/rotas/")) {
    return { ok: true, status: 200, statusText: "OK", json: async () => ({ ok: true, rotas: [] }) };
  }
  if (metodo === "POST" && rota === "/api/ciclo") {
    return { ok: true, status: 200, statusText: "OK", json: async () => ({ ok: true, status: "iniciado" }) };
  }
  if (metodo === "POST" && rota === "/api/cron") {
    const corpo = typeof init.body === "string" ? JSON.parse(init.body) : (init.body || {});
    const ativo = Boolean(corpo.ativo);
    const horas = Number(corpo.intervalo_horas || 1);
    const atualizado = {
      ...payloads["/api/cron"],
      ativo: ativo,
      intervalo_horas: horas,
      intervalo_minutos: Math.round(horas * 60),
      segundos_restantes: ativo ? Math.round(horas * 3600) : null,
      proxima_execucao: ativo ? new Date(Date.now() + horas * 3600000).toISOString() : null,
    };
    payloads["/api/cron"] = atualizado;
    return { ok: true, status: 200, statusText: "OK", json: async () => atualizado };
  }
  if (metodo === "POST" && rota === "/api/configuracoes") {
    const corpo = typeof init.body === "string" ? JSON.parse(init.body) : (init.body || {});
    const cfgAtual = payloads["/api/configuracoes"] || {};
    const atualizado = {
      ...cfgAtual,
      email: { ...cfgAtual.email, ...(corpo.email || {}) },
      fontes: { ...cfgAtual.fontes, ...(corpo.fontes || {}) },
      cron: { ...cfgAtual.cron, ...(corpo.cron || {}) },
    };
    payloads["/api/configuracoes"] = atualizado;
    return { ok: true, status: 200, statusText: "OK", json: async () => ({ ok: true, configuracoes: atualizado }) };
  }
  if (metodo === "POST" && rota === "/api/email/testar") {
    return { ok: true, status: 200, statusText: "OK", json: async () => ({ ok: true, mensagem: "E-mail de teste enviado com sucesso!" }) };
  }
  if (rota === "/api/aeroportos") {
    const u = new URL(url, "http://127.0.0.1");
    const q = (u.searchParams.get("q") || "").toUpperCase();
    if (q) {
      const todos = (payloads["/api/aeroportos"]?.aeroportos || []);
      const filtrados = todos.filter((a) => a.codigo === q || (a.cidade && a.cidade.toUpperCase().includes(q)));
      return { ok: true, status: 200, statusText: "OK", json: async () => ({ aeroportos: filtrados }) };
    }
  }
  const corpo = payloads[rota];
  if (!corpo) return { ok: false, status: 404, statusText: "Not Found", json: async () => ({ detail: "rota nao mapeada: " + rota }) };
  return { ok: true, status: 200, statusText: "OK", json: async () => corpo };
};

// --------------------------- carrega o script ---------------------------
const html = readFileSync(path.join(projeto, "src", "busca_voos", "painel.html"), "utf8");
const m = html.match(/<script>([\s\S]*?)<\/script>/);
checar("painel.html tem um <script> embutido", !!m);
const codigo = m[1];

// procura erros de sintaxe antes de executar
new Function("document", "window", "fetch", "Node", "Intl", "URL", "setInterval", "clearInterval", "console", codigo);
console.log("  OK     sintaxe do script valida");

process.on("unhandledRejection", (e) => console.log("!! promessa rejeitada sem tratamento:", e));
try {
  new Function("document", "window", "fetch", "Node", "Intl", "URL", "setInterval", "clearInterval", "console", codigo)(
    document, janela, fetchFalso, No, Intl, URL, setInterval, clearInterval, console
  );
  console.log("  OK     script executado sem excecao sincrona");
} catch (e) {
  console.log("!! excecao ao executar o script:", e);
}
console.log("  ..     chamadas logo apos executar:", chamadas.length);

// ------------------------------- espera -------------------------------
const espera = (ms) => new Promise((r) => setTimeout(r, ms));
for (let i = 0; i < 60; i++) {
  await espera(10);
  if (registro["ofertas"].children.length && registro["cards"].children.length > 1 && registro["lista-rotas-card"].children.length) break;
}

const achar = (no, pred, saida = []) => {
  if (pred(no)) saida.push(no);
  for (const c of no.children) achar(c, pred, saida);
  return saida;
};
const linhasDe = (no) => {
  const tbody = achar(no, (n) => n.tagName === "tbody")[0];
  return tbody ? tbody.children.filter((tr) => tr.tagName === "tr") : [];
};
const textos = (nos) => nos.map((n) => n.textContent);

// ------------------------------- asserts -------------------------------
console.log("\n== chamadas feitas pela pagina ==");
for (const rota of ["/api/resumo", "/api/filtros", "/api/ofertas", "/api/alertas", "/api/historico", "/api/rotas", "/api/ciclo/status", "/api/aeroportos", "/api/cron", "/api/configuracoes", "/api/versao"]) {
  checar(`chamou ${rota}`, chamadas.some((u) => u.startsWith(rota)), chamadas);
}

console.log("\n== cards ==");
const cards = registro["cards"].children;
checar("5 cards de KPI", cards.length === 5, cards.length);
checar("menor preco no primeiro card", /R\$\s*750,00/.test(cards[0].textContent), cards[0].textContent);
checar("card de ciclo = 6", cards[1].textContent.includes("6"), cards[1].textContent);

console.log("\n== rotas monitoradas e ciclo ==");
const linhasRotasCfg = linhasDe(registro["lista-rotas-card"]);
checar("rotas configuradas renderizadas", linhasRotasCfg.length === payloads["/api/rotas"].rotas.length, linhasRotasCfg.length);
if (linhasRotasCfg.length) {
  checar("coluna de rota contem origem e destino", linhasRotasCfg[0].children[0].textContent.includes("FLN") && linhasRotasCfg[0].children[0].textContent.includes("RIO"), linhasRotasCfg[0].children[0].textContent);
  checar("coluna de acoes tem botao excluir", achar(linhasRotasCfg[0], (n) => n.tagName === "button" && (n.getAttribute("aria-label") || "").startsWith("Excluir rota")).length === 1);
}
checar("status inicial do ciclo exibido", registro["status-ciclo"].textContent.includes("Pronto para buscar"), registro["status-ciclo"].textContent);
checar("funcoes de rotas expostas em window", typeof janela.carregarRotas === "function" && typeof janela.adicionarRota === "function" && typeof janela.removerRota === "function" && typeof janela.dispararCiclo === "function" && typeof janela.verificarCicloStatus === "function");

console.log("\n== tabelas ==");
const linhasOfertas = linhasDe(registro["ofertas"]);
checar("ofertas renderizadas", linhasOfertas.length === payloads["/api/ofertas"].ofertas.length, linhasOfertas.length);
checar("melhor preco por rota renderizado (um poco por rota)", registro["rotas"].children.filter((n) => n.className.includes("bv-well")).length === payloads["/api/resumo"].por_rota.length);
checar("alertas renderizados", linhasDe(registro["alertas"]).length === payloads["/api/alertas"].alertas.length);
checar("contagem de ofertas na tela", /9 de 9/.test(registro["c-ofertas"].textContent), registro["c-ofertas"].textContent);
checar("selecao de rota preenchida", registro["f-rota"].children.length === 4, registro["f-rota"].children.length);
checar("selecao de fonte preenchida", registro["f-fonte"].children.length === 4, registro["f-fonte"].children.length);

console.log("\n== conteudo das celulas ==");
// a celula de preco tem o valor no 1o filho e o selo de limite no restante
const numeroBR = (t) => {
  const m = String(t).match(/([\d.]+),(\d{2})/);
  return m ? Number(m[1].replace(/\./g, "") + "." + m[2]) : NaN;
};
const primeiroPreco = linhasOfertas[0].children[0].children[0].textContent;
checar("preco formatado em BRL", /R\$\s*750,00/.test(primeiroPreco), primeiroPreco);
checar("marca de teto aplicada (<= R$ 800)", /≤ teto/.test(linhasOfertas[0].children[0].textContent), linhasOfertas[0].children[0].textContent);
const precos = linhasOfertas.map((tr) => numeroBR(tr.children[0].children[0].textContent));
checar("linhas em ordem crescente de preco", precos.length > 0 && precos.every((v, i) => i === 0 || precos[i - 1] <= v), precos);
checar("precos da tela batem com a API", JSON.stringify(precos) === JSON.stringify(payloads["/api/ofertas"].ofertas.map((o) => o.preco)), precos);
checar("rota aparece nas linhas", linhasOfertas[0].children[1].textContent === "FLNRIO", linhasOfertas[0].children[1].textContent);
checar("data de ida em pt-BR", /^\d{2}\/\d{2}\/\d{4}$/.test(linhasOfertas[0].children[2].textContent), linhasOfertas[0].children[2].textContent);

console.log("\n== links (dado de scraping) ==");
const anchors = achar(registro["alertas"], (n) => n.tagName === "a");
const hrefs = anchors.map((a) => a.getAttribute("href"));
checar("link http vira ancora", hrefs.some((h) => h && h.startsWith("https://exemplo.test/")), hrefs);
checar("javascript: nao vira ancora", !hrefs.some((h) => h && h.startsWith("javascript:")), hrefs);
checar("javascript: virou 'sem link'", textos(achar(registro["alertas"], (n) => n.tagName === "span" && n.textContent === "sem link")).length === 1);
checar("ancoras abrem em nova aba", anchors.every((a) => a.getAttribute("target") === "_blank" && a.getAttribute("rel") === "noopener noreferrer"));

console.log("\n== grafico ==");
const svg = achar(registro["grafico"], (n) => n.tagName === "svg")[0];
checar("svg criado", !!svg);
checar("paths do grafico (area + linha)", achar(registro["grafico"], (n) => n.tagName === "path").length === 2, achar(registro["grafico"], (n) => n.tagName === "path").length);
checar("um ponto por dia", achar(registro["grafico"], (n) => n.tagName === "circle").length === payloads["/api/historico"].historico.length, achar(registro["grafico"], (n) => n.tagName === "circle").length);
checar("tooltip nos pontos", achar(registro["grafico"], (n) => n.tagName === "title").length === payloads["/api/historico"].historico.length);
checar("rotulos de preco no eixo", achar(registro["grafico"], (n) => n.tagName === "text").length >= 7, achar(registro["grafico"], (n) => n.tagName === "text").length);

console.log("\n== aviso de erro ==");
checar("sem aviso de erro quando tudo carrega", registro["aviso"].hidden === true || registro["aviso"].textContent === "", registro["aviso"].textContent);

console.log("\n== interacoes de rotas e ciclo ==");
// Validacao ao tentar adicionar rota com campos vazios
registro["r-origem"].value = "";
await janela.adicionarRota();
checar("adicionar rota vazia exibe erro", registro["aviso-rotas"].className.includes("erro"), registro["aviso-rotas"].textContent);

// Adicionar rota com campos preenchidos
registro["r-origem"].value = "BSB";
registro["r-destino"].value = "SDU";
registro["r-ida-de"].value = "2026-11-01";
registro["r-preco"].value = "500";
await janela.adicionarRota();
checar("adicionar rota valida exibe sucesso", registro["aviso-rotas"].className.includes("ok"), registro["aviso-rotas"].textContent);
checar("campos do formulario limpos apos cadastro", registro["r-origem"].value === "" && registro["r-destino"].value === "");

// Cancelar remocao no confirm
janela.confirm = () => false;
const chamadasAntes = chamadas.length;
await janela.removerRota(0);
checar("remover rota cancelado pelo usuario nao chama api", chamadas.length === chamadasAntes);

// Confirmar remocao
janela.confirm = () => true;
await janela.removerRota(0);
checar("remover rota confirmada exibe sucesso", registro["aviso-rotas"].className.includes("ok"), registro["aviso-rotas"].textContent);

// Disparar ciclo
await janela.dispararCiclo();
checar("disparar ciclo altera status", registro["status-ciclo"].className.includes("running") || registro["status-ciclo"].className.includes("success"));

console.log("\n== catalogo e validacao de aeroportos ==");
checar("datalist de aeroportos populada", registro["lista-aeroportos"].children.length > 0, registro["lista-aeroportos"].children.length);

// Feedback em tempo real para aeroporto valido
registro["r-origem"].value = "FLN";
await janela.atualizarSeloAeroporto("r-origem", "selo-origem");
checar("selo com FLN fica valido", registro["selo-origem"].className.includes("valido") && registro["selo-origem"].textContent.includes("Florianópolis"), registro["selo-origem"].textContent);

// Feedback em tempo real para metropolitano
registro["r-origem"].value = "RIO";
await janela.atualizarSeloAeroporto("r-origem", "selo-origem");
checar("selo com RIO fica metropolitano", registro["selo-origem"].className.includes("metropolitano") && registro["selo-origem"].textContent.includes("Metropolitano"), registro["selo-origem"].textContent);

// Feedback para aeroporto invalido / inexistente
registro["r-origem"].value = "ZZZ";
await janela.atualizarSeloAeroporto("r-origem", "selo-origem");
checar("selo com ZZZ fica invalido", registro["selo-origem"].className.includes("invalido"), registro["selo-origem"].textContent);

// Validacao na criacao de rota rejeita aeroporto inexistente
registro["r-origem"].value = "ZZZ";
registro["r-destino"].value = "SDU";
registro["r-ida-de"].value = "2026-11-01";
registro["r-preco"].value = "500";
await janela.adicionarRota();
checar("adicionar rota com origem desconhecida bloqueia", registro["aviso-rotas"].className.includes("erro") && registro["aviso-rotas"].textContent.includes("não reconhecida"), registro["aviso-rotas"].textContent);

console.log("\n== diagnostico de ciclo ==");
janela.renderDiagnostico({
  detalhes_fontes: {
    google_flights: { status: "ok", ofertas: 12, mensagem: "12 ofertas encontradas" },
    skiplagged: { status: "aviso", mensagem: "sem voos para as datas" }
  }
});
const cardsDiag = achar(registro["diagnostico-ciclo"], (n) => n.className.includes("bvx-fonte"));
checar("cards de diagnostico renderizados", cardsDiag.length === 2, cardsDiag.length);
checar("estado ok no card", cardsDiag[0].className.includes("bv-status--success"));
checar("estado aviso no card", cardsDiag[1].className.includes("bvx-aviso"));
checar("dica de rotas exibida quando ha aviso", achar(registro["diagnostico-ciclo"], (n) => n.className.includes("dica-rotas")).length === 1);

console.log("\n== agendador cron ==");
checar("funcoes de cron expostas em window", typeof janela.carregarCronStatus === "function" && typeof janela.salvarCronConfig === "function" && typeof janela.atualizarContagemCron === "function");
checar("cron inicia desativado", registro["cron-ativo"].checked === false);
checar("badge de cron inicia pausado", registro["cron-contagem"].textContent.includes("Agendador pausado"));
checar("badge pausado nao e verde", !registro["cron-contagem"].className.includes("success"));

// Ativar cron
registro["cron-ativo"].checked = true;
registro["cron-horas"].value = "2";
await janela.salvarCronConfig();
checar("salvar cron ativa badge", registro["cron-contagem"].className.includes("success"));
checar("badge exibe contagem regressiva", registro["cron-contagem"].textContent.includes("Próxima busca em"));

// Desativar cron
registro["cron-ativo"].checked = false;
await janela.salvarCronConfig();
checar("desativar cron volta a pausado", registro["cron-contagem"].textContent.includes("Agendador pausado"));

console.log("\n== progresso do ciclo em tempo real ==");
const contagemOfertasAntes = chamadas.filter((u) => u.includes("/api/ofertas")).length;

payloads["/api/ciclo/status"] = {
  rodando: true,
  ultimo_ciclo: 6,
  iniciado_em: new Date(Date.now() - 5000).toISOString(),
  ofertas_encontradas: 4,
  consultas_feitas: 2,
  fonte_atual: "google_flights",
  mensagem: "Consultando google_flights (4 ofertas encontradas até agora)...",
  diagnostico: null
};
await janela.verificarCicloStatus();
checar("status fica rodando", registro["status-ciclo"].className.includes("running"));
checar("mensagem de progresso exibida", registro["status-ciclo"].textContent.includes("google_flights") && registro["status-ciclo"].textContent.includes("4 ofertas"));
const contagemCom4 = chamadas.filter((u) => u.includes("/api/ofertas")).length;
checar("ofertas encontradas dispara atualizar() live", contagemCom4 > contagemOfertasAntes, { contagemOfertasAntes, contagemCom4 });

// Incrementa ofertas encontradas progressivamente durante o ciclo
payloads["/api/ciclo/status"] = {
  rodando: true,
  ultimo_ciclo: 6,
  iniciado_em: new Date(Date.now() - 8000).toISOString(),
  ofertas_encontradas: 8,
  consultas_feitas: 3,
  fonte_atual: "skiplagged",
  mensagem: "Consultando skiplagged (8 ofertas encontradas até agora)...",
  diagnostico: null
};
await janela.verificarCicloStatus();
const contagemCom8 = chamadas.filter((u) => u.includes("/api/ofertas")).length;
checar("nova rodada com mais ofertas dispara atualizar() novamente", contagemCom8 > contagemCom4, { contagemCom4, contagemCom8 });

// Finalizacao do ciclo
payloads["/api/ciclo/status"] = {
  rodando: false,
  ultimo_ciclo: 7,
  erro: null,
  mensagem: "Ciclo finalizado com sucesso",
  ofertas_encontradas: 9,
  consultas_feitas: 3,
  fonte_atual: null,
  diagnostico: null
};
await janela.verificarCicloStatus();
checar("ciclo concluido exibe sucesso", registro["status-ciclo"].className.includes("success") && registro["status-ciclo"].textContent.includes("#7"));

console.log("\n== navegacao por abas (SPA) ==");
checar("funcao alternarAba exposta", typeof janela.alternarAba === "function");
checar("aba monitoramento inicia ativa", registro["tab-painel"].className.includes("is-active"));
checar("aba gestao inicia inativa", !registro["tab-gestao"].className.includes("is-active"));
checar("view-gestao inicia oculta", registro["view-gestao"].style.display === "none");

// Alternar para gestao
janela.alternarAba("gestao");
checar("tab-gestao fica ativa", registro["tab-gestao"].className.includes("is-active"));
checar("tab-painel fica inativa", !registro["tab-painel"].className.includes("is-active"));
checar("view-painel fica oculto", registro["view-painel"].style.display === "none");
checar("view-gestao fica visivel", registro["view-gestao"].style.display === "block");

// Alternar de volta para painel
janela.alternarAba("painel");
checar("view-painel volta a visivel", registro["view-painel"].style.display === "block");
checar("view-gestao volta a oculta", registro["view-gestao"].style.display === "none");

console.log("\n== aba de gestao: configuracoes e seguranca ==");
checar("funcoes de gestao expostas", typeof janela.carregarConfiguracoesGestao === "function" && typeof janela.salvarConfiguracoesGestao === "function" && typeof janela.testarEmail === "function");
checar("versao carregada no header", registro["painel-versao"].textContent.includes("1.2.0"), registro["painel-versao"].textContent);
checar("email host preenchido", !!registro["cfg-email-host"].value);
checar("fontes checkboxes populados", registro["cfg-fonte-google-flights"].checked === true);
checar("badge de senha exibe status inicial", registro["badge-senha-status"].textContent.includes("Nenhuma senha salva") || registro["badge-senha-status"].textContent.includes("AES"), registro["badge-senha-status"].textContent);
janela.atualizarBadgeSenha(true);
checar("badge de senha exibe protecao AES quando tem_senha", registro["badge-senha-status"].textContent.includes("AES") && registro["badge-senha-status"].className.includes("success"), registro["badge-senha-status"].textContent);

// Alternar ajuda
janela.alternarAjudaEmail();
checar("painel de ajuda aberto", registro["painel-ajuda-email"].style.display === "block");
janela.alternarAjudaEmail(false);
checar("painel de ajuda fechado", registro["painel-ajuda-email"].style.display === "none");

// Presets de email
registro["preset-email"].value = "outlook";
janela.aplicarPresetEmail();
checar("preset outlook preenche host", registro["cfg-email-host"].value === "smtp.office365.com", registro["cfg-email-host"].value);
checar("preset outlook preenche porta", String(registro["cfg-email-porta"].value) === "587", registro["cfg-email-porta"].value);

// Testar email
await janela.testarEmail();
checar("testar email exibe feedback", registro["aviso-gestao"].className.includes("ok"), registro["aviso-gestao"].textContent);

// Salvar configuracoes
registro["cfg-email-de"].value = "teste@exemplo.com";
await janela.salvarConfiguracoesGestao();
checar("salvar configuracoes exibe sucesso", registro["aviso-gestao"].className.includes("ok") && registro["aviso-gestao"].textContent.includes("sucesso"), registro["aviso-gestao"].textContent);

console.log("\n" + "=".repeat(60));
if (falhas.length) {
  console.log(`${falhas.length} FALHA(S): ` + falhas.join("; "));
  process.exit(1);
}
console.log("JS DO PAINEL: TODOS OS TESTES PASSARAM");
process.exit(0);
