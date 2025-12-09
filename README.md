<p align="center">
  <img src="docs/failsafe-logo.png" alt="Failsafe" style="max-width:350px;width:100%;height:auto;">
</p>

<p align="center">
    <em>Fault tolerance and resiliency patterns for modern Python microservices</em>
</p>

<p align="center">
    <a href="#installation">Installation</a> •
    <a href="#quick-start">Quick Start</a> •
    <a href="#rate-limiting">Rate Limiting</a> •
    <a href="#adaptive-clients">Adaptive Clients</a> •
    <a href="#resiliency-patterns">All Patterns</a> •
    <a href="#opentelemetry-integration">Observability</a>
</p>

---

**Failsafe** is a collection of production-ready resiliency patterns for microservice-based systems, implemented in idiomatic, async-only Python. It provides self-protecting services and self-regulating clients — resilience through cooperation.

Inspired by [Failsafe (Java)](https://github.com/failsafe-lib/failsafe), with first-class OpenTelemetry metrics and Prometheus integration for operational visibility.

---

## Table of Contents

- [Key Features](#key-features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Rate Limiting](#rate-limiting)
  - [Token Bucket Basics](#token-bucket-basics)
  - [Configuration Reference](#token-bucket-configuration)
  - [Retry-After Strategies](#retry-after-strategies)
  - [Backpressure Deep Dive](#backpressure-deep-dive)
- [Adaptive Clients](#adaptive-clients)
- [Resiliency Patterns](#resiliency-patterns)
  - [Retry](#retry)
  - [Circuit Breaker](#circuit-breaker)
  - [Timeout](#timeout)
  - [Bulkhead](#bulkhead)
  - [Fallback](#fallback)
  - [Hedge](#hedge)
  - [Fail Fast](#fail-fast)
  - [Feature Toggle](#feature-toggle)
  - [Cache](#cache)
- [FastAPI Integration](#fastapi-integration)
  - [Bootstrap](#bootstrap)
  - [Exception Handlers](#exception-handlers)
  - [Middleware](#middleware)
- [OpenAPI Vendor Extensions](#openapi-vendor-extensions)
- [Response Headers](#response-headers)
- [OpenTelemetry Integration](#opentelemetry-integration)
- [Prometheus Metrics](#prometheus-metrics)
- [How It Works](#how-it-works)
- [Acknowledgements](#acknowledgements)

---

## Key Features

- **AsyncIO-native** — All patterns designed for modern async Python
- **Decorator & Context Manager APIs** — Clean, Pythonic interfaces
- **Self-regulating systems** — Services and clients cooperate via backpressure signals
- **Adaptive rate limiting** — Dynamic `Retry-After` based on real-time system health
- **OpenTelemetry & Prometheus** — Built-in observability for every pattern
- **OpenAPI integration** — Define resilience in your API spec, generate protected services
- **Zero boilerplate** — One decorator, production-grade protection

---

## Requirements

- Python 3.12+

---

## Installation

```bash
# Install via uv (recommended)
uv add failsafe

# Or via pip
pip install failsafe
```

---

## Quick Start

### Protect an Endpoint in 30 Seconds

```python
from fastapi import FastAPI, Request
from failsafe.ratelimit import tokenbucket

app = FastAPI()

@app.get("/products/{product_id}")
@tokenbucket(
    name="get_product",
    max_executions=1000,
    per_time_secs=60,
)
async def get_product(request: Request, product_id: str):
    return {"id": product_id, "name": "Widget"}
```

That's it. Your endpoint now:
- Allows 1,000 requests per minute
- Returns `429 Too Many Requests` when exceeded
- Includes `Retry-After` header telling clients when to retry

---

## Rate Limiting

### Token Bucket Basics

Token bucket rate limiting works by refilling tokens at a steady rate and consuming one per request. When the bucket empties, requests are rejected with a `Retry-After` header.

$$
r = \frac{E_{max}}{T} \quad \text{tokens/second}
$$

```
refill_rate = max_executions / per_time_secs
```

```
┌─────────────────────────────────────────────────────────────────┐
│                        TOKEN BUCKET                              │
│                                                                  │
│    Tokens refill at steady rate (e.g., 166/second)              │
│                         │                                        │
│                         ▼                                        │
│                  ┌─────────────┐                                 │
│                  │ ░░░░░░░░░░░ │ ← Current tokens                │
│                  │ ░░░░░░░░░░░ │                                 │
│                  │             │ ← Bucket capacity (burst limit) │
│                  └─────────────┘                                 │
│                         │                                        │
│                         ▼                                        │
│              Request consumes 1 token                            │
│              Empty bucket → 429 rejected                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Why buckets instead of counters?**
- Counters reset abruptly at window edges, causing traffic spikes
- Buckets allow controlled **bursting** — absorb traffic spikes using accumulated tokens
- Smooth, predictable rate limiting

---

### Token Bucket Configuration

```python
@tokenbucket(
    name="get_product",           # Identifier for metrics/logging
    max_executions=10000,         # Requests allowed per time window
    per_time_secs=60,             # Time window in seconds
    bucket_size=500,              # Maximum burst capacity
    retry_after_strategy="backpressure",  # How Retry-After is calculated
    enable_per_client_tracking=True,      # Track each client separately
    track_latency=True,           # Record response times for backpressure
    
    # Backpressure tuning (when strategy="backpressure")
    p95_baseline=1.0,             # Target P95 latency (seconds)
    min_latency=0.001,            # Minimum expected latency (seconds)
    min_retry_delay=0.01,         # Minimum Retry-After (seconds)
    max_retry_penalty=1.0,        # Maximum additional wait (seconds)
    gradient_sensitivity=10.0,    # Latency change sensitivity
)
```

#### Configuration Reference

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | Required | Identifier for metrics and logging |
| `max_executions` | `int` | `100` | Total requests allowed per time window |
| `per_time_secs` | `float` | `60` | Time window in seconds |
| `bucket_size` | `int` | `max_executions` | Maximum burst capacity |
| `retry_after_strategy` | `str` | `"backpressure"` | `"fixed"`, `"backpressure"`, or `"utilization"` |
| `enable_per_client_tracking` | `bool` | `False` | Track rate limits per client ID |
| `track_latency` | `bool` | `True` | Record response times |

#### Backpressure Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `p95_baseline` | `float` | `0.2` | Target P95 response time (seconds) |
| `min_latency` | `float` | `0.05` | Floor for gradient calculation (seconds) |
| `min_retry_delay` | `float` | `1.0` | Minimum `Retry-After` value (seconds) |
| `max_retry_penalty` | `float` | `15.0` | Maximum additional penalty (seconds) |
| `gradient_sensitivity` | `float` | `2.0` | Higher = less reactive to latency changes |
| `window_size` | `int` | `100` | Latency samples in sliding window |

---

### Retry-After Strategies

#### Fixed Strategy

Returns exact time until next token — simple, predictable, no system awareness.

```python
@tokenbucket(
    name="simple_endpoint",
    max_executions=1000,
    per_time_secs=60,
    retry_after_strategy="fixed",
    track_latency=False,  # Not needed for fixed strategy
)
async def simple_endpoint(request: Request):
    return {"status": "ok"}
```

**When to use:** Simple APIs, predictable load, no latency concerns.

**Retry-After calculation:**
```
retry_after = time_until_next_token
            = 1 / refill_rate
            = per_time_secs / max_executions
```

#### Backpressure Strategy

Dynamically adjusts `Retry-After` based on system health — the sicker the system, the longer the wait.

```python
@tokenbucket(
    name="smart_endpoint",
    max_executions=10000,
    per_time_secs=60,
    bucket_size=500,
    retry_after_strategy="backpressure",
    p95_baseline=1.0,        # 1 second target
    min_retry_delay=0.01,    # 10ms minimum
    max_retry_penalty=1.0,   # 1s maximum penalty
)
async def smart_endpoint(request: Request):
    return {"status": "ok"}
```

**When to use:** Production services, variable load, latency-sensitive systems.

**Retry-After calculation:**

$$
b = \max(b_{p95}, b_{grad}) \quad \text{where} \quad b \in [0, 1]
$$
```python
backpressure = max(p95_component, gradient_component)  # 0.0 to 1.0
```

$$
t_{retry} = t_{min} + (t_{max} \times b) \times j \quad \text{where} \quad j \sim \mathcal{U}(0.8, 1.2)
$$

```python
retry_after  = min_retry_delay + (max_retry_penalty × backpressure) × jitter
```

#### Utilization Strategy

Based on bucket fill level — simpler than backpressure, no latency tracking required.

```python
@tokenbucket(
    name="utilization_endpoint",
    max_executions=1000,
    per_time_secs=60,
    retry_after_strategy="utilization",
    track_latency=False,
)
async def utilization_endpoint(request: Request):
    return {"status": "ok"}
```

---

### Backpressure Deep Dive

Backpressure monitors system health through two signals:

#### 1. P95 Component
> "Are response times exceeding our target?"

$$
b_{p95} = \frac{|\{l \in W : l > L_{baseline}\}|}{|W|}
$$

```python
# Count requests exceeding p95_baseline
violations = sum(1 for latency in window if latency > p95_baseline)
p95_component = violations / len(window)
```

#### 2. Gradient Component
> "Are response times getting worse over time?"


$$
b_{grad} = \frac{\bar{L} - L_{min}}{L_{min} \times S}
$$
```python
# Compare average latency to minimum expected
gradient = (avg_latency - min_latency) / min_latency
gradient_component = gradient / gradient_sensitivity
```

#### Combined Score

```python
backpressure = max(p95_component, gradient_component)  # Clamped 0.0-1.0
```

#### Retry-After Formula

```python
base_delay = min_retry_delay                    # e.g., 0.01s
penalty    = max_retry_penalty * backpressure   # e.g., 1.0 * 0.5 = 0.5s
jitter     = random.uniform(0.8, 1.2)           # Prevent thundering herd
retry_after = (base_delay + penalty) * jitter   # e.g., 0.51 * 1.1 = 0.56s
```

#### Adaptive Baseline

The P95 baseline slowly drifts toward reality:

$$
L_{baseline}^{(t+1)} = 0.95 \cdot L_{baseline}^{(t)} + 0.05 \cdot L_{p95}^{(t)}
$$
```python
# 95% old value, 5% new measurement
self.p95_baseline = self.p95_baseline * 0.95 + actual_p95 * 0.05
```

This prevents stale baselines when your service gets faster (optimizations) or legitimately slower (data growth).

---

## Adaptive Clients

### The Problem

A rate-limited server returns `Retry-After: 2` but badly-behaved clients ignore it, hammering the server with rejected requests. Wasteful for everyone.

### The Solution

The `@adaptive` decorator creates self-regulating clients that respect server signals:

```python
from failsafe.client import EnhancedClientInterface, adaptive


class ProductClient(EnhancedClientInterface):
    """Self-regulating client that respects backpressure signals."""
    
    @adaptive(strategy="queue", max_retries=3)
    def create_product(self, data: ProductRequest) -> ProductResponse:
        return ProductResponse.parse_obj(
            self.send_request(
                method="POST",
                endpoint="/products",
                json=data.model_dump()
            )
        )
    
    @adaptive(strategy="reject")
    def get_product(self, product_id: str) -> ProductResponse:
        return ProductResponse.parse_obj(
            self.send_request(
                method="GET",
                endpoint=f"/products/{product_id}"
            )
        )


# Usage
client = ProductClient(base_url="http://product-service:8000")
product = client.create_product(ProductRequest(name="Widget", price=29.99))
```

### Strategies

| Strategy | Behavior |
|----------|----------|
| `"queue"` | Wait for `Retry-After` duration, then automatically retry |
| `"reject"` | Immediately raise `RateLimitedError` with wait time |

### What the Client Reads

| Header | Purpose |
|--------|---------|
| `Retry-After` | Seconds to wait before retrying |
| `X-Backpressure` | System stress level (0.0-1.0) — slow down proactively |
| `RateLimit-Remaining` | Tokens left — stop before hitting limit |

---

## Resiliency Patterns

All patterns support both **decorator** and **async context manager** APIs.

### Retry

Automatically retry operations on transient failures.

```python
from failsafe.retry import retry

@retry(
    name="fetch_data",
    attempts=3,
    delay=0.5,
    backoff=2.0,              # Exponential backoff multiplier
    exceptions=(ConnectionError, TimeoutError),
)
async def fetch_data(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()
```

Or as context manager:

```python
from failsafe.retry import retry

async def fetch_with_retry():
    async with retry(name="fetch", attempts=3, delay=1.0):
        return await external_api.call()
```

---

### Circuit Breaker

Stop calling failing downstream services — fail fast, recover gradually.

```python
from failsafe.circuitbreaker import circuitbreaker, CircuitBreakerOpen

@circuitbreaker(
    name="payment_service",
    failure_threshold=5,      # Open after 5 failures
    recovery_timeout=30,      # Try again after 30 seconds
    half_open_requests=3,     # Allow 3 test requests when recovering
)
async def process_payment(order_id: str) -> PaymentResult:
    return await payment_gateway.charge(order_id)

# Handle open circuit
try:
    result = await process_payment("order-123")
except CircuitBreakerOpen:
    return {"status": "payment_unavailable", "retry_later": True}
```

**States:**
- **Closed**: Normal operation, requests flow through
- **Open**: Failing, reject immediately without calling downstream
- **Half-Open**: Testing recovery, allow limited requests

---

### Timeout

Bound execution time with deterministic timeouts.

```python
from failsafe.timeout import timeout, TimeoutError as FsTimeoutError

@timeout(name="db_query", seconds=5.0)
async def query_database(query: str) -> list:
    return await db.execute(query)

# Or as context manager
async def fetch_with_timeout():
    async with timeout(name="api_call", seconds=2.0):
        return await slow_api.fetch()
```

---

### Bulkhead

Limit concurrent executions to prevent resource exhaustion.

```python
from failsafe.bulkhead import bulkhead, BulkheadFull

@bulkhead(
    name="report_generator",
    max_concurrent=10,        # Maximum parallel executions
    max_queued=50,            # Maximum waiting in queue
)
async def generate_report(report_id: str) -> Report:
    return await heavy_computation(report_id)

try:
    report = await generate_report("report-123")
except BulkheadFull:
    return {"status": "busy", "message": "Try again later"}
```

---

### Fallback

Gracefully degrade when dependencies fail.

```python
from failsafe.fallback import fallback

async def get_cached_price(product_id: str) -> float:
    return await cache.get(f"price:{product_id}") or 0.0

@fallback(name="pricing", fallback_fn=get_cached_price)
async def get_live_price(product_id: str) -> float:
    return await pricing_service.get_price(product_id)
```

---

### Hedge

Race parallel requests, return first success — reduce tail latency.

```python
from failsafe.hedge import hedge, HedgeTimeout

@hedge(
    name="price_quote",
    attempts=3,               # Run up to 3 parallel requests
    delay=0.03,               # Stagger by 30ms
    timeout=0.25,             # Total timeout
)
async def get_price(venue: str) -> float:
    return await venue_api.fetch_price(venue)
```

---

### Fail Fast

Immediately fail when system is in known bad state.

```python
from failsafe.failfast import failfast, FailFastOpen

@failfast(
    name="orders_write",
    failure_threshold=3,
)
async def create_order(order: Order) -> OrderResult:
    return await order_service.create(order)

try:
    result = await create_order(order)
except FailFastOpen:
    raise HTTPException(503, "Service temporarily unavailable")
```

---

### Feature Toggle

Enable/disable features without redeployment.

```python
from failsafe.featuretoggle import featuretoggle, FeatureDisabled

@featuretoggle(name="new_checkout", enabled=False)
async def checkout_v2(cart: Cart) -> CheckoutResult:
    return await new_checkout_service.process(cart)

try:
    result = await checkout_v2(cart)
except FeatureDisabled:
    return await checkout_v1(cart)  # Fall back to old version
```

---

### Cache

Cache expensive operation results.

```python
from failsafe.cache import cache

@cache(
    name="user_profile",
    ttl=300,                  # Cache for 5 minutes
    max_size=1000,            # Maximum cached entries
)
async def get_user_profile(user_id: str) -> UserProfile:
    return await user_service.fetch_profile(user_id)
```

---

## FastAPI Integration

### Bootstrap

Full resilience setup in one place:

```python
from fastapi import FastAPI, Request, HTTPException
from failsafe.integrations.fastapi import FailsafeController
from failsafe.ratelimit import tokenbucket
from failsafe import Strategy, Telemetry, Protection

app = FastAPI(title="Product Service", version="1.0.0")

# One-line resilience setup
FailsafeController(app) \
    .with_telemetry(Telemetry.OTEL) \
    .with_protection(Protection.INGRESS)


@app.get("/products/{product_id}")
@tokenbucket(
    name="get_product",
    max_executions=5000,
    per_time_secs=60,
    bucket_size=500,
    retry_after_strategy=Strategy.BACKPRESSURE,
)
async def get_product(request: Request, product_id: str):
    return await product_service.get(product_id)


@app.post("/products")
@tokenbucket(
    name="create_product",
    max_executions=1000,
    per_time_secs=60,
    retry_after_strategy=Strategy.BACKPRESSURE,
)
async def create_product(request: Request, product: ProductCreate):
    return await product_service.create(product)
```

---

### Exception Handlers

Failsafe provides ready-to-use exception handlers:

```python
from failsafe.integrations.fastapi_helpers import register_exception_handlers

app = FastAPI()
register_exception_handlers(app)
```

This registers handlers for:

| Exception | Status | Response |
|-----------|--------|----------|
| `RateLimitExceeded` | `429` | Includes `Retry-After` header |
| `AttemptsExceeded` | `503` | All retry attempts failed |
| `CircuitBreakerOpen` | `503` | Circuit breaker tripped |
| `BulkheadFull` | `503` | Concurrency limit reached |
| `TimeoutError` | `504` | Operation timed out |

Or register manually:

```python
from fastapi import Request
from fastapi.responses import JSONResponse
from failsafe.ratelimit.exceptions import RateLimitExceeded

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": f"Rate limit exceeded. Retry after {exc.retry_after_ms}ms",
            "retry_after_ms": exc.retry_after_ms,
        },
        headers={
            "Retry-After": str(int(exc.retry_after_ms / 1000)),
            "X-RateLimit-Retry-After-Ms": str(exc.retry_after_ms),
        },
    )
```

---

### Middleware

Add rate limit info to all responses:

```python
from failsafe.integrations.fastapi_helpers import RateLimitMiddleware

app.add_middleware(RateLimitMiddleware)
```

This adds headers to successful responses:
- `RateLimit-Limit`: Maximum requests allowed
- `RateLimit-Remaining`: Tokens remaining
- `X-Backpressure`: Current system stress (0.0-1.0)

---

## OpenAPI Vendor Extensions

Define resilience patterns in your OpenAPI specification, then generate protected services automatically with [failsafe-generator](https://github.com/yourorg/failsafe-generator).

### Rate Limiting (`x-ratelimit`)

```yaml
paths:
  /products:
    get:
      operationId: list_products
      x-ratelimit:
        name: list_products
        max_executions: 5000
        per_time_secs: 60
        bucket_size: 500
        retry_after_strategy: backpressure
        p95_baseline: 1.0
        min_retry_delay: 0.01
        max_retry_penalty: 1.0
      responses:
        '200':
          description: OK
```

Generates:

```python
@tokenbucket(
    name="list_products",
    max_executions=5000,
    per_time_secs=60,
    bucket_size=500,
    retry_after_strategy="backpressure",
    p95_baseline=1.0,
    min_retry_delay=0.01,
    max_retry_penalty=1.0,
)
@router.get("/products")
async def list_products(request: Request):
    ...
```

### Retry (`x-retry`)

```yaml
paths:
  /orders:
    post:
      operationId: create_order
      x-retry:
        name: create_order_retry
        attempts: 3
        delay: 0.5
        backoff: 2.0
        exceptions:
          - ConnectionError
          - TimeoutError
      responses:
        '200':
          description: OK
```

Generates:

```python
@retry(
    name="create_order_retry",
    attempts=3,
    delay=0.5,
    backoff=2.0,
    exceptions=(ConnectionError, TimeoutError),
)
@router.post("/orders")
async def create_order(request: Request, order: OrderCreate):
    ...
```

### Circuit Breaker (`x-circuitbreaker`)

```yaml
paths:
  /payments:
    post:
      operationId: process_payment
      x-circuitbreaker:
        name: payment_circuit
        failure_threshold: 5
        recovery_timeout: 30
      responses:
        '200':
          description: OK
```

---

## Response Headers

### Successful Responses (2xx)

| Header | Example | Description |
|--------|---------|-------------|
| `RateLimit-Limit` | `10000` | Maximum requests per window |
| `RateLimit-Remaining` | `9487` | Tokens remaining |
| `X-Backpressure` | `0.25` | System stress (0.0-1.0) |
| `X-Client-Id` | `192.168.1.100` | Client identifier used |

### Rate Limited Responses (429)

| Header | Example | Description |
|--------|---------|-------------|
| `Retry-After` | `2` | Seconds to wait (RFC 7231) |
| `X-RateLimit-Retry-After-Ms` | `1850` | Precise milliseconds |
| `X-Backpressure` | `0.75` | Current stress level |
| `X-Client-Id` | `192.168.1.100` | Client identifier |

### Example Response

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 2
X-RateLimit-Retry-After-Ms: 1850
X-Backpressure: 0.75
X-Client-Id: 192.168.1.100
Content-Type: application/json

{
  "error": "rate_limit_exceeded",
  "message": "Rate limit exceeded. Retry after 1850ms",
  "retry_after_seconds": 1.85,
  "retry_after_ms": 1850,
  "client_id": "192.168.1.100"
}
```

---

## OpenTelemetry Integration

### Setup

```python
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import set_meter_provider

from failsafe.integrations.opentelemetry import FailsafeOtelInstrumentor


def setup_telemetry(service_name: str) -> MeterProvider:
    resource = Resource.create({"service.name": service_name})
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint="http://otel-collector:4318/v1/metrics",
            timeout=5,
        )
    )
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    set_meter_provider(provider)
    
    # Register Failsafe metrics
    FailsafeOtelInstrumentor().instrument(
        namespace="failsafe.service",
        meter_provider=provider,
    )
    
    return provider


# Call once at startup
setup_telemetry("product-service")
```

### Metrics Emitted

Naming scheme: `{namespace}.{component_name}.{pattern}.{metric}`

| Pattern | Metrics |
|---------|---------|
| **retry** | `attempt`, `success`, `giveup` |
| **circuitbreaker** | `transition.working`, `transition.recovering`, `transition.failing`, `success` |
| **timeout** | `fired` |
| **bulkhead** | `full` |
| **cache** | `hit`, `miss`, `set` |
| **failfast** | `opened`, `closed` |
| **featuretoggle** | `enabled`, `disabled` |
| **hedge** | `success`, `failure`, `all_failed`, `timeout` |
| **fallback** | `invoked` |

---

## Prometheus Metrics

The rate limiter exposes Prometheus metrics automatically:

### Counters

| Metric | Labels | Description |
|--------|--------|-------------|
| `failsafe_ratelimit_requests_total` | `pattern`, `client`, `status` | Total requests (allowed/rejected) |
| `failsafe_ratelimit_tokens_consumed_total` | `pattern` | Tokens consumed |
| `failsafe_ratelimit_rejections_total` | `pattern`, `client`, `reason` | Rejections by reason |

### Gauges

| Metric | Labels | Description |
|--------|--------|-------------|
| `failsafe_ratelimit_tokens_available` | `pattern` | Current available tokens |
| `failsafe_ratelimit_tokens_max` | `pattern` | Bucket capacity |
| `failsafe_ratelimit_bucket_utilization_ratio` | `pattern` | Fill percentage (0.0-1.0) |
| `failsafe_ratelimit_backpressure_score` | `pattern`, `client` | Backpressure level (0.0-1.0) |
| `failsafe_ratelimit_token_refill_rate` | `pattern` | Tokens per second |

### Histograms

| Metric | Labels | Description |
|--------|--------|-------------|
| `failsafe_ratelimit_request_latency_seconds` | `pattern`, `client` | Request latencies |
| `failsafe_ratelimit_retry_after_seconds` | `pattern`, `client` | Retry-After values |

---

## How It Works

### Request Flow (Backpressure Perspective)

#### Happy Path (Token Available)

1. Client calls `@adaptive` decorated method
2. Client checks if currently rate-limited
3. Client sends HTTP request
4. Server receives request, hits `@tokenbucket`
5. Server checks bucket — token available, consumes 1
6. Server executes business logic, records latency
7. Server returns `200` with `X-Backpressure` header
8. Client notes backpressure, optionally slows down

#### Rejection Path (Bucket Empty)

1. Client sends HTTP request
2. Server checks bucket — **empty**
3. Server calculates time until next token
4. Server queries backpressure calculator:
   - Compute P95 component from latency window
   - Compute gradient component from latency trend
   - Return `max(P95, gradient)` as score
5. Server calculates `Retry-After = min_delay + (max_penalty × backpressure)`
6. Server returns `429` with `Retry-After` header
7. Client `@adaptive` reads header, waits
8. Client retries after wait period
9. Server (now has tokens) processes successfully

### Self-Stabilisation

When server and client cooperate:

```
Load spike → Bucket empties → 429s returned
    ↓
Backpressure rises → Longer Retry-After
    ↓
Adaptive clients wait longer
    ↓
Request rate decreases → Bucket refills
    ↓
Backpressure drops → Shorter Retry-After
    ↓
System finds equilibrium
```

---

## Legend


## Acknowledgements

- [failsafe-lib/failsafe](https://github.com/failsafe-lib/failsafe) — Original Java implementation
- [resilience4j](https://github.com/resilience4j/resilience4j) — Additional pattern inspiration

---

<p align="center">
  <em>Resilience-as-code: generate self-protecting services and self-regulating clients from your API spec.</em>
</p>