"""Safe event projection is independent of the optional OTLP collector.

Prompt/tool-result bodies live in protected checkpoints, never in telemetry.
Only selected execution metadata is exported and streamed to the UI.
"""
import logging
import os
import threading
from contextlib import contextmanager

PROGRESS = {
    "session.started": ("understanding", "正在理解你的需求…"),
    "tool.started": ("working", "正在调用工具处理任务…"),
    "mcp.started": ("working", "正在调用工具处理任务…"),
    "approval.requested": ("approval", "需要你的确认后才能继续"),
    "user.input_required": ("clarifying", "需要你补充一项关键信息"),
    "session.waiting": ("waiting", "正在等待外部处理…"),
    "session.failed": ("failed", "任务未能完成"),
}
VISIBLE_EVENT_KINDS = {"user.progress"}


class Telemetry:
    def __init__(self, store):
        self.store = store
        self.provider = self.meter_provider = self.logger_provider = None
        self.logger = logging.getLogger("agent.audit")
        self.tracer = self.counter = self.otel_logger = None
        self._progress = {}
        self._progress_lock = threading.Lock()
        try:
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.metrics import MeterProvider
            resource = Resource.create({"service.name": "agent"})
            self.provider = TracerProvider(resource=resource)
            readers = []
            endpoint = os.getenv("AGENT_OTLP_ENDPOINT", "").rstrip("/")
            if endpoint:
                from opentelemetry.sdk.trace.export import BatchSpanProcessor
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
                from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
                from opentelemetry.sdk._logs import LoggerProvider
                from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
                from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
                self.provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint + "/v1/traces")))
                readers.append(PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint + "/v1/metrics")))
                self.logger_provider = LoggerProvider(resource=resource)
                self.logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint + "/v1/logs")))
                self.otel_logger = self.logger_provider.get_logger("agent")
            self.meter_provider = MeterProvider(resource=resource, metric_readers=readers)
            self.counter = self.meter_provider.get_meter("agent").create_counter("agent.events")
            self.tracer = self.provider.get_tracer("agent")
        except ImportError:
            self.logger.warning("OpenTelemetry SDK unavailable; durable UI events remain enabled")

    @contextmanager
    def span(self, name, sid):
        if self.tracer:
            with self.tracer.start_as_current_span(name, attributes={"session.id": sid},
                    record_exception=False, set_status_on_exception=False) as span:
                try:
                    yield
                except Exception:
                    from opentelemetry.trace import Status, StatusCode
                    span.set_status(Status(StatusCode.ERROR, "Operation failed"))
                    raise
        else:
            yield

    def emit(self, sid, kind, **metadata):
        if kind == "prompt.received":
            with self._progress_lock:
                self._progress.pop(sid, None)
        internal = {key: str(metadata[key])[:256] for key in (
            "tool", "call_id", "count", "step", "chars", "error_type"
        ) if key in metadata}
        self.store.developer_event(sid, kind, internal)
        event = None
        progress = PROGRESS.get(kind)
        if progress:
            stage, message = progress
            with self._progress_lock:
                if self._progress.get(sid) != stage:
                    self._progress[sid] = stage
                    event = self.store.event(sid, "user.progress", {"stage": stage, "message": message})

        # Selected metadata remains internal to OpenTelemetry and is never
        # returned by the user-facing SSE endpoint.
        try:
            with self.span(kind, sid):
                if self.tracer:
                    from opentelemetry import trace
                    trace.get_current_span().add_event(kind, internal)
                if self.counter:
                    self.counter.add(1, {"event.kind": kind})
                if self.otel_logger:
                    from opentelemetry._logs import LogRecord, SeverityNumber
                    self.otel_logger.emit(LogRecord(body=kind, severity_number=SeverityNumber.INFO,
                                                   attributes={"session.id": sid, **internal}))
        except Exception:
            # Collector failure must never change task execution or approvals.
            self.logger.warning("Telemetry export failed for %s", kind)
        return event

    def close(self):
        for provider in (self.provider, self.meter_provider, self.logger_provider):
            if provider:
                provider.shutdown()
