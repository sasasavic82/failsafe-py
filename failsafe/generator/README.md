<p align="center">
  <img src="../../docs/logo.png" alt="Failsafe Generator" style="max-width:350px;width:100%;height:auto;">
</p>

<p align="center">
    <em>From OpenAPI spec to production-ready resilient FastAPI service — in one command</em>
</p>

<p align="center">
    <a href="#installation">Installation</a> •
    <a href="#quick-start">Quick Start</a> •
    <a href="#cli-reference">CLI Reference</a> •
    <a href="#openapi-vendor-extensions">Vendor Extensions</a> •
    <a href="#generated-output">Generated Output</a>
</p>

---

**failsafe-generator** is a custom OpenAPI code generator that extends [`openapi-generator`](https://github.com/OpenAPITools/openapi-generator) to produce production-ready, resilient FastAPI microservices.

Define your resilience patterns directly in your OpenAPI specification — rate limits, retries, circuit breakers — and generate fully working, protected services automatically.

---

## Table of Contents

- [Key Features](#key-features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
- [OpenAPI Vendor Extensions](#openapi-vendor-extensions)
  - [Global Configuration](#global-configuration)
  - [Rate Limiting](#rate-limiting)
  - [Retry](#retry)
  - [Circuit Breaker](#circuit-breaker)
  - [Timeout](#timeout)
  - [Complete Example](#complete-openapi-example)
- [Generated Output](#generated-output)
  - [Project Structure](#project-structure)
  - [Generated Code Examples](#generated-code-examples)
- [Configuration Files](#configuration-files)
- [Environment Variables](#environment-variables)
- [Docker Support](#docker-support)

---

## Key Features

- **Spec-Driven Resilience** — Define rate limits, retries, and circuit breakers in your OpenAPI spec
- **One-Line Bootstrap** — Generated services use `FailsafeController` for clean setup
- **Telemetry Built-In** — OpenTelemetry and Prometheus integration out of the box
- **Control Plane Ready** — Dynamic configuration updates without redeployment
- **Container Ready** — Generates `Dockerfile`, `.env`, and config files
- **Drop-In Replacement** — Uses standard `openapi-generator` under the hood

---

## Requirements

- Python 3.12+
- One of:
  - `openapi-generator-cli` installed locally
  - Docker (falls back automatically)

---

## Installation

```bash
# Install via uv (recommended)
uv add failsafe-generator

# Or via pip
pip install failsafe-generator

# Verify installation
failsafe --help
```

---

## Quick Start

### 1. Create your OpenAPI spec with resilience extensions

```yaml
# product-api.yaml
openapi: 3.1.0
info:
  title: Product Service
  version: 1.0.0

paths:
  /products/{product_id}:
    get:
      operationId: get_product
      x-ratelimit:
        name: get_product
        max_executions: 5000
        per_time_secs: 60
        retry_after_strategy: backpressure
      responses:
        '200':
          description: OK
```

### 2. Generate your service

```bash
failsafe generate product-api.yaml \
  -o ./product-service \
  --package-name product_service \
  --app-name "Product Service"
```

### 3. Run the generated service

```bash
cd product-service
uv sync
uvicorn main:app --reload --port 8000
```

Your service is now running with:
- ✅ Rate limiting on `/products/{product_id}`
- ✅ OpenTelemetry metrics export
- ✅ Control plane integration
- ✅ Exception handlers for 429/503/504

---

## CLI Reference

```bash
failsafe generate <spec> [OPTIONS]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `spec` | Path to OpenAPI spec file (YAML or JSON) |

### Options

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

### Examples

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

# Egress protection only (for gateway services)
failsafe generate openapi.yaml --protection-type EGRESS

# Full protection (both ingress and egress)
failsafe generate openapi.yaml --protection-type FULL

# Use Prometheus instead of OTEL
failsafe generate openapi.yaml --telemetry PROMETHEUS
```

---

## OpenAPI Vendor Extensions

Define resilience patterns directly in your OpenAPI specification using vendor extensions.

### Supported Extension Formats

The generator supports two extension formats:

| Format | Example | Use Case |
|--------|---------|----------|
| **Direct** | `x-ratelimit`, `x-retry` | Simple, one pattern per operation |
| **Namespaced** | `x-telstra.resiliency.ratelimit` | Multiple patterns, organization-wide standards |

---

### Global Configuration

Configure service-wide settings at the root level:

```yaml
openapi: 3.1.0
info:
  title: My Service
  version: 1.0.0

# Global Failsafe configuration
x-failsafe:
  telemetry:
    enabled: true
    type: otel
    endpoint: http://otel-collector:4318/v1/metrics
  controlplane:
    enabled: true
    url: http://failsafe-controlplane:8080
  protection:
    type: ingress

# Or using custom namespace
x-telstra:
  otel:
    enabled: true
  controller:
    enabled: true
```

---

### Rate Limiting

Protect endpoints from excessive requests using token bucket rate limiting.

#### Direct Extension (`x-ratelimit`)

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
        min_latency: 0.001
        min_retry_delay: 0.01
        max_retry_penalty: 1.0
        gradient_sensitivity: 10.0
      responses:
        '200':
          description: OK
```

#### Namespaced Extension (`x-telstra`)

```yaml
paths:
  /products:
    get:
      operationId: list_products
      x-telstra:
        resiliency:
          ratelimit:
            enabled: true
            max_executions: 5000
            per_time_secs: 60
            bucket_size: 500
            p95_baseline: 1.0
            min_latency: 0.001
      responses:
        '200':
          description: OK
```

#### Rate Limit Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `string` | `operationId` | Identifier for metrics |
| `enabled` | `boolean` | `true` | Enable/disable rate limiting |
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
    min_retry_delay=0.01,
    max_retry_penalty=1.0,
    gradient_sensitivity=10.0,
)
async def list_products(request: Request) -> List[Product]:
    ...
```

---

### Retry

Automatically retry failed operations with exponential backoff.

#### Direct Extension (`x-retry`)

```yaml
paths:
  /orders:
    post:
      operationId: create_order
      x-retry:
        name: create_order
        attempts: 3
        delay: 0.5
        backoff: 2.0
        max_delay: 30.0
        exceptions:
          - ConnectionError
          - TimeoutError
          - HTTPStatusError
      responses:
        '200':
          description: OK
```

#### Namespaced Extension

```yaml
paths:
  /orders:
    post:
      operationId: create_order
      x-telstra:
        resiliency:
          retry:
            enabled: true
            attempts: 3
            delay: 0.5
            backoff: 2.0
      responses:
        '200':
          description: OK
```

#### Retry Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `string` | `operationId` | Identifier for metrics |
| `enabled` | `boolean` | `true` | Enable/disable retry |
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
    max_delay=30.0,
    exceptions=(ConnectionError, TimeoutError),
)
async def create_order(request: Request, order: OrderCreate) -> Order:
    ...
```

---

### Circuit Breaker

Prevent cascading failures by stopping calls to failing services.

#### Direct Extension (`x-circuitbreaker`)

```yaml
paths:
  /payments:
    post:
      operationId: process_payment
      x-circuitbreaker:
        name: payment_gateway
        failure_threshold: 5
        recovery_timeout: 30
        half_open_requests: 3
      responses:
        '200':
          description: OK
```

#### Namespaced Extension

```yaml
paths:
  /payments:
    post:
      operationId: process_payment
      x-telstra:
        resiliency:
          circuitbreaker:
            enabled: true
            failure_threshold: 5
            recovery_timeout: 30
      responses:
        '200':
          description: OK
```

#### Circuit Breaker Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `string` | `operationId` | Identifier for metrics |
| `enabled` | `boolean` | `true` | Enable/disable circuit breaker |
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
    half_open_requests=3,
)
async def process_payment(request: Request, payment: PaymentRequest) -> Payment:
    ...
```

---

### Timeout

Bound execution time for operations.

#### Direct Extension (`x-timeout`)

```yaml
paths:
  /reports:
    get:
      operationId: generate_report
      x-timeout:
        name: report_generation
        seconds: 30.0
      responses:
        '200':
          description: OK
```

#### Timeout Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
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
@tokenbucket(
    name="create_order",
    max_executions=1000,
    per_time_secs=60,
)
@circuitbreaker(
    name="create_order_circuit",
    failure_threshold=5,
)
@retry(
    name="create_order_retry",
    attempts=3,
    delay=0.5,
)
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

# Global configuration
x-telstra:
  otel:
    enabled: true
  controller:
    enabled: true

servers:
  - url: "http://0.0.0.0:8001"
    description: Local development server

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
      x-ratelimit:
        name: create_inventory
        max_executions: 1000
        per_time_secs: 60
        retry_after_strategy: backpressure
      x-retry:
        name: create_inventory_retry
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
      x-circuitbreaker:
        name: inventory_delete
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
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time

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
        low_stock_threshold:
          type: integer
          minimum: 0
          default: 10

    StockAdjustment:
      type: object
      required:
        - amount
      properties:
        amount:
          type: integer
          description: Positive to add, negative to remove
```

---

## Generated Output

### Project Structure

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
└── inventory_service/
    ├── __init__.py
    ├── settings.py            # Pydantic settings
    ├── apis/
    │   ├── __init__.py
    │   ├── inventories_api.py # Generated routes with decorators
    │   └── products_api.py
    └── models/
        ├── __init__.py
        ├── inventory.py
        └── inventory_request.py
```

### Generated Code Examples

#### `main.py`

```python
# coding: utf-8
"""
Inventory Service

Generated by failsafe-generator
"""

from fastapi import FastAPI

from failsafe import FailsafeController, Telemetry, Protection

from inventory_service.apis.inventories_api import router as InventoriesApiRouter
from inventory_service.apis.products_api import router as ProductsApiRouter

app = FastAPI(
    title="Inventory Service",
    description="Inventory management API",
    version="0.1.0",
)

# Failsafe Resilience Bootstrap
FailsafeController(app, service_name="inventory_service") \
    .with_telemetry(
        Telemetry.OTEL,
        endpoint="http://otel-collector:4318/v1/metrics",
    ) \
    .with_protection(Protection.INGRESS) \
    .with_controlplane(
        url="http://failsafe-controlplane:8080",
    )

app.include_router(InventoriesApiRouter)
app.include_router(ProductsApiRouter)
```

#### `apis/inventories_api.py`

```python
# coding: utf-8
"""
Inventories API

Generated by failsafe-generator
"""

from typing import List
from fastapi import APIRouter, Request, HTTPException

from failsafe.ratelimit import tokenbucket, Strategy
from failsafe.retry import retry
from failsafe.circuitbreaker import circuitbreaker
from failsafe.timeout import timeout

from ..models import Inventory, InventoryRequest, StockAdjustment

router = APIRouter(prefix="/inventories", tags=["inventories"])


@router.get("", response_model=List[Inventory])
@tokenbucket(
    name="get_inventories",
    max_executions=5000,
    per_time_secs=60,
    retry_after_strategy=Strategy.BACKPRESSURE,
    p95_baseline=0.5,
    min_latency=0.01,
)
async def get_inventories(request: Request) -> List[Inventory]:
    """Get Inventories"""
    # TODO: Implement business logic
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("", response_model=Inventory)
@tokenbucket(
    name="create_inventory",
    max_executions=1000,
    per_time_secs=60,
    retry_after_strategy=Strategy.BACKPRESSURE,
)
@retry(
    name="create_inventory_retry",
    attempts=3,
    delay=0.5,
    backoff=2.0,
)
async def create_inventory(
    request: Request,
    inventory_request: InventoryRequest,
) -> Inventory:
    """Create Inventory"""
    # TODO: Implement business logic
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/{inventory_id}", response_model=Inventory)
@tokenbucket(
    name="get_inventory",
    max_executions=5000,
    per_time_secs=60,
    retry_after_strategy=Strategy.BACKPRESSURE,
)
@timeout(name="get_inventory_timeout", seconds=5.0)
async def get_inventory(
    request: Request,
    inventory_id: str,
) -> Inventory:
    """Get Inventory"""
    # TODO: Implement business logic
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/{inventory_id}")
@circuitbreaker(
    name="inventory_delete",
    failure_threshold=3,
    recovery_timeout=60,
)
async def delete_inventory(
    request: Request,
    inventory_id: str,
):
    """Delete Inventory"""
    # TODO: Implement business logic
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/{inventory_id}/stock", response_model=Inventory)
@tokenbucket(
    name="adjust_stock",
    max_executions=2000,
    per_time_secs=60,
    retry_after_strategy=Strategy.BACKPRESSURE,
    p95_baseline=0.2,
    min_latency=0.05,
)
@retry(
    name="adjust_stock_retry",
    attempts=3,
    delay=1.0,
)
async def adjust_stock(
    request: Request,
    inventory_id: str,
    stock_adjustment: StockAdjustment,
) -> Inventory:
    """Adjust Stock"""
    # TODO: Implement business logic
    raise HTTPException(status_code=501, detail="Not implemented")
```

---

## Configuration Files

### `.env`

```bash
SERVICE_NAME=inventory-service
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318/v1/metrics
FAILSAFE_CONTROLPLANE_URL=http://failsafe-controlplane:8080
FAILSAFE_ENABLED=true
```

### `.config/otel-config.yaml`

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:

exporters:
  prometheus:
    endpoint: "0.0.0.0:8889"

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [prometheus]
```

### `.config/prometheus.yml`

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'otel-collector'
    static_configs:
      - targets: ['otel-collector:8889']
  
  - job_name: 'inventory-service'
    static_configs:
      - targets: ['inventory-service:8000']
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVICE_NAME` | App title | Service identifier |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318/v1/metrics` | OTLP endpoint |
| `OTEL_SERVICE_NAME` | `SERVICE_NAME` | OTEL service name |
| `FAILSAFE_CONTROLPLANE_URL` | `http://localhost:8080` | Control plane URL |
| `FAILSAFE_ENABLED` | `true` | Enable/disable Failsafe |

---

## Docker Support

### Generated Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Build and Run

```bash
# Build
docker build -t inventory-service:latest .

# Run
docker run -p 8000:8000 \
  -e OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318/v1/metrics \
  inventory-service:latest
```

### Docker Compose

```yaml
version: '3.8'

services:
  inventory-service:
    build: .
    ports:
      - "8000:8000"
    environment:
      - SERVICE_NAME=inventory-service
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318/v1/metrics
      - FAILSAFE_CONTROLPLANE_URL=http://controlplane:8080
    depends_on:
      - otel-collector

  otel-collector:
    image: otel/opentelemetry-collector:latest
    volumes:
      - ./.config/otel-config.yaml:/etc/otel-config.yaml
    command: ["--config", "/etc/otel-config.yaml"]
    ports:
      - "4318:4318"
      - "8889:8889"

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./.config/prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"
```

---

## Acknowledgements

- [openapi-generator](https://github.com/OpenAPITools/openapi-generator) — Core code generation
- [failsafe-lib/failsafe](https://github.com/failsafe-lib/failsafe) — Java resilience patterns inspiration
- [FastAPI](https://fastapi.tiangolo.com/) — Modern Python web framework

---

<p align="center">
  <em>From spec to resilient service — resilience-as-code, automated.</em>
</p>