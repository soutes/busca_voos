# AGENTS.md — Regras de Desenvolvimento e Operação do Busca Voos

`busca_voos` é um monitor de passagens aéreas com observabilidade OpenTelemetry, alertas acionáveis e auto-cura de seletores por IA.

## Documentos de Referência
- `README.md` — Visão geral e instruções de execução
- `docs/operations-and-security-report.md` — Relatório de DevOps, Observabilidade e Resposta a Incidentes (Módulo 4)

## Comandos Principais
- `pytest -v tests/` — Executa toda a suíte de testes unitários e de integração
- `docker compose -f observability/compose.yaml up -d` — Sobe a stack de telemetria (OTel Collector, Prometheus, Loki, Tempo, Grafana)
- `docker compose up -d --build` — Sobe a aplicação web e o incident responder
- `python incident-response/server.py` — Inicia o webhook de incidentes na porta 8001

## Regras de Arquitetura e Camadas
- `src/busca_voos/sources/`: Módulos de extração de dados. Não devem importar FastAPI ou Uvicorn.
- `src/busca_voos/web.py`: Superfície de entrega web somente-leitura. Keep it thin.
- `src/busca_voos/telemetry.py`: Camada de instrumentação OpenTelemetry. Não deve quebrar a execução se o collector estiver offline.
- `incident-response/`: Serviço independente rodando na porta 8001. Apenas reage a alertas autorizados e opera em sandbox delimitado.

## Governança e Segurança
- O modelo de IA pode raciocinar e propor correções; o sistema deve observar, autorizar, verificar e lembrar.
- Toda auto-remediação requer validação obrigatória pela suíte de testes (`pytest`).
- Nenhuma credencial (SMTP, tokens) deve ser gravada em código ou trafegar em logs claros.
