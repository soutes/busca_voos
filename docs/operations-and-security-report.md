# Relatório de Operações, Observabilidade e Segurança (Módulo 4)

**Aplicação:** Busca Voos — Monitoramento e Auto-Cura de Scrapers com OpenTelemetry e Agentes de IA  
**Repositório:** [https://github.com/soutes/busca_voos](https://github.com/soutes/busca_voos)  
**Data:** 03 de Outubro de 2026  
**Autor:** Luiz Soutes  

---

## 1. Visão Geral da Arquitetura

O **Busca Voos** é um sistema distribuído de inteligência e monitoramento de passagens aéreas que extrai preços em tempo real de múltiplos agregadores (Google Flights, Skiplagged, Skyscanner e Trip.com), armazena o histórico em banco de dados e disponibiliza um painel web analítico para o usuário.

Com a evolução para a arquitetura nativa de IA e observabilidade do **Módulo 4**, o sistema agora opera em um ciclo fechado de confiabilidade:

```text
[Scrapers / Engine] ──(OTLP)──► [OTel Collector]
                                     │
           ┌─────────────────────────┼─────────────────────────┐
           ▼                         ▼                         ▼
     [Prometheus]                 [Loki]                    [Tempo]
     (Métricas)                   (Logs)                    (Traces)
           │                         │                         │
           └─────────────────────────┼─────────────────────────┘
                                     ▼
                            [Grafana Dashboard]
                                     │ (Alerta de impacto: 0 ofertas / erro de layout)
                                     ▼
                        [Incident Responder :8001]
                                     │
                                     ▼
                         [Agente On-Call Headless]
                       (Diagnóstico & Auto-Remediação)
```

---

## 2. Telemetria e Sinais Implementados

O sistema foi instrumentado com o SDK oficial do **OpenTelemetry** sem acoplamento a provedores proprietários:

### Métricas de Negócio e Operação (Prometheus)
* `busca_voos_buscas_total`: Contador de execuções com labels `{origem, destino, sucesso}`.
* `busca_voos_ofertas_total`: Volume de passagens extraídas com label `{fonte}`.
* `busca_voos_erros_total`: Taxa de erro com labels `{fonte, tipo}` (ex: `zero_ofertas_layout`, `rede`, `captcha`).
* `busca_voos_duracao_segundos`: Histograma de latência por provedor.
* `http_server_requests_total`: Métricas padrão da API web (status 2xx, 4xx e 5xx).

### Logs Estruturados em JSON (Loki)
Todos os logs do sistema emitem formato JSON com injeção automática de `trace_id` e `span_id`. Quando ocorre uma falha em uma rota, o log contém a correlação direta com a requisição e a fonte.

### Traces Distribuídos (Tempo)
Cada busca de voo é envelopada em um Span raiz `google_flights.buscar`, medindo o tempo exato de requisição HTTP, tempo de parsing no BeautifulSoup e tempo de gravação no banco.

---

## 3. Alertas com Foco no Impacto Real

Em vez de monitorar uso genérico de CPU ou disco, o alerta foi desenhado com base no impacto de negócio:
* **Regra:** `ScraperZeroOffersOrError`
* **Condição:** Dispara quando uma fonte externa termina a coleta com **0 ofertas** ou taxa de erro superior a 0 por mais de 1 minuto em rota configurada.
* **Anotações:** O alerta envia no payload a fonte afetada (`google_flights`), a severidade, o link do dashboard no Grafana e a rota. Períodos sem coletas são mantidos no estado **Normal** para evitar alertas falsos de "No Data".

---

## 4. O Incidente e a Resposta Automatizada (Auto-Cura)

### O Problema Comum de Web Scraping
Fornecedores como Google Flights atualizam o DOM frequentemente. Quando a classe CSS muda (ex: de `li.pIav2d` para um layout diferente), o código não lança exceção fatal, mas retorna `0 ofertas`, quebrando o serviço silenciosamente.

### O Fluxo de Auto-Cura
1. O Grafana detecta a anomalia através da métrica `busca_voos_erros_total{tipo="zero_ofertas_layout"}` e dispara um webhook para `POST http://localhost:8001/alerts`.
2. O **Incident Responder** intercepta o alerta e gera um pacote delimitado de evidências (`collect_evidence.py`):
   - Os últimos 5 minutos de logs de erro no Loki.
   - O trace correspondente no Tempo.
   - O código-fonte atual do parser `src/busca_voos/sources/google_flights.py`.
   - O status do Git.
3. O **Agente de IA On-Call** é executado em modo headless e isolado.
4. O agente analisa o HTML da página, identifica a nova classe CSS no container de voos, aplica o patch de fallback no seletor e executa a suíte de testes (`pytest tests/test_parsers.py`).
5. Os testes passam com sucesso (`2 passed`), e o agente encerra a investigação registrando a causa raiz e o diff auditável em `incident-response/incidents/<id>/agent-answer.txt`.

---

## 5. Políticas de Segurança e Governança

Seguindo o princípio central ensinado no curso:  
> *"O modelo pode raciocinar; o sistema deve observar, autorizar, verificar e lembrar."*

* **Menor Privilégio:** O agente on-call não possui credenciais de nuvem, senhas de banco nem permissão para realizar `git push` direto na branch principal de produção sem validação por testes.
* **Sanitização de Evidências:** Dados sensíveis (como tokens de autenticação ou credenciais de e-mail SMTP) são filtrados antes da geração do pacote de evidências enviado ao agente.
* **Deduplicação de Alertas:** Notificações repetidas do mesmo alerta durante a investigação são agrupadas para evitar loops e consumo desnecessário de tokens.
* **Testes como Porta de Qualidade:** Nenhuma auto-remediação é considerada válida se a suíte de testes automatizados (`pytest`) falhar.

---

## 6. Conclusão

A adaptação do projeto **Busca Voos** demonstra na prática a aplicação dos padrões mais modernos de engenharia de software nativa de IA: observabilidade de ponta a ponta, redução drástica do tempo médio de reparo (MTTR) e proteção de produção com guardrails rigorosos.
