"""Safe event projection is independent of the optional OTLP collector.

Prompt/tool-result bodies live in protected checkpoints, never in telemetry.
Only selected execution metadata is exported and streamed to the UI.
"""
import logging
import os
from contextlib import contextmanager

LABELS = {
    "session.created": "正在准备回答…",
    "session.started": "正在理解你的问题…",
    "prompt.received": "正在理解你的问题…",
    "model.started": "正在整理结果…",
    "model.completed": "正在整理结果…",
    "context.compacted": "正在整理对话上下文…",
    "tool.started": "正在查询和处理相关数据…",
    "tool.completed": "正在整理查询结果…",
    "tool.failed": "数据处理未完成，正在调整…",
    "approval.requested": "需要你的确认后才能继续",
    "approval.approved": "已确认，正在继续处理…",
    "approval.denied": "已取消该操作，正在整理回答…",
    "network.allowed": "连接检查已通过",
    "network.denied": "连接未通过安全检查",
    "mcp.started": "正在读取任务所需的外部资源…",
    "mcp.completed": "外部资源读取完成，正在整理…",
    "session.completed": "回答已生成",
    "session.failed": "任务未能完成",
    "session.interrupted": "任务已中断",
    "session.resumed": "正在恢复任务…",
    "user.input_required": "需要你补充一项关键信息",
    "session.waiting": "正在等待外部处理",
    "action.selected": "正在执行下一步…",
}

# Only these coarse stages are exposed by the App Server event stream.
VISIBLE_EVENT_KINDS = {
    "session.started",
    "prompt.received",
    "model.started",
    "tool.started",
    "tool.completed",
    "tool.failed",
    "approval.requested",
    "approval.approved",
    "approval.denied",
    "mcp.started",
    "mcp.completed",
    "session.completed",
    "session.failed",
    "session.interrupted",
    "session.resumed",
    "user.input_required",
    "session.waiting",
}


class Telemetry:
    def __init__(self, store):
        self.store = store
        self.provider = self.meter_provider = self.logger_provider = None
        self.logger = logging.getLogger("agent.audit")
        self.tracer = self.counter = self.otel_logger = None
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
        # The durable public projection never contains tool names, arguments,
        # call IDs, prompt sizes, exception types, or arbitrary text.
        public = {"message": LABELS.get(kind, "任务状态已更新")}
        event = self.store.event(sid, kind, public)

        # Selected metadata remains internal to OpenTelemetry and is never
        # returned by the user-facing SSE endpoint.
        internal = dict(public)
        for key in ("tool", "call_id", "count", "step", "chars", "error_type"):
            if key in metadata:
                internal[key] = str(metadata[key])[:128]
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
