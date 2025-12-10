"""
Failsafe Controller - One-line resilience bootstrap for FastAPI applications.

The controller provides:
    - Fluent API for quick bootstrap (.with_telemetry(), .with_protection(), .with_controlplane())
    - Embedded control plane REST APIs for runtime management
    - Pattern registry and metrics collection
    - Dynamic configuration updates

Usage:
    from fastapi import FastAPI
    from failsafe import FailsafeController, Telemetry, Protection

    app = FastAPI()

    FailsafeController(app) \\
        .with_telemetry(Telemetry.OTEL) \\
        .with_protection(Protection.INGRESS) \\
        .with_controlplane()
"""

from __future__ import annotations

import asyncio
import os
import weakref
from collections import defaultdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from fastapi import FastAPI
    from opentelemetry.sdk.metrics import MeterProvider


# ============================================================================
# Enums
# ============================================================================

class Telemetry(str, Enum):
    """Telemetry backend options."""
    OTEL = "otel"
    PROMETHEUS = "prometheus"
    NONE = "none"


class Protection(str, Enum):
    """Protection type options."""
    INGRESS = "ingress"      # Rate limiting on incoming requests
    EGRESS = "egress"        # Resilience on outgoing requests
    FULL = "full"            # Both ingress and egress


# ============================================================================
# Global Registry and Stores
# ============================================================================

_PATTERN_REGISTRY: Dict[str, Dict[str, Any]] = defaultdict(dict)
_METRICS_STORE: Dict[str, Dict[str, Any]] = defaultdict(lambda: defaultdict(int))
_CONFIG_STORE: Dict[str, Dict[str, Any]] = {}
_DEFAULT_CONFIGS: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# Pydantic Models for Control Plane API
# ============================================================================

class PatternConfig(BaseModel):
    """Generic pattern configuration"""
    pattern_type: str
    name: str
    enabled: bool = True
    parameters: Dict[str, Any] = Field(default_factory=dict)


class RetryConfig(BaseModel):
    """Retry pattern configuration"""
    attempts: Optional[int] = 3
    backoff: float = 0.5
    enabled: bool = True


class RateLimitConfig(BaseModel):
    """Rate limiter configuration"""
    max_executions: float
    per_time_secs: float
    bucket_size: Optional[float] = None
    enabled: bool = True


