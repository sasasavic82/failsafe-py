# telemetry.py
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import set_meter_provider

from integrations.opentelemetry import FailsafeOtelInstrumentor

def setup_otel(service_name: str = "api") -> MeterProvider:
    resource = Resource.create({"service.name": service_name})
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint="http://localhost:4318/v1/metrics", timeout=5)
    )
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    set_meter_provider(provider)

    FailsafeOtelInstrumentor().instrument(
        namespace="failsafe.service",
        meter_provider=provider,
    )
    return provider
