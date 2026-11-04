"""Local, bounded, redacted trace export. No prompts or credential payloads."""

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

ALLOWED_ATTRIBUTES = {
    "http.request.method",
    "http.route",
    "http.response.status_code",
    "http.method",
    "http.status_code",
    "model.provider",
    "model.task",
    "commerce.execution_id",
}
_configured = False


class LocalExporter(SpanExporter):
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        path.touch(mode=0o600, exist_ok=True)
        path.chmod(0o600)
        self.handler = RotatingFileHandler(path, maxBytes=10 * 1024 * 1024, backupCount=2)
        self.handler.setFormatter(logging.Formatter("%(message)s"))

    def export(self, spans):
        for span in spans:
            value = {
                "name": span.name[:160],
                "trace_id": f"{span.context.trace_id:032x}",
                "span_id": f"{span.context.span_id:016x}",
                "start_ns": span.start_time,
                "end_ns": span.end_time,
                "status": span.status.status_code.name,
                "attributes": {
                    k: str(v)[:160]
                    for k, v in (span.attributes or {}).items()
                    if k in ALLOWED_ATTRIBUTES
                },
            }
            self.handler.emit(
                logging.LogRecord(
                    "commerce.trace", logging.INFO, "", 0, json.dumps(value), (), None
                )
            )
        return SpanExportResult.SUCCESS

    def shutdown(self):
        self.handler.close()


def configure_tracing(enabled: bool = True):
    global _configured
    if not enabled or _configured:
        return
    provider = TracerProvider(
        resource=Resource.create({"service.name": "agentic-commerce", "service.version": "0.1.0"})
    )
    provider.add_span_processor(SimpleSpanProcessor(LocalExporter(Path(".local/traces.jsonl"))))
    trace.set_tracer_provider(provider)
    _configured = True
