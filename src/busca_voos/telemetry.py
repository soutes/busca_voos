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


import atexit

_TRACER_PROVIDER: Any = None
_METER_PROVIDER: Any = None
_LOGGER_PROVIDER: Any = None


def encerrar_telemetria() -> None:
    """Descarrega buffers pendentes de traces, metricas e logs."""
    global _TRACER_PROVIDER, _METER_PROVIDER, _LOGGER_PROVIDER
    if _TRACER_PROVIDER:
        try:
            _TRACER_PROVIDER.shutdown()
        except Exception:
            pass
    if _METER_PROVIDER:
        try:
            _METER_PROVIDER.shutdown()
        except Exception:
            pass
    if _LOGGER_PROVIDER:
        try:
            _LOGGER_PROVIDER.shutdown()
        except Exception:
            pass


atexit.register(encerrar_telemetria)


def _atualizar_instrumentos() -> None:
    global _meter, contador_buscas, contador_ofertas, contador_erros_scraper, histograma_duracao
    if not OTEL_DISPONIVEL:
        return
    _meter = metrics.get_meter("busca_voos")
    contador_buscas = _meter.create_counter(
        name="busca_voos_buscas_total",
        description="Total de buscas de voos realizadas",
        unit="1",
    )
    contador_ofertas = _meter.create_counter(
        name="busca_voos_ofertas_total",
        description="Total de ofertas de passagens encontradas",
        unit="1",
    )
    contador_erros_scraper = _meter.create_counter(
        name="busca_voos_erros_total",
        description="Total de erros encontrados nos scrapers por fonte e tipo",
        unit="1",
    )
    histograma_duracao = _meter.create_histogram(
        name="busca_voos_duracao_segundos",
        description="Duracao da execucao de busca em cada fonte",
        unit="s",
    )


def configurar_telemetria(service_name: str = "busca-voos") -> None:
    """Configura TracerProvider, MeterProvider e LoggerProvider com OTLP."""
    global _INICIALIZADO, _TRACER_PROVIDER, _METER_PROVIDER, _LOGGER_PROVIDER
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
        if os.getenv("OTEL_CONSOLE_LOGS") == "1":
            tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(tracer_provider)
    _TRACER_PROVIDER = tracer_provider

    # Setup Metrics
    if endpoint:
        try:
            metric_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
            reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=2000)
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(meter_provider)
            _METER_PROVIDER = meter_provider
            _atualizar_instrumentos()
            log.info("OTel: exportando metricas para %s", endpoint)
        except Exception as e:
            log.warning("Falha ao configurar OTLPMetricExporter: %s", e)

    # Setup Structured Logs via OTLP to Loki
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
            from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
            from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

            logger_provider = LoggerProvider(resource=resource)
            log_exporter = OTLPLogExporter(endpoint=endpoint, insecure=True)
            logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
            handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
            logging.getLogger().addHandler(handler)
            _LOGGER_PROVIDER = logger_provider
            log.info("OTel: exportando logs via OTLP para %s", endpoint)
        except Exception as e:
            log.debug("OTLPLogExporter indisponivel: %s", e)

    _INICIALIZADO = True


from contextlib import nullcontext


def rastrear_span(nome: str, atributos: dict[str, Any] | None = None):
    """Context manager para rastreabilidade de Spans OpenTelemetry."""
    tracer = obter_tracer()
    if tracer:
        return tracer.start_as_current_span(nome, attributes=atributos or {})
    return nullcontext()


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
