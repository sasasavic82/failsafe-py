# Makefile — uv-based workflow + local OpenTelemetry Collector

SOURCE ?= failsafe docs/snippets
TESTS  ?= tests

OTEL_NAME ?= otelcol-failsafe
OTEL_IMG  ?= otel/opentelemetry-collector:latest
OTEL_DIR  ?= .otel
OTEL_CFG  ?= $(OTEL_DIR)/collector.yaml
# Ports: OTLP gRPC 4317, OTLP HTTP 4318
OTEL_PORTS ?= -p 4317:4317 -p 4318:4318

.PHONY: help install install-dev clean lint-check lint package-build docs-serve docs-build build \
        test test-meta test-meta-results test-cov-xml test-cov-html test-cov-open \
        otel-init otel-up otel-down otel-restart otel-logs

help: ## List targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "%-28s %s\n", $$1, $$2}'

install: ## Install default dependencies (creates .venv and syncs)
	@uv sync

install-dev: ## Install all dependency groups (dev/docs/etc)
	@uv sync --all-groups

clean: ## Clean build, cache, coverage artifacts
	@rm -rf dist build .mypy_cache .pytest_cache .ruff_cache
	@rm -rf .coverage htmlcov coverage.xml .mutmut-cache site

lint-check: ## Lint without changes (ruff, black --check, mypy)
	@uv run ruff $(SOURCE) $(TESTS)
	@uv run black --check $(SOURCE) $(TESTS)
	@uv run mypy --pretty $(SOURCE) $(TESTS)

lint: ## Auto-fix and type-check
	@uv run ruff --fix $(SOURCE) $(TESTS)
	@uv run black $(SOURCE) $(TESTS)
	@uv run mypy --pretty $(SOURCE) $(TESTS)

package-build: ## Build wheel/sdist with uv
	@uv build

docs-serve: ## Serve docs with autoreload
	@uv run mkdocs serve

docs-build: ## Build docs
	@uv run mkdocs build

build: package-build docs-build ## Build package and docs

test: ## Run tests with coverage
	@uv run coverage run -m pytest $(TESTS) $(SOURCE)

test-meta: ## Mutation tests
	@uv run mutmut run

test-meta-results: ## Mutation test results
	@uv run mutmut results

test-cov-xml: ## Coverage XML
	@uv run coverage run -m pytest $(TESTS) --cov $(SOURCE) --cov-report=xml

test-cov-html: ## Coverage HTML
	@uv run coverage run -m pytest $(TESTS) --cov $(SOURCE) --cov-report=html
	@uv run coverage report --show-missing

test-cov-open: test-cov-html ## Open HTML coverage
	@open htmlcov/index.html

# -----------------------------
# OpenTelemetry Collector (local)
# -----------------------------

otel-init: ## Write minimal OTLP collector config to .otel/collector.yaml
	@mkdir -p $(OTEL_DIR)
	@test -f $(OTEL_CFG) || { \
		echo "receivers:"                                  >  $(OTEL_CFG); \
		echo "  otlp:"                                     >> $(OTEL_CFG); \
		echo "    protocols:"                              >> $(OTEL_CFG); \
		echo "      grpc:"                                 >> $(OTEL_CFG); \
		echo "      http:"                                 >> $(OTEL_CFG); \
		echo ""                                            >> $(OTEL_CFG); \
		echo "processors:"                                 >> $(OTEL_CFG); \
		echo "  batch:"                                    >> $(OTEL_CFG); \
		echo ""                                            >> $(OTEL_CFG); \
		echo "exporters:"                                  >> $(OTEL_CFG); \
		echo "  logging:"                                  >> $(OTEL_CFG); \
		echo "    loglevel: debug"                         >> $(OTEL_CFG); \
		echo ""                                            >> $(OTEL_CFG); \
		echo "extensions:"                                 >> $(OTEL_CFG); \
		echo "  health_check:"                             >> $(OTEL_CFG); \
		echo ""                                            >> $(OTEL_CFG); \
		echo "service:"                                    >> $(OTEL_CFG); \
		echo "  extensions: [health_check]"                >> $(OTEL_CFG); \
		echo "  pipelines:"                                >> $(OTEL_CFG); \
		echo "    metrics:"                                >> $(OTEL_CFG); \
		echo "      receivers: [otlp]"                     >> $(OTEL_CFG); \
		echo "      processors: [batch]"                   >> $(OTEL_CFG); \
		echo "      exporters: [logging]"                  >> $(OTEL_CFG); \
		echo "    traces:"                                 >> $(OTEL_CFG); \
		echo "      receivers: [otlp]"                     >> $(OTEL_CFG); \
		echo "      processors: [batch]"                   >> $(OTEL_CFG); \
		echo "      exporters: [logging]"                  >> $(OTEL_CFG); \
	}

otel-up: otel-init ## Run OpenTelemetry Collector (OTLP gRPC/HTTP → logging)
	@docker rm -f $(OTEL_NAME) >/dev/null 2>&1 || true
	@docker run --name $(OTEL_NAME) $(OTEL_PORTS) -v $(PWD)/$(OTEL_CFG):/etc/otelcol/config.yaml:ro \
		$(OTEL_IMG) --config=/etc/otelcol/config.yaml

otel-down: ## Stop OpenTelemetry Collector
	@docker rm -f $(OTEL_NAME) >/dev/null 2>&1 || true

otel-restart: otel-down otel-up ## Restart OpenTelemetry Collector

otel-logs: ## Tail collector logs
	@docker logs -f $(OTEL_NAME)
