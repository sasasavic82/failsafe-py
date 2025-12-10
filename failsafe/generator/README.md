<p align="center">
  <img src="../../docs//logo.png" alt="Failsafe" style="max-width:350px;width:100%;height:auto;">
</p>

<p align="center">
    <em>Fault tolerance and resiliency patterns for modern Python microservices</em>
</p>

<p align="center">
    <a href="#installation">Installation</a> •
    <a href="#quick-start">Quick Start</a> •
    <a href="#code-generation">Code Generation</a> •
    <a href="#openapi-vendor-extensions">Vendor Extensions</a> •
    <a href="#resiliency-patterns">Patterns</a> •
    <a href="#observability">Observability</a>
</p>

---

**Failsafe** is a collection of production-ready resiliency patterns for microservice-based systems, implemented in idiomatic, async-only Python. It provides self-protecting services and self-regulating clients — resilience through cooperation.

Includes a code generator that transforms OpenAPI specifications into fully working, protected FastAPI services — define your resilience patterns in your spec, generate production-ready code automatically.

---

## Table of Contents

- [Key Features](#key-features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Code Generation](#code-generation)
  - [CLI Reference](#cli-reference)
  - [Generated Output](#generated-output)
- [OpenAPI Vendor Extensions](#openapi-vendor-extensions)
  - [Global Configuration](#global-configuration)
  - [Rate Limiting](#rate-limiting)
  - [Retry](#retry)
  - [Circuit Breaker](#circuit-breaker)
  - [Timeout](#timeout)
  - [Combining Patterns](#combining-multiple-patterns)
  - [Complete Example](#complete-openapi-example)
- [Resiliency Patterns](#resiliency-patterns)
  - [Rate Limiting](#rate-limiting-decorator)
  - [Retry](#retry-1)
  - [Circuit Breaker](#circuit-breaker-1)
  - [Timeout](#timeout-1)
  - [Bulkhead](#bulkhead)
  - [Fallback](#fallback)
  - [Hedge](#hedge)
  - [Fail Fast](#fail-fast)
  - [Feature Toggle](#feature-toggle)
  - [Cache](#cache)
- [FastAPI Integration](#fastapi-integration)
- [Adaptive Clients](#adaptive-clients)
- [Observability](#observability)
  - [OpenTelemetry](#opentelemetry-integration)
  - [Prometheus Metrics](#prometheus-metrics)
- [How It Works](#how-it-works)
- [Acknowledgements](#acknowledgements)

---

## Key Features

- **Spec-Driven Resilience** — Define rate limits, retries, and circuit breakers in your OpenAPI spec
- **Code Generation** — Generate production-ready FastAPI services from OpenAPI specs
- **One-Line Bootstrap** — `FailsafeController` for clean service setup
- **AsyncIO-Native** — All patterns designed for modern async Python
- **Self-Regulating Systems** — Services and clients cooperate via backpressure signals
- **Adaptive Rate Limiting** — Dynamic `Retry-After` based on real-time system health
- **Telemetry Built-In** — OpenTelemetry and Prometheus integration out of the box
- **Control Plane Ready** — Dynamic configuration updates without redeployment

---

## Requirements

- Python 3.12+
- For code generation: `openapi-generator-cli` or Docker

---

## Installation

```bash
# Install via uv (recommended)
uv add failsafe

# Or via pip
pip install failsafe

# Verify CLI
failsafe --help
```

---

## Quick Start

### Option 1: Generate from OpenAPI Spec

```bash
# Generate a resilient service from your spec
failsafe generate api.yaml -o ./my-service --package-name my_service

# Run it
cd my-service && uvicorn main:app --reload
```

### Option 2: Add to Existing FastAPI App

```python
from fastapi import FastAPI, Request
from failsafe import FailsafeController, Telemetry, Protection
from failsafe.ratelimit import tokenbucket, Strategy

app = FastAPI()

# One-line resilience bootstrap
FailsafeController(app) \
    .with_telemetry(Telemetry.OTEL) \
    .with_protection(Protection.INGRESS) \
    .with_controlplane()


@app.get("/products/{product_id}")
@tokenbucket(
    name="get_product",
    max_executions=5000,
    per_time_secs=60,
    retry_after_strategy=Strategy.BACKPRESSURE,
)
async def get_product(request: Request, product_id: str):
    return {"id": product_id, "name": "Widget"}
```

---

## Code Generation

Generate production-ready FastAPI services from OpenAPI specifications with resilience patterns baked in.

### CLI Reference

```bash
failsafe generate <spec> [OPTIONS]
```

#### Arguments

| Argument | Description |
|----------|-------------|
| `spec` | Path to OpenAPI spec file (YAML or JSON) |

#### Basic Options

| Option | Default | Description |
|--------|---------|-------------|
| `-o, --out` | `./generated-server` | Output directory |
| `--package-name` | `service` | Python package name |
| `--app-name` | `service` | Application display name |
| `--app-version` | `0.1.0` | Application version |
| `--server-port` | `8080` | Default server port |
| `--dockerfile/--no-dockerfile` | `true` | Generate Dockerfile |

#### Telemetry Options

| Option | Default | Description |
|--------|---------|-------------|
| `--telemetry` | `OTEL` | Backend: `OTEL`, `PROMETHEUS`, `NONE` |
| `--otel-endpoint` | `http://otel-collector:4318/v1/metrics` | OTLP collector endpoint |

#### Protection Options

| Option | Default | Description |
|--------|---------|-------------|
| `--protection/--no-protection` | `true` | Enable protection handlers |
| `--protection-type` | `INGRESS` | Type: `INGRESS`, `EGRESS`, `FULL` |

#### Control Plane Options

| Option | Default | Description |
|--------|---------|-------------|
| `--controlplane/--no-controlplane` | `true` | Enable control plane |
| `--controlplane-url` | `http://failsafe-controlplane:8080` | Control plane URL |

#### Examples

```bash
# Full setup with all defaults
failsafe generate openapi.yaml \
  -o ./my-service \
  --package-name my_service

# Minimal setup (no telemetry, no controlplane)
failsafe generate openapi.yaml \
  --telemetry NONE \
  --no-protection \
  --no-controlplane

# Custom endpoints
failsafe generate openapi.yaml \
  --otel-endpoint http://localhost:4318/v1/metrics \
  --controlplane-url http://localhost:8080

# Full protection (both ingress and egress)
failsafe generate openapi.yaml --protection-type FULL
```

### Generated Output

```
generated-service/
├── main.py                    # FastAPI app with FailsafeController
├── requirements.txt
├── pyproject.toml
├── Dockerfile
├── .env
├── .config/
│   ├── otel-config.yaml       # OTEL Collector configuration
│   └── prometheus.yml         # Prometheus scrape configuration
└── my_service/
    ├── __init__.py
    ├── settings.py
    ├── apis/
    │   └── products_api.py    # Routes with resilience decorators
    └── models/
        └── product.py
```

---

## OpenAPI Vendor Extensions

Define resilience patterns directly in your OpenAPI specification using `x-telstra` vendor extensions.

### Global Configuration

Configure service-wide settings at the root level:

```yaml
openapi: 3.1.0
info:
  title: My Service
  version: 1.0.0

x-telstra:
  otel:
    enabled: true
    endpoint: http://otel-collector:4318/v1/metrics
  controller:
    enabled: true
    url: http://failsafe-controlplane:8080
  protection:
    type: ingress
```

---

### Rate Limiting

Protect endpoints from excessive requests using token bucket rate limiting.

```yaml
paths:
  /products:
    get:
      operationId: list_products
      x-telstra:
        resiliency:
          ratelimit:
            enabled: true
            name: list_products
            max_executions: 5000
            per_time_secs: 60
            bucket_size: 500
            retry_after_strategy: backpressure
            p95_baseline: 1.0
            min_latency: 0.001
            min_retry_delay: 0.01
            max_retry_penalty: 1.0
            gradient_sensitivity: 10.0
      responses:
        '200':
          description: OK
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | `boolean` | `true` | Enable/disable rate limiting |
| `name` | `string` | `operationId` | Identifier for metrics |
| `max_executions` | `integer` | `100` | Requests per time window |
| `per_time_secs` | `number` | `60` | Time window in seconds |
| `bucket_size` | `integer` | `max_executions` | Maximum burst capacity |
| `retry_after_strategy` | `string` | `backpressure` | `fixed`, `backpressure`, `utilization` |
| `p95_baseline` | `number` | `0.2` | Target P95 latency (seconds) |
| `min_latency` | `number` | `0.05` | Minimum expected latency |
| `min_retry_delay` | `number` | `1.0` | Minimum Retry-After value |
| `max_retry_penalty` | `number` | `15.0` | Maximum additional wait |
| `gradient_sensitivity` | `number` | `2.0` | Latency sensitivity |

#### Generated Code

```python
@router.get("/products")
@tokenbucket(
    name="list_products",
    max_executions=5000,
    per_time_secs=60,
    bucket_size=500,
    retry_after_strategy=Strategy.BACKPRESSURE,
    p95_baseline=1.0,
    min_latency=0.001,
)
async def list_products(request: Request) -> List[Product]:
    ...
```

---

### Retry

Automatically retry failed operations with exponential backoff.

```yaml
paths:
  /orders:
    post:
      operationId: create_order
      x-telstra:
        resiliency:
          retry:
            enabled: true
            name: create_order
            attempts: 3
            delay: 0.5
            backoff: 2.0
            max_delay: 30.0
            exceptions:
              - ConnectionError
              - TimeoutError
      responses:
        '200':
          description: OK
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | `boolean` | `true` | Enable/disable retry |
| `name` | `string` | `operationId` | Identifier for metrics |
| `attempts` | `integer` | `3` | Maximum retry attempts |
| `delay` | `number` | `1.0` | Initial delay between retries |
| `backoff` | `number` | `2.0` | Exponential backoff multiplier |
| `max_delay` | `number` | `60.0` | Maximum delay cap |
| `exceptions` | `array` | `[Exception]` | Exceptions to retry on |

#### Generated Code

```python
@router.post("/orders")
@retry(
    name="create_order",
    attempts=3,
    delay=0.5,
    backoff=2.0,
)
async def create_order(request: Request, order: OrderCreate) -> Order:
    ...
```

---

### Circuit Breaker

Prevent cascading failures by stopping calls to failing services.

```yaml
paths:
  /payments:
    post:
      operationId: process_payment
      x-telstra:
        resiliency:
          circuitbreaker:
            enabled: true
            name: payment_gateway
            failure_threshold: 5
            recovery_timeout: 30
            half_open_requests: 3
      responses:
        '200':
          description: OK
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | `boolean` | `true` | Enable/disable circuit breaker |
| `name` | `string` | `operationId` | Identifier for metrics |
| `failure_threshold` | `integer` | `5` | Failures before opening |
| `recovery_timeout` | `number` | `30` | Seconds before half-open |
| `half_open_requests` | `integer` | `3` | Test requests in half-open |

#### Generated Code

```python
@router.post("/payments")
@circuitbreaker(
    name="payment_gateway",
    failure_threshold=5,
    recovery_timeout=30,
)
async def process_payment(request: Request, payment: PaymentRequest) -> Payment:
    ...
```

---

### Timeout

Bound execution time for operations.

```yaml
paths:
  /reports:
    get:
      operationId: generate_report
      x-telstra:
        resiliency:
          timeout:
            enabled: true
            name: report_generation
            seconds: 30.0
      responses:
        '200':
          description: OK
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | `boolean` | `true` | Enable/disable timeout |
| `name` | `string` | `operationId` | Identifier for metrics |
| `seconds` | `number` | `30.0` | Timeout duration |

#### Generated Code

```python
@router.get("/reports")
@timeout(name="report_generation", seconds=30.0)
async def generate_report(request: Request) -> Report:
    ...
```

---

### Combining Multiple Patterns

Apply multiple resilience patterns to a single endpoint:

```yaml
paths:
  /orders:
    post:
      operationId: create_order
      x-telstra:
        resiliency:
          ratelimit:
            enabled: true
            max_executions: 1000
            per_time_secs: 60
          retry:
            enabled: true
            attempts: 3
            delay: 0.5
          circuitbreaker:
            enabled: true
            failure_threshold: 5
          timeout:
            enabled: true
            seconds: 10.0
      responses:
        '200':
          description: OK
```

#### Generated Code (Stacked Decorators)

```python
@router.post("/orders")
@tokenbucket(name="create_order", max_executions=1000, per_time_secs=60)
@circuitbreaker(name="create_order_circuit", failure_threshold=5)
@retry(name="create_order_retry", attempts=3, delay=0.5)
@timeout(name="create_order_timeout", seconds=10.0)
async def create_order(request: Request, order: OrderCreate) -> Order:
    ...
```

---

### Complete OpenAPI Example

```yaml
openapi: 3.1.0
info:
  title: Inventory Service
  version: 0.1.0

x-telstra:
  otel:
    enabled: true
  controller:
    enabled: true

servers:
  - url: "http://0.0.0.0:8001"

paths:
  /inventories:
    get:
      tags:
        - inventories
      summary: Get Inventories
      operationId: get_inventories
      x-telstra:
        resiliency:
          ratelimit:
            enabled: true
            max_executions: 5000
            per_time_secs: 60
            p95_baseline: 0.5
            min_latency: 0.01
      responses:
        "200":
          description: Successful Response
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/Inventory"

    post:
      tags:
        - inventories
      summary: Create Inventory
      operationId: create_inventory
      x-telstra:
        resiliency:
          ratelimit:
            enabled: true
            max_executions: 1000
            per_time_secs: 60
          retry:
            enabled: true
            attempts: 3
            delay: 0.5
            backoff: 2.0
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/InventoryRequest"
      responses:
        "200":
          description: Successful Response
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Inventory"

  /inventories/{inventory_id}:
    get:
      tags:
        - inventories
      summary: Get Inventory
      operationId: get_inventory
      x-telstra:
        resiliency:
          ratelimit:
            enabled: true
            max_executions: 5000
            per_time_secs: 60
          timeout:
            enabled: true
            seconds: 5.0
      parameters:
        - name: inventory_id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Successful Response
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Inventory"

    delete:
      tags:
        - inventories
      summary: Delete Inventory
      operationId: delete_inventory
      x-telstra:
        resiliency:
          circuitbreaker:
            enabled: true
            failure_threshold: 3
            recovery_timeout: 60
      parameters:
        - name: inventory_id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Successful Response

  /inventories/{inventory_id}/stock:
    post:
      tags:
        - inventories
      summary: Adjust Stock
      operationId: adjust_stock
      x-telstra:
        resiliency:
          ratelimit:
            enabled: true
            max_executions: 2000
            per_time_secs: 60
            p95_baseline: 0.2
            min_latency: 0.05
          retry:
            enabled: true
            attempts: 3
            delay: 1.0
      parameters:
        - name: inventory_id
          in: path
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/StockAdjustment"
      responses:
        "200":
          description: Successful Response
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Inventory"

components:
  schemas:
    Inventory:
      type: object
      required:
        - id
        - product_id
        - stock
      properties:
        id:
          type: string
        product_id:
          type: string
        stock:
          type: integer
          minimum: 0
        low_stock_threshold:
          type: integer
          default: 10

    InventoryRequest:
      type: object
      required:
        - product_id
      properties:
        product_id:
          type: string
        stock:
          type: integer
          minimum: 0
          default: 0

    StockAdjustment:
      type: object
      required:
        - amount
      properties:
        amount:
          type: integer
```

---

## Resiliency Patterns

All patterns support both **decorator** and **async context manager** APIs.

### Rate Limiting (Decorator)

```python
from failsafe.ratelimit import tokenbucket, Strategy

@tokenbucket(
    name="get_product",
    max_executions=5000,
    per_time_secs=60,
    bucket_size=500,
    retry_after_strategy=Strategy.BACKPRESSURE,
)
async def get_product(request: Request, product_id: str):
    return await product_service.get(product_id)
```

### Retry

```python
from failsafe.retry import retry

@retry(name="fetch_data", attempts=3, delay=0.5, backoff=2.0)
async def fetch_data(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        return (await client.get(url)).json()
```

### Circuit Breaker

```python
from failsafe.circuitbreaker import circuitbreaker, CircuitBreakerOpen

@circuitbreaker(name="payment_service", failure_threshold=5, recovery_timeout=30)
async def process_payment(order_id: str) -> PaymentResult:
    return await payment_gateway.charge(order_id)
```

### Timeout

```python
from failsafe.timeout import timeout

@timeout(name="db_query", seconds=5.0)
async def query_database(query: str) -> list:
    return await db.execute(query)
```

### Bulkhead

```python
from failsafe.bulkhead import bulkhead, BulkheadFull

@bulkhead(name="report_generator", max_concurrent=10, max_queued=50)
async def generate_report(report_id: str) -> Report:
    return await heavy_computation(report_id)
```

### Fallback

```python
from failsafe.fallback import fallback

async def get_cached_price(product_id: str) -> float:
    return await cache.get(f"price:{product_id}") or 0.0

@fallback(name="pricing", fallback_fn=get_cached_price)
async def get_live_price(product_id: str) -> float:
    return await pricing_service.get_price(product_id)
```

### Hedge

```python
from failsafe.hedge import hedge

@hedge(name="price_quote", attempts=3, delay=0.03, timeout=0.25)
async def get_price(venue: str) -> float:
    return await venue_api.fetch_price(venue)
```

### Fail Fast

```python
from failsafe.failfast import failfast, FailFastOpen

@failfast(name="orders_write", failure_threshold=3)
async def create_order(order: Order) -> OrderResult:
    return await order_service.create(order)
```

### Feature Toggle

```python
from failsafe.featuretoggle import featuretoggle, FeatureDisabled

@featuretoggle(name="new_checkout", enabled=False)
async def checkout_v2(cart: Cart) -> CheckoutResult:
    return await new_checkout_service.process(cart)
```

### Cache

```python
from failsafe.cache import cache

@cache(name="user_profile", ttl=300, max_size=1000)
async def get_user_profile(user_id: str) -> UserProfile:
    return await user_service.fetch_profile(user_id)
```

---

## FastAPI Integration

### Bootstrap

```python
from fastapi import FastAPI
from failsafe import FailsafeController, Telemetry, Protection

app = FastAPI(title="My Service")

FailsafeController(app) \
    .with_telemetry(Telemetry.OTEL) \
    .with_protection(Protection.INGRESS) \
    .with_controlplane()
```

This single chain:
- Sets up OpenTelemetry metrics export
- Registers exception handlers (429, 503, 504)
- Adds `RateLimit-*` headers middleware
- Enables control plane for dynamic config

---

## Adaptive Clients

Create self-regulating clients that respect server backpressure:

```python
from failsafe.client import EnhancedClientInterface, adaptive


class ProductClient(EnhancedClientInterface):
    
    @adaptive(strategy="queue", max_retries=3)
    def create_product(self, data: ProductRequest) -> ProductResponse:
        return ProductResponse.parse_obj(
            self.send_request(
                method="POST",
                endpoint="/products",
                json=data.model_dump()
            )
        )


client = ProductClient(base_url="http://product-service:8000")
product = client.create_product(ProductRequest(name="Widget", price=29.99))
```

---

## Observability

### OpenTelemetry Integration

Configured automatically with `FailsafeController.with_telemetry(Telemetry.OTEL)`, or manually:

```python
from failsafe.integrations.opentelemetry import FailsafeOtelInstrumentor

FailsafeOtelInstrumentor().instrument(
    namespace="failsafe.my_service",
    meter_provider=meter_provider,
)
```

### Prometheus Metrics

| Metric | Labels | Description |
|--------|--------|-------------|
| `failsafe_ratelimit_requests_total` | `pattern`, `status` | Total requests |
| `failsafe_ratelimit_tokens_available` | `pattern` | Current tokens |
| `failsafe_ratelimit_backpressure_score` | `pattern` | Stress level (0-1) |
| `failsafe_ratelimit_request_latency_seconds` | `pattern` | Request latencies |

---

## How It Works

### Token Bucket + Backpressure

Token bucket rate limiting works by refilling tokens at a steady rate and consuming one per request. When the bucket empties, requests are rejected with a `Retry-After` header calculated by the backpressure system, which monitors the P95 latency sliding window and latency gradient to determine system stress — returning shorter waits when healthy and longer waits when response times are degrading.

### Formulas

**Backpressure Score:**
$$
b = \max(b_{p95}, b_{grad}) \quad \text{where} \quad b \in [0, 1]
$$

**Retry-After Calculation:**
$$
t_{retry} = (t_{min} + t_{max} \times b) \times j \quad \text{where} \quad j \sim \mathcal{U}(0.8, 1.2)
$$

**Refill Rate:**
$$
r = \frac{E_{max}}{T} \quad \text{tokens/second}
$$

---

## Acknowledgements

- [failsafe-lib/failsafe](https://github.com/failsafe-lib/failsafe) — Java resilience patterns inspiration
- [openapi-generator](https://github.com/OpenAPITools/openapi-generator) — Code generation
- [FastAPI](https://fastapi.tiangolo.com/) — Modern Python web framework

---

<p align="center">
  <em>Resilience-as-code: generate self-protecting services and self-regulating clients from your API spec.</em>
</p>