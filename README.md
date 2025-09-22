<p align="center">
  <img src="docs/failsafe-logo.png" alt="Failsafe" style="max-width:350px;width:100%;height:auto;">
</p>

<p align="center">
    <em>Fault tolerance for resiliency and stability in modern Python applications</em>
</p>

---

Failsafe is a collection of resiliency patterns for microservice-based systems, implemented in idiomatic, async-only Python. It aims to provide a Python analogue to <a href="https://github.com/failsafe-lib/failsafe">Failsafe (Java)</a> while integrating first-class OpenTelemetry metrics for operational visibility.

## Key Features

* AsyncIO-native implementations of core resiliency patterns
* Clean decorator and async context-manager APIs
* OpenTelemetry metric listeners for every pattern
* Lightweight, readable, testable

## Requirements

* Python 3.12+

## Installation

Failsafe is currently available internally.

```bash
uv sync
```


## Resiliency Patterns

| Pattern         | Problem                                               | Solution                                                              | Implemented |
| --------------- | ----------------------------------------------------- | --------------------------------------------------------------------- | ----------- |
| Retry           | Transient failures that self-recover                  | Automatically retry operations on temporary errors                    | Yes         |
| Cache           | Recomputing or refetching identical data is wasteful  | Store and reuse results of expensive operations                       | Yes         |
| Hedge           | Slow or unpredictable responses increase tail latency | Run hedged requests in parallel; return the first success             | Yes         |
| Fail Fast       | Known failure state makes further attempts wasteful   | Immediately fail after threshold; remain open until recovery          | Yes         |
| Feature Toggle  | Need feature on/off without redeploy                  | Dynamically enable or disable code paths at runtime                   | Yes         |
| Circuit Breaker | Overloaded or failing downstream worsens under load   | Trip the breaker on failure thresholds; recover via half-open probing | Yes         |
| Timeout         | Operations can hang or exceed acceptable latency      | Bound execution time with deterministic timeouts                      | Yes         |
| Bulkhead        | Unbounded concurrency can starve the system           | Limit concurrent executions; queue or reject overflow                 | Yes         |
| Rate Limiter    | Uncontrolled request rate can overload services       | Enforce a maximum request rate                                        | Yes         |
| Fallback        | Dependencies can be down or degraded                  | Degrade gracefully with defaults or alternative code paths            | Yes         |

## Usage Patterns

* **Decorator**: apply to async callables to guard a single operation.
* **Async context manager**: guard a critical section (`async with pattern(...): ...`).
* All patterns are async-only. Do not wrap sync callables.

## OpenTelemetry Integration

### What you get

Each pattern registers an OpenTelemetry **MetricListener** that emits counters under a consistent naming scheme:

```
{namespace}.{component_name}.{pattern}.{metric}
```

* `namespace`: e.g., `failsafe.service` (configurable in the instrumentor)
* `component_name`: the `name=` you pass to the pattern factory (required for stable, low-cardinality metric keys)
* `pattern`: one of `retry`, `failfast`, `featuretoggle`, `hedge`, `timeout`, `bulkhead`, `cache`, `circuitbreaker`, `fallback`
* `metric`: pattern-specific counter name

### Metrics per pattern

* **retry**: `attempt`, `success`, `giveup`
* **failfast**: `opened`, `closed`
* **featuretoggle**: `enabled`, `disabled`
* **hedge**: `success`, `failure`, `all_failed`, `timeout`
* **timeout**: `fired`
* **bulkhead**: `full`
* **cache**: `hit`, `miss`, `set`
* **circuitbreaker**: `transition.working`, `transition.recovering`, `transition.failing`, `success`
* **fallback**: `invoked`

All are OpenTelemetry `Counter` instruments. Resource attributes (e.g., `service.name`) come from your `MeterProvider` configuration.

### Wiring

1. Configure a `MeterProvider` and exporter (OTLP HTTP shown):

```python
# service/src/telemetry.py
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import set_meter_provider

from integrations.opentelemetry import FailsafeOtelInstrumentor  # or: from failsafe.integrations.opentelemetry ...

def setup_otel(service_name: str) -> MeterProvider:
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
```

2. Call `setup_otel(...)` once at process start (e.g., in FastAPI `main.py`), then use the patterns.

### FastAPI example

```python
# service/src/main.py
import asyncio
from fastapi import FastAPI, HTTPException

from telemetry import setup_otel

from failsafe.retry import retry
from failsafe.failfast import failfast, FailFastOpen
from failsafe.featuretoggle import featuretoggle, FeatureDisabled
from failsafe.hedge import hedge, HedgeTimeout
from failsafe.timeout import timeout, TimeoutError as FsTimeoutError
# add bulkhead/circuitbreaker/fallback imports as needed

setup_otel("failsafe-service")
app = FastAPI()

@hedge(name="price_quote", attempts=3, delay=0.03, timeout=0.25)
@retry(name="price_quote", attempts=3)  # backoff args per your retry API
async def fetch_price(venue: str) -> float:
    await asyncio.sleep(0.1)
    return 123.45

@featuretoggle(name="beta_orders", enabled=True)
@failfast(name="orders_write_guard", failure_threshold=1)
async def create_order_impl(payload: dict) -> dict:
    async with timeout(name="db_write_timeout", seconds=0.3):
        await asyncio.sleep(0.05)
    price = await fetch_price(payload["venue"])
    return {"ok": True, "price": price}

@app.post("/orders")
async def create_order(payload: dict):
    try:
        return await create_order_impl(payload)
    except FeatureDisabled:
        raise HTTPException(status_code=403, detail="feature disabled")
    except FailFastOpen:
        raise HTTPException(status_code=503, detail="fail-fast open")
    except HedgeTimeout:
        raise HTTPException(status_code=504, detail="pricing timed out")
    except FsTimeoutError:
        raise HTTPException(status_code=504, detail="db timeout")
```

Rules:

* Register metric listeners once via `FailsafeOtelInstrumentor().instrument(...)`.
* Always pass `name=` to each pattern factory.
* Do not attach custom listeners in app code unless you need additional behavior; OpenTelemetry listeners are globally registered.



## Acknowledgements

* <a href="https://github.com/failsafe-lib/failsafe">failsafe-lib/failsafe</a>