class TimeoutConfig(BaseModel):
    """Timeout pattern configuration"""
    seconds: float
    enabled: bool = True


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration"""
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: float = 60.0
    enabled: bool = True


class BulkheadConfig(BaseModel):
    """Bulkhead pattern configuration"""
    max_concurrent: int = 10
    max_waiting: int = 10
    enabled: bool = True


class MetricsResponse(BaseModel):
    """Response model for metrics"""
    pattern_type: str
    name: str
    metrics: Dict[str, Any]
    timestamp: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: str
    patterns_active: int
    version: str = "1.0.0"


# ============================================================================
# Pattern Registry
# ============================================================================

class PatternRegistry:
    """
    Central registry for all pattern instances.
    Uses weak references to avoid memory leaks.
    """
    
    def __init__(self):
        self._patterns: Dict[str, weakref.WeakSet] = defaultdict(weakref.WeakSet)
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    def register(self, pattern_type: str, name: str, manager: Any, metadata: Optional[Dict] = None):
        """Register a pattern instance"""
        key = f"{pattern_type}:{name}"
        self._patterns[pattern_type].add(manager)
        self._metadata[key] = {
            "name": name,
            "pattern_type": pattern_type,
            "manager": manager,
            "registered_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        
        # Store in global registry for API access
        _PATTERN_REGISTRY[pattern_type][name] = {
            "manager": manager,
            "metadata": metadata or {},
            "registered_at": datetime.utcnow().isoformat()
        }
    
    def get_pattern(self, pattern_type: str, name: str) -> Optional[Any]:
        """Get a specific pattern instance"""
        key = f"{pattern_type}:{name}"
        meta = self._metadata.get(key)
        return meta["manager"] if meta else None
    
    def list_patterns(self, pattern_type: Optional[str] = None) -> Dict[str, List[str]]:
        """List all registered patterns"""
        if pattern_type:
            return {pattern_type: list(_PATTERN_REGISTRY.get(pattern_type, {}).keys())}
        
        return {
            ptype: list(patterns.keys())
            for ptype, patterns in _PATTERN_REGISTRY.items()
        }
    
    def get_all_patterns(self) -> List[Dict[str, Any]]:
        """Get all pattern instances with metadata"""
        patterns = []
        for pattern_type, instances in _PATTERN_REGISTRY.items():
            for name, data in instances.items():
                patterns.append({
                    "pattern_type": pattern_type,
                    "name": name,
                    "registered_at": data.get("registered_at"),
                    "metadata": data.get("metadata", {})
                })
        return patterns


# ============================================================================
# Metrics Collector
# ============================================================================

class MetricsCollector:
    """
    Lightweight metrics collector for pattern performance.
    Integrates with existing event system.
    """
    
    def __init__(self):
        self._metrics: Dict[str, Dict[str, Any]] = defaultdict(lambda: defaultdict(int))
        self._lock = asyncio.Lock()
    
    async def increment(self, pattern_type: str, name: str, metric: str, value: int = 1):
        """Increment a metric counter"""
        async with self._lock:
            key = f"{pattern_type}:{name}"
            self._metrics[key][metric] += value
            self._metrics[key]["last_updated"] = datetime.utcnow().isoformat()
    
    async def set_gauge(self, pattern_type: str, name: str, metric: str, value: Any):
        """Set a gauge metric"""
        async with self._lock:
            key = f"{pattern_type}:{name}"
            self._metrics[key][metric] = value
            self._metrics[key]["last_updated"] = datetime.utcnow().isoformat()
    
    def get_metrics(self, pattern_type: str, name: str) -> Dict[str, Any]:
        """Get metrics for a specific pattern"""
        key = f"{pattern_type}:{name}"
        return dict(self._metrics.get(key, {}))
    
    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get all metrics"""
        return {k: dict(v) for k, v in self._metrics.items()}
    
    def reset_metrics(self, pattern_type: str, name: str):
        """Reset metrics for a pattern"""
        key = f"{pattern_type}:{name}"
        if key in self._metrics:
            self._metrics[key].clear()


# ============================================================================
# Configuration Manager
# ============================================================================

