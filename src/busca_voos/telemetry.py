"""Modulo de Observabilidade e Telemetria (OpenTelemetry) para busca_voos.

Fornece traces distribuidos, metricas de negocio e logs estruturados em JSON
com injecao automatica de trace_id e span_id.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

log = logging.getLogger("busca_voos.telemetry")

# ----------------- OpenTelemetry SDK & Traces -----------------
try:
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    OTEL_DISPONIVEL = True
except ImportError:
    OTEL_DISPONIVEL = False

_INICIALIZADO = False


class JsonFormatter(logging.Formatter):
    """Formatador de log estruturado em JSON com correlacao de trace_id."""

    def format(self, record: logging.LogRecord) -> str:
        dados: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service.name": os.getenv("OTEL_SERVICE_NAME", "busca-voos"),
        }
        if OTEL_DISPONIVEL:
            span = trace.get_current_span()
            if span and span.get_span_context().is_valid:
                ctx = span.get_span_context()
                dados["trace_id"] = f"{ctx.trace_id:032x}"
                dados["span_id"] = f"{ctx.span_id:016x}"

        if record.exc_info:
            dados["exception"] = self.formatException(record.exc_info)
        return json.dumps(dados, ensure_ascii=False)


def configurar_telemetria(service_name: str = "busca-voos") -> None:
    """Configura TracerProvider e MeterProvider com OTLP ou Console."""
    global _INICIALIZADO
    if _INICIALIZADO or not OTEL_DISPONIVEL:
        return

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    resource = Resource.create({"service.name": service_name, "service.version": "0.1.0"})

    # Setup Tracing
    tracer_provider = TracerProvider(resource=resource)
    if endpoint:
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            log.info("OTel: exportando traces para %s", endpoint)
        except Exception as e:
            log.warning("Falha ao configurar OTLPSpanExporter: %s", e)
    else:
        # Se nao houver endpoint, pode usar Console exporter se OTEL_CONSOLE_LOGS=1
        if os.getenv("OTEL_CONSOLE_LOGS") == "1":
            tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(tracer_provider)

    # Setup Metrics
    if endpoint:
        try:
            metric_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
            reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=5000)
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(meter_provider)
            log.info("OTel: exportando metricas para %s", endpoint)
        except Exception as e:
            log.warning("Falha ao configurar OTLPMetricExporter: %s", e)

    _INICIALIZADO = True


def obter_tracer():
    return trace.get_tracer("busca_voos") if OTEL_DISPONIVEL else None


def obter_meter():
    return metrics.get_meter("busca_voos") if OTEL_DISPONIVEL else None


# Contadores e Metricas do Negocio
_meter = metrics.get_meter("busca_voos") if OTEL_DISPONIVEL else None

contador_buscas = (
    _meter.create_counter(
        name="busca_voos_buscas_total",
        description="Total de buscas de voos realizadas",
        unit="1",
    )
    if _meter
    else None
)

contador_ofertas = (
    _meter.create_counter(
        name="busca_voos_ofertas_total",
        description="Total de ofertas de passagens encontradas",
        unit="1",
    )
    if _meter
    else None
)

contador_erros_scraper = (
    _meter.create_counter(
        name="busca_voos_erros_total",
        description="Total de erros encontrados nos scrapers por fonte e tipo",
        unit="1",
    )
    if _meter
    else None
)

histograma_duracao = (
    _meter.create_histogram(
        name="busca_voos_duracao_segundos",
        description="Duracao da execucao de busca em cada fonte",
        unit="s",
    )
    if _meter
    else None
)


def registrar_busca(origem: str, destino: str, sucesso: bool = True) -> None:
    if contador_buscas:
        contador_buscas.add(1, {"origem": origem, "destino": destino, "sucesso": str(sucesso)})


def registrar_ofertas(fonte: str, quantidade: int) -> None:
    if contador_ofertas and quantidade > 0:
        contador_ofertas.add(quantidade, {"fonte": fonte})


def registrar_erro(fonte: str, tipo_erro: str) -> None:
    if contador_erros_scraper:
        contador_erros_scraper.add(1, {"fonte": fonte, "tipo": tipo_erro})


def medir_tempo(fonte: str):
    """Context manager para medir duracao da coleta e registrar na metrica."""
    class _Timer:
        def __enter__(self):
            self.inicio = time.time()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duracao = time.time() - self.inicio
            if histograma_duracao:
                histograma_duracao.record(duracao, {"fonte": fonte})

    return _Timer()