class ConfigManager:
    """Manages configuration loading and updates"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("failsafe.yaml")
        self._configs: Dict[str, Dict[str, Any]] = {}
    
    def load_config(self) -> Dict[str, Dict[str, Any]]:
        """Load configuration from YAML file"""
        if not self.config_path.exists():
            return {}
        
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
                self._configs = config or {}
                
                # Store in global default configs
                global _DEFAULT_CONFIGS
                _DEFAULT_CONFIGS = self._configs.copy()
                
                return self._configs
        except Exception as e:
            print(f"Warning: Failed to load config from {self.config_path}: {e}")
            return {}
    
    def get_pattern_config(self, pattern_type: str, name: str) -> Dict[str, Any]:
        """Get configuration for a specific pattern"""
        pattern_configs = self._configs.get(pattern_type, {})
        
        # Try exact match first
        if name in pattern_configs:
            return pattern_configs[name]
        
        # Try default config
        if "default" in pattern_configs:
            return pattern_configs["default"]
        
        return {}
    
    def update_pattern_config(self, pattern_type: str, name: str, config: Dict[str, Any]):
        """Update pattern configuration at runtime"""
        if pattern_type not in self._configs:
            self._configs[pattern_type] = {}
        
        self._configs[pattern_type][name] = config
        
        # Store in global config store
        key = f"{pattern_type}:{name}"
        _CONFIG_STORE[key] = config
    
    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_path, 'w') as f:
                yaml.dump(self._configs, f, default_flow_style=False)
        except Exception as e:
            print(f"Warning: Failed to save config to {self.config_path}: {e}")


# ============================================================================
# Control Plane Listeners (for event system integration)
# ============================================================================

class ControlPlaneListener:
    """
    Base listener that collects metrics from pattern events.
    Each pattern type should have a specific implementation.
    """
    
    def __init__(self, pattern_type: str, name: str, collector: MetricsCollector):
        self.pattern_type = pattern_type
        self.name = name
        self.collector = collector


class RetryControlPlaneListener(ControlPlaneListener):
    """Listener for retry pattern metrics"""
    
    async def on_retry(self, retry, exception: Exception, counter, backoff: float):
        await self.collector.increment(self.pattern_type, self.name, "attempts")
        await self.collector.increment(self.pattern_type, self.name, "retries")
    
    async def on_attempts_exceeded(self, retry):
        await self.collector.increment(self.pattern_type, self.name, "failures")
        await self.collector.increment(self.pattern_type, self.name, "attempts_exceeded")
    
    async def on_success(self, retry, counter):
        await self.collector.increment(self.pattern_type, self.name, "successes")
        await self.collector.set_gauge(self.pattern_type, self.name, "last_attempt_count", counter.current_attempt)


class RateLimitControlPlaneListener(ControlPlaneListener):
    """Listener for rate limit pattern metrics"""
    
    def __init__(self, pattern_type: str, name: str, collector: MetricsCollector, manager=None):
        super().__init__(pattern_type, name, collector)
        self._manager = manager
    
    async def on_acquire(self):
        """Called when a token is successfully acquired"""
        await self.collector.increment(self.pattern_type, self.name, "requests")
        
        # Update gauge for current tokens if manager available
        if self._manager and hasattr(self._manager, 'current_tokens'):
            await self.collector.set_gauge(
                self.pattern_type,
                self.name,
                "tokens_available",
                self._manager.current_tokens
            )
    
    async def on_throttle(self):
        """Called when rate limit is hit (EmptyBucket/RateLimitExceeded)"""
        await self.collector.increment(self.pattern_type, self.name, "throttled")
        await self.collector.increment(self.pattern_type, self.name, "rejections")


# Global instances
_REGISTRY = PatternRegistry()
_METRICS = MetricsCollector()


# ============================================================================
# FailsafeController - Main Controller Class
# ============================================================================

class FailsafeController:
    """
    Fluent API for bootstrapping Failsafe resilience patterns in FastAPI.
    
    Provides:
        - Quick bootstrap via method chaining
        - Embedded control plane REST APIs
        - Telemetry setup (OTEL, Prometheus)
        - Protection handlers (ingress/egress)
    
    Example:
        app = FastAPI()
        
        FailsafeController(app) \\
            .with_telemetry(Telemetry.OTEL) \\
            .with_protection(Protection.INGRESS) \\
            .with_controlplane()
    
    This single chain:
        - Sets up OpenTelemetry metrics export
        - Registers all exception handlers (429, 503, 504, etc.)
        - Adds rate limit info middleware
        - Mounts control plane REST APIs at /failsafe/*
    """
    
    def __init__(
        self,
        app: "FastAPI",
        *,
        service_name: Optional[str] = None,
        namespace: str = "failsafe",
        config_path: Optional[Path] = None,
    ) -> None:
        """
        Initialize the Failsafe controller.
        
        Args:
            app: FastAPI application instance
            service_name: Service name for telemetry (defaults to app.title or env var)
            namespace: Metric namespace prefix (default: "failsafe")
            config_path: Path to failsafe.yaml config file
        """
        self.app = app
        self.service_name = service_name or self._resolve_service_name()
        self.namespace = namespace
        self._meter_provider: Optional["MeterProvider"] = None
        self._telemetry_type: Telemetry = Telemetry.NONE
        self._protection_type: Optional[Protection] = None
        self._controlplane_enabled: bool = False
        self._controlplane_prefix: str = "/failsafe"
        
        # Control plane components
        self.config_manager = ConfigManager(config_path)
        self.registry = _REGISTRY
        self.metrics = _METRICS
        
        # Load configuration at initialization
        self.config_manager.load_config()
    
    def _resolve_service_name(self) -> str:
        """Resolve service name from app title or environment."""
        if name := os.environ.get("SERVICE_NAME"):
            return name
        if name := os.environ.get("OTEL_SERVICE_NAME"):
            return name
        if hasattr(self.app, "title") and self.app.title:
            return self.app.title.lower().replace(" ", "-")
        return "failsafe-service"
    
    # ========================================================================
    # Fluent API Methods
    # ========================================================================
    
    def with_telemetry(
        self,
        telemetry_type: Telemetry = Telemetry.OTEL,
        *,
        endpoint: Optional[str] = None,
        export_interval_ms: int = 10000,
        timeout: int = 5,
    ) -> "FailsafeController":
        """
        Configure telemetry and metrics export.
        
        Args:
            telemetry_type: Backend type (OTEL, PROMETHEUS, NONE)
            endpoint: Export endpoint (defaults to env var or localhost)
            export_interval_ms: How often to export metrics (default: 10s)
            timeout: Export timeout in seconds
        
        Returns:
            Self for method chaining
        """
        self._telemetry_type = telemetry_type
        
        if telemetry_type == Telemetry.OTEL:
            self._setup_otel(
                endpoint=endpoint,
                export_interval_ms=export_interval_ms,
                timeout=timeout,
            )
        elif telemetry_type == Telemetry.PROMETHEUS:
            self._setup_prometheus()
        
        return self
    
    def _setup_otel(
        self,
        endpoint: Optional[str] = None,
        export_interval_ms: int = 10000,
        timeout: int = 5,
    ) -> None:
        """Configure OpenTelemetry metrics export."""
        try:
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.metrics import set_meter_provider
            from failsafe.integrations.opentelemetry import FailsafeOtelInstrumentor
        except ImportError as e:
            raise ImportError(
                "OpenTelemetry dependencies not installed. "
                "Install with: pip install failsafe[otel]"
            ) from e
        
        otel_endpoint = endpoint or os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "http://localhost:4318/v1/metrics"
        )
        
        resource = Resource.create({
            "service.name": self.service_name,
            "service.namespace": self.namespace,
        })
        
        exporter = OTLPMetricExporter(endpoint=otel_endpoint, timeout=timeout)
        reader = PeriodicExportingMetricReader(exporter, export_interval_millis=export_interval_ms)
        
        self._meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        set_meter_provider(self._meter_provider)
        
        FailsafeOtelInstrumentor().instrument(
            namespace=f"{self.namespace}.{self.service_name}",
            meter_provider=self._meter_provider,
        )
    
    def _setup_prometheus(self) -> None:
        """Configure Prometheus metrics endpoint."""
        try:
            from prometheus_fastapi_instrumentator import Instrumentator
        except ImportError as e:
            raise ImportError(
                "Prometheus dependencies not installed. "
                "Install with: pip install failsafe[prometheus]"
            ) from e
        
        Instrumentator().instrument(
            self.app,
            metric_namespace=self.namespace,
            metric_subsystem=self.service_name.replace("-", "_"),
        ).expose(self.app)
    
    def with_protection(
        self,
        protection_type: Protection = Protection.INGRESS,
        *,
        add_headers: bool = True,
        log_rejections: bool = True,
    ) -> "FailsafeController":
        """
        Configure protection handlers and middleware.
        
        Args:
            protection_type: Type of protection (INGRESS, EGRESS, FULL)
            add_headers: Add RateLimit-* headers to responses
            log_rejections: Log rate limit rejections
        
        Returns:
            Self for method chaining
        """
        self._protection_type = protection_type
        
        if protection_type in (Protection.INGRESS, Protection.FULL):
            self._setup_ingress_protection(add_headers=add_headers, log_rejections=log_rejections)
        
        if protection_type in (Protection.EGRESS, Protection.FULL):
            self._setup_egress_protection()
        
        return self
    
    def _setup_ingress_protection(self, add_headers: bool = True, log_rejections: bool = True) -> None:
        """Configure ingress protection (rate limiting)."""
        from fastapi import Request
        from fastapi.responses import JSONResponse
        from failsafe.ratelimit.exceptions import RateLimitExceeded, EmptyBucket
        
        @self.app.exception_handler(RateLimitExceeded)
        async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
            retry_after_secs = exc.retry_after_ms / 1000
            
            if log_rejections:
                client_id = getattr(exc, "client_id", None) or _get_client_id(request)
                print(f"[RATE_LIMIT] Rejected {request.method} {request.url.path} "
                      f"client={client_id} retry_after={retry_after_secs:.2f}s")
            
            headers = {
                "Retry-After": str(int(retry_after_secs + 0.5)),
                "X-RateLimit-Retry-After-Ms": str(int(exc.retry_after_ms)),
            }
            
            if hasattr(request.state, "endpoint_limiter"):
                limiter = request.state.endpoint_limiter
                client_id = getattr(request.state, "client_id", None)
                bp = limiter.get_backpressure(client_id=client_id)
                if bp is not None:
                    headers["X-Backpressure"] = f"{bp:.3f}"
            
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded. Retry after {exc.retry_after_ms}ms",
                    "retry_after_seconds": retry_after_secs,
                    "retry_after_ms": exc.retry_after_ms,
                },
                headers=headers,
            )
        
        @self.app.exception_handler(EmptyBucket)
        async def empty_bucket_handler(request: Request, exc: EmptyBucket):
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limit_exceeded", "message": "Rate limit exceeded"},
                headers={"Retry-After": "1"},
            )
        
        if add_headers:
            @self.app.middleware("http")
            async def rate_limit_info_middleware(request: Request, call_next):
                response = await call_next(request)
                
                if hasattr(request.state, "endpoint_limiter"):
                    limiter = request.state.endpoint_limiter
                    if hasattr(limiter, "_limiter"):
                        bucket = limiter._limiter
                        response.headers["RateLimit-Limit"] = str(int(bucket.max_executions))
                        response.headers["RateLimit-Remaining"] = str(int(bucket.current_tokens))
                    
                    client_id = getattr(request.state, "client_id", None)
                    bp = limiter.get_backpressure(client_id=client_id)
                    if bp is not None:
                        response.headers["X-Backpressure"] = f"{bp:.3f}"
                
                return response
    
    def _setup_egress_protection(self) -> None:
        """Configure egress protection (retry, circuit breaker, etc.)."""
        from fastapi import Request
        from fastapi.responses import JSONResponse
        
        try:
            from failsafe.retry.exceptions import AttemptsExceeded
            
            @self.app.exception_handler(AttemptsExceeded)
            async def retry_exhausted_handler(request: Request, exc: AttemptsExceeded):
                return JSONResponse(
                    status_code=503,
                    content={"error": "service_unavailable", "message": "All retry attempts failed"},
                    headers={"Retry-After": "60"},
                )
        except ImportError:
            pass
        
        try:
            from failsafe.circuitbreaker import CircuitBreakerOpen
            
            @self.app.exception_handler(CircuitBreakerOpen)
            async def circuit_breaker_handler(request: Request, exc: CircuitBreakerOpen):
                return JSONResponse(
                    status_code=503,
                    content={"error": "circuit_breaker_open", "message": "Circuit breaker open"},
                    headers={"Retry-After": "30"},
                )
        except ImportError:
            pass
        
        try:
            from failsafe.bulkhead import BulkheadFull
            
            @self.app.exception_handler(BulkheadFull)
            async def bulkhead_handler(request: Request, exc: BulkheadFull):
                return JSONResponse(
                    status_code=503,
                    content={"error": "bulkhead_full", "message": "Concurrency limit reached"},
                    headers={"Retry-After": "5"},
                )
        except ImportError:
            pass
        
        try:
            from failsafe.timeout import TimeoutError as FsTimeoutError
            
            @self.app.exception_handler(FsTimeoutError)
            async def timeout_handler(request: Request, exc: FsTimeoutError):
                return JSONResponse(
                    status_code=504,
                    content={"error": "timeout", "message": "Operation timed out"},
                )
        except ImportError:
            pass
    
    def with_controlplane(
        self,
        *,
        prefix: str = "/failsafe",
        enable_metrics: bool = True,
        enable_control: bool = True,
    ) -> "FailsafeController":
        """
        Mount the control plane REST APIs on this service.
        
        This adds endpoints to the FastAPI app for:
            - Health/liveness checks
            - Pattern discovery and management
            - Dynamic configuration updates
            - Metrics querying
        
        Args:
            prefix: URL prefix for control plane endpoints (default: /failsafe)
            enable_metrics: Enable metrics endpoints
            enable_control: Enable control endpoints (config updates, enable/disable)
        
        Returns:
            Self for method chaining
        
        Endpoints added:
            GET  {prefix}/health              - Health check
            GET  {prefix}/liveness            - Liveness probe
            GET  {prefix}/patterns            - List all patterns
            GET  {prefix}/config              - Get all configs
            GET  {prefix}/config/{type}/{name} - Get pattern config
            PUT  {prefix}/config/{type}/{name} - Update pattern config
            GET  {prefix}/metrics             - Get all metrics
            GET  {prefix}/metrics/{type}/{name} - Get pattern metrics
            POST {prefix}/control/{type}/{name}/enable  - Enable pattern
            POST {prefix}/control/{type}/{name}/disable - Disable pattern
        """
        self._controlplane_enabled = True
        self._controlplane_prefix = prefix
        
        self._register_controlplane_routes(
            prefix=prefix,
            enable_metrics=enable_metrics,
            enable_control=enable_control,
        )
        
        self._add_lifecycle_hooks()
        
        return self
    
    def _add_lifecycle_hooks(self):
        """Add startup/shutdown hooks"""
        
        @self.app.on_event("startup")
        async def startup():
            print(f"[FAILSAFE] Controller initialized")
            print(f"[FAILSAFE] Control plane mounted at: {self._controlplane_prefix}")
            print(f"[FAILSAFE] Service: {self.service_name}")
            if _DEFAULT_CONFIGS:
                print(f"[FAILSAFE] Loaded configs: {list(_DEFAULT_CONFIGS.keys())}")
        
        @self.app.on_event("shutdown")
        async def shutdown():
            print("[FAILSAFE] Controller shutting down")
    
    def _register_controlplane_routes(
        self,
        prefix: str,
        enable_metrics: bool,
        enable_control: bool,
    ) -> None:
        """Register all control plane API routes on the FastAPI app."""
        from fastapi import HTTPException
        
        # ====================================================================
        # Health and Liveness
        # ====================================================================
        
        @self.app.get(f"{prefix}/health", response_model=HealthResponse, tags=["failsafe"])
        async def health():
            """Health check endpoint"""
            patterns = self.registry.get_all_patterns()
            return HealthResponse(
                status="healthy",
                timestamp=datetime.utcnow().isoformat(),
                patterns_active=len(patterns),
            )
        
        @self.app.get(f"{prefix}/liveness", tags=["failsafe"])
        async def liveness():
            """Simple liveness check (ping)"""
            return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}
        
        # ====================================================================
        # Pattern Discovery
        # ====================================================================
        
        @self.app.get(f"{prefix}/patterns", tags=["failsafe"])
        async def list_patterns(pattern_type: Optional[str] = None):
            """List all registered patterns"""
            if pattern_type:
                patterns = self.registry.list_patterns(pattern_type)
            else:
                patterns = self.registry.get_all_patterns()
            
            return {"patterns": patterns, "timestamp": datetime.utcnow().isoformat()}
        
        # ====================================================================
        # Configuration Management
        # ====================================================================
        
        if enable_control:
            @self.app.get(f"{prefix}/config", tags=["failsafe"])
            async def get_all_configs():
                """Get all configurations"""
                return {
                    "configs": self.config_manager._configs,
                    "defaults": _DEFAULT_CONFIGS,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            
            @self.app.get(f"{prefix}/config/{{pattern_type}}/{{name}}", tags=["failsafe"])
            async def get_config(pattern_type: str, name: str):
                """Get configuration for a specific pattern"""
                config = self.config_manager.get_pattern_config(pattern_type, name)
                if not config:
                    key = f"{pattern_type}:{name}"
                    config = _CONFIG_STORE.get(key, {})
                
                return {
                    "pattern_type": pattern_type,
                    "name": name,
                    "config": config,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            
            @self.app.put(f"{prefix}/config/{{pattern_type}}/{{name}}", tags=["failsafe"])
            async def update_config(pattern_type: str, name: str, config: Dict[str, Any]):
                """Update configuration for a specific pattern"""
                pattern = self.registry.get_pattern(pattern_type, name)
                if not pattern:
                    raise HTTPException(status_code=404, detail=f"Pattern {pattern_type}:{name} not found")
                
                self.config_manager.update_pattern_config(pattern_type, name, config)
                await self._apply_config_to_pattern(pattern_type, name, pattern, config)
                
                return {
                    "pattern_type": pattern_type,
                    "name": name,
                    "config": config,
                    "status": "updated",
                    "timestamp": datetime.utcnow().isoformat(),
                }
        
        # ====================================================================
        # Metrics
        # ====================================================================
        
        if enable_metrics:
            @self.app.get(f"{prefix}/metrics", tags=["failsafe"])
            async def get_all_metrics():
                """Get all metrics"""
                return {"metrics": self.metrics.get_all_metrics(), "timestamp": datetime.utcnow().isoformat()}
            
            @self.app.get(f"{prefix}/metrics/{{pattern_type}}/{{name}}", response_model=MetricsResponse, tags=["failsafe"])
            async def get_metrics(pattern_type: str, name: str):
                """Get metrics for a specific pattern"""
                metrics = self.metrics.get_metrics(pattern_type, name)
                if not metrics:
                    raise HTTPException(status_code=404, detail=f"No metrics found for {pattern_type}:{name}")
                
                return MetricsResponse(
                    pattern_type=pattern_type,
                    name=name,
                    metrics=metrics,
                    timestamp=datetime.utcnow().isoformat(),
                )
            
            @self.app.delete(f"{prefix}/metrics/{{pattern_type}}/{{name}}", tags=["failsafe"])
            async def reset_metrics(pattern_type: str, name: str):
                """Reset metrics for a specific pattern"""
                self.metrics.reset_metrics(pattern_type, name)
                return {
                    "pattern_type": pattern_type,
                    "name": name,
                    "status": "reset",
                    "timestamp": datetime.utcnow().isoformat(),
                }
        
        # ====================================================================
        # Pattern Control (Enable/Disable)
        # ====================================================================
        
        if enable_control:
            @self.app.post(f"{prefix}/control/{{pattern_type}}/{{name}}/enable", tags=["failsafe"])
            async def enable_pattern(pattern_type: str, name: str):
                """Enable a specific pattern"""
                pattern = self.registry.get_pattern(pattern_type, name)
                if not pattern:
                    raise HTTPException(status_code=404, detail=f"Pattern {pattern_type}:{name} not found")
                
                if hasattr(pattern, '_enabled'):
                    pattern._enabled = True
                
                return {
                    "pattern_type": pattern_type,
                    "name": name,
                    "status": "enabled",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            
            @self.app.post(f"{prefix}/control/{{pattern_type}}/{{name}}/disable", tags=["failsafe"])
            async def disable_pattern(pattern_type: str, name: str):
                """Disable a specific pattern"""
                pattern = self.registry.get_pattern(pattern_type, name)
                if not pattern:
                    raise HTTPException(status_code=404, detail=f"Pattern {pattern_type}:{name} not found")
                
                if hasattr(pattern, '_enabled'):
                    pattern._enabled = False
                
                return {
                    "pattern_type": pattern_type,
                    "name": name,
                    "status": "disabled",
                    "timestamp": datetime.utcnow().isoformat(),
                }
    
    async def _apply_config_to_pattern(
        self,
        pattern_type: str,
        name: str,
        pattern: Any,
        config: Dict[str, Any],
    ) -> None:
        """Apply configuration changes to a pattern instance"""
        
        if pattern_type == "retry":
            if "attempts" in config:
                pattern._attempts = config["attempts"]
            if "backoff" in config:
                from failsafe.retry.backoffs import create_backoff
                pattern._backoff = create_backoff(config["backoff"])
        
        elif pattern_type == "ratelimit":
            limiter = pattern
            if hasattr(pattern, '_limiter'):
                limiter = pattern._limiter
            
            if hasattr(limiter, 'update_config'):
                update_params = {}
                if "max_executions" in config:
                    update_params["max_executions"] = config["max_executions"]
                if "per_time_secs" in config:
                    update_params["per_time_secs"] = config["per_time_secs"]
                if "bucket_size" in config:
                    update_params["bucket_size"] = config["bucket_size"]
                
                if update_params:
                    limiter.update_config(**update_params)
            else:
                if "max_executions" in config and hasattr(limiter, 'update_max_executions'):
                    limiter.update_max_executions(config["max_executions"])
                if "per_time_secs" in config and hasattr(limiter, 'update_per_time_secs'):
                    limiter.update_per_time_secs(config["per_time_secs"])
                if "bucket_size" in config and hasattr(limiter, 'update_bucket_size'):
                    limiter.update_bucket_size(config["bucket_size"])
        
        elif pattern_type == "circuitbreaker":
            if "failure_threshold" in config and hasattr(pattern, '_failure_threshold'):
                pattern._failure_threshold = config["failure_threshold"]
            if "timeout_seconds" in config and hasattr(pattern, '_timeout_seconds'):
                pattern._timeout_seconds = config["timeout_seconds"]
        
        elif pattern_type == "timeout":
            if "seconds" in config and hasattr(pattern, '_seconds'):
                pattern._seconds = config["seconds"]
        
        elif pattern_type == "bulkhead":
            if "max_concurrent" in config and hasattr(pattern, '_max_concurrent'):
                pattern._max_concurrent = config["max_concurrent"]


# ============================================================================
# Helper Functions for Pattern Registration
# ============================================================================

def register_pattern(pattern_type: str, name: str, manager: Any, metadata: Optional[Dict] = None):
    """
    Register a pattern instance with the global registry.
    Call this from pattern decorators.
    """
    _REGISTRY.register(pattern_type, name, manager, metadata)


def get_pattern_config(pattern_type: str, name: str) -> Dict[str, Any]:
    """
    Get configuration for a pattern from the global config store.
    Call this from pattern decorators to check for default configs.
    """
    key = f"{pattern_type}:{name}"
    if key in _CONFIG_STORE:
        return _CONFIG_STORE[key]
    
    pattern_configs = _DEFAULT_CONFIGS.get(pattern_type, {})
    
    if name in pattern_configs:
        return pattern_configs[name]
    
    if "default" in pattern_configs:
        return pattern_configs["default"]
    
    return {}


def create_control_plane_listener(pattern_type: str, name: str):
    """
    Factory function to create appropriate listener for pattern type.
    Returns a listener factory that can be used with the event system.
    """
    async def listener_factory(component):
        if pattern_type == "retry":
            return RetryControlPlaneListener(pattern_type, name, _METRICS)
        elif pattern_type == "ratelimit":
            return RateLimitControlPlaneListener(pattern_type, name, _METRICS, component)
        return ControlPlaneListener(pattern_type, name, _METRICS)
    
    return listener_factory


def _get_client_id(request) -> str:
    """Extract client ID from request."""
    if client_id := request.headers.get("X-Client-Id"):
        return client_id
    if forwarded := request.headers.get("X-Forwarded-For"):
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


# ============================================================================
# Convenience Exports
# ============================================================================

__all__ = [
    # Main controller
    "FailsafeController",
    
    # Enums
    "Telemetry",
    "Protection",
    
    # Registry helpers
    "register_pattern",
    "get_pattern_config",
    "create_control_plane_listener",
    
    # Pydantic models
    "PatternConfig",
    "RetryConfig",
    "RateLimitConfig",
    "TimeoutConfig",
    "CircuitBreakerConfig",
    "BulkheadConfig",
    "MetricsResponse",
    "HealthResponse",
]