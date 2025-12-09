"""
Failsafe Controller - One-line resilience bootstrap for FastAPI applications.

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

import os
from enum import Enum
from typing import TYPE_CHECKING, Optional, Callable, Any

if TYPE_CHECKING:
    from fastapi import FastAPI
    from opentelemetry.sdk.metrics import MeterProvider


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


class FailsafeController:
    """
    Fluent API for bootstrapping Failsafe resilience patterns in FastAPI.
    
    Example:
        app = FastAPI()
        
        FailsafeController(app) \\
            .with_telemetry(Telemetry.OTEL) \\
            .with_protection(Protection.INGRESS) \\
            .with_controlplane()
    
    This single chain:
        - Registers all exception handlers (429, 503, 504, etc.)
        - Adds rate limit info middleware
        - Sets up OpenTelemetry metrics export
        - Configures control plane integration
    """
    
    def __init__(
        self,
        app: "FastAPI",
        *,
        service_name: Optional[str] = None,
        namespace: str = "failsafe",
    ) -> None:
        """
        Initialize the Failsafe controller.
        
        Args:
            app: FastAPI application instance
            service_name: Service name for telemetry (defaults to app.title or env var)
            namespace: Metric namespace prefix (default: "failsafe")
        """
        self.app = app
        self.service_name = service_name or self._resolve_service_name()
        self.namespace = namespace
        self._meter_provider: Optional["MeterProvider"] = None
        self._telemetry_type: Telemetry = Telemetry.NONE
        self._protection_type: Optional[Protection] = None
        self._controlplane_enabled: bool = False
        self._controlplane_url: Optional[str] = None
    
    def _resolve_service_name(self) -> str:
        """Resolve service name from app title or environment."""
        # Try environment variable first
        if name := os.environ.get("SERVICE_NAME"):
            return name
        if name := os.environ.get("OTEL_SERVICE_NAME"):
            return name
        # Fall back to FastAPI app title
        if hasattr(self.app, "title") and self.app.title:
            return self.app.title.lower().replace(" ", "-")
        return "failsafe-service"
    
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
        
        Example:
            FailsafeController(app).with_telemetry(Telemetry.OTEL)
            
            # With custom endpoint
            FailsafeController(app).with_telemetry(
                Telemetry.OTEL,
                endpoint="http://otel-collector:4318/v1/metrics"
            )
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
        
        # Resolve endpoint
        otel_endpoint = endpoint or os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "http://localhost:4318/v1/metrics"
        )
        
        # Create resource with service info
        resource = Resource.create({
            "service.name": self.service_name,
            "service.namespace": self.namespace,
        })
        
        # Create exporter and reader
        exporter = OTLPMetricExporter(
            endpoint=otel_endpoint,
            timeout=timeout,
        )
        reader = PeriodicExportingMetricReader(
            exporter,
            export_interval_millis=export_interval_ms,
        )
        
        # Create and set meter provider
        self._meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[reader],
        )
        set_meter_provider(self._meter_provider)
        
        # Instrument Failsafe patterns
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
        
        # Add Prometheus metrics endpoint
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
        
        Protection types:
            - INGRESS: Rate limiting on incoming requests (exception handlers + middleware)
            - EGRESS: Resilience on outgoing requests (retry, circuit breaker handlers)
            - FULL: Both ingress and egress protection
        
        Example:
            FailsafeController(app).with_protection(Protection.INGRESS)
        """
        self._protection_type = protection_type
        
        if protection_type in (Protection.INGRESS, Protection.FULL):
            self._setup_ingress_protection(
                add_headers=add_headers,
                log_rejections=log_rejections,
            )
        
        if protection_type in (Protection.EGRESS, Protection.FULL):
            self._setup_egress_protection()
        
        return self
    
    def _setup_ingress_protection(
        self,
        add_headers: bool = True,
        log_rejections: bool = True,
    ) -> None:
        """Configure ingress protection (rate limiting)."""
        from fastapi import Request
        from fastapi.responses import JSONResponse
        from failsafe.ratelimit.exceptions import RateLimitExceeded, EmptyBucket
        
        # Register rate limit exception handler
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
            
            # Add backpressure header if available
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
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Rate limit exceeded",
                },
                headers={"Retry-After": "1"},
            )
        
        # Add rate limit info middleware
        if add_headers:
            @self.app.middleware("http")
            async def rate_limit_info_middleware(request: Request, call_next):
                response = await call_next(request)
                
                # Add rate limit headers if limiter is available
                if hasattr(request.state, "endpoint_limiter"):
                    limiter = request.state.endpoint_limiter
                    if hasattr(limiter, "_limiter"):
                        bucket = limiter._limiter
                        response.headers["RateLimit-Limit"] = str(int(bucket.max_executions))
                        response.headers["RateLimit-Remaining"] = str(int(bucket.current_tokens))
                    
                    # Add backpressure header
                    client_id = getattr(request.state, "client_id", None)
                    bp = limiter.get_backpressure(client_id=client_id)
                    if bp is not None:
                        response.headers["X-Backpressure"] = f"{bp:.3f}"
                
                return response
    
    def _setup_egress_protection(self) -> None:
        """Configure egress protection (retry, circuit breaker, etc.)."""
        from fastapi import Request
        from fastapi.responses import JSONResponse
        
        # Import egress-related exceptions
        try:
            from failsafe.retry.exceptions import AttemptsExceeded
            
            @self.app.exception_handler(AttemptsExceeded)
            async def retry_exhausted_handler(request: Request, exc: AttemptsExceeded):
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "service_unavailable",
                        "message": "Service temporarily unavailable - all retry attempts failed",
                    },
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
                    content={
                        "error": "circuit_breaker_open",
                        "message": "Service temporarily unavailable - circuit breaker open",
                    },
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
                    content={
                        "error": "bulkhead_full",
                        "message": "Service temporarily unavailable - concurrency limit reached",
                    },
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
                    content={
                        "error": "timeout",
                        "message": "Operation timed out",
                    },
                )
        except ImportError:
            pass
    
    def with_controlplane(
        self,
        *,
        url: Optional[str] = None,
        poll_interval_secs: int = 30,
        enable_dynamic_config: bool = True,
    ) -> "FailsafeController":
        """
        Enable control plane integration for dynamic configuration.
        
        Args:
            url: Control plane URL (defaults to env var or localhost)
            poll_interval_secs: How often to poll for config changes
            enable_dynamic_config: Allow runtime config updates
        
        Returns:
            Self for method chaining
        
        Features:
            - Dynamic rate limit adjustment
            - Feature flag management
            - Circuit breaker state control
            - Real-time configuration updates
        
        Example:
            FailsafeController(app).with_controlplane(
                url="http://failsafe-controlplane:8080"
            )
        """
        self._controlplane_enabled = True
        self._controlplane_url = url or os.environ.get(
            "FAILSAFE_CONTROLPLANE_URL",
            "http://localhost:8080"
        )
        
        self._setup_controlplane(
            poll_interval_secs=poll_interval_secs,
            enable_dynamic_config=enable_dynamic_config,
        )
        
        return self
    
    def _setup_controlplane(
        self,
        poll_interval_secs: int = 30,
        enable_dynamic_config: bool = True,
    ) -> None:
        """Configure control plane integration."""
        import asyncio
        from contextlib import asynccontextmanager
        
        # Store original lifespan if exists
        original_lifespan = getattr(self.app, "router", None)
        original_lifespan = getattr(original_lifespan, "lifespan_context", None)
        
        @asynccontextmanager
        async def lifespan(app):
            # Start control plane polling task
            poll_task = None
            if enable_dynamic_config:
                poll_task = asyncio.create_task(
                    self._poll_controlplane(poll_interval_secs)
                )
            
            # Register with control plane
            await self._register_with_controlplane()
            
            # Run original lifespan if exists
            if original_lifespan:
                async with original_lifespan(app):
                    yield
            else:
                yield
            
            # Cleanup
            if poll_task:
                poll_task.cancel()
                try:
                    await poll_task
                except asyncio.CancelledError:
                    pass
            
            # Deregister from control plane
            await self._deregister_from_controlplane()
        
        # Note: Setting lifespan after app creation requires FastAPI >= 0.93
        # For older versions, users should pass lifespan to FastAPI constructor
        self.app.router.lifespan_context = lifespan
    
    async def _register_with_controlplane(self) -> None:
        """Register this service instance with the control plane."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self._controlplane_url}/api/v1/services/register",
                    json={
                        "service_name": self.service_name,
                        "namespace": self.namespace,
                        "telemetry": self._telemetry_type.value,
                        "protection": self._protection_type.value if self._protection_type else None,
                    },
                    timeout=5.0,
                )
        except Exception as e:
            # Log but don't fail startup
            print(f"[FAILSAFE] Warning: Could not register with control plane: {e}")
    
    async def _deregister_from_controlplane(self) -> None:
        """Deregister this service instance from the control plane."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self._controlplane_url}/api/v1/services/deregister",
                    json={"service_name": self.service_name},
                    timeout=5.0,
                )
        except Exception:
            pass  # Best effort
    
    async def _poll_controlplane(self, interval_secs: int) -> None:
        """Poll control plane for configuration updates."""
        import asyncio
        
        while True:
            try:
                await asyncio.sleep(interval_secs)
                await self._fetch_and_apply_config()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[FAILSAFE] Warning: Control plane poll failed: {e}")
    
    async def _fetch_and_apply_config(self) -> None:
        """Fetch and apply configuration from control plane."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._controlplane_url}/api/v1/services/{self.service_name}/config",
                    timeout=5.0,
                )
                if response.status_code == 200:
                    config = response.json()
                    self._apply_config(config)
        except Exception:
            pass  # Continue with current config
    
    def _apply_config(self, config: dict) -> None:
        """Apply configuration updates from control plane."""
        # Update rate limit configs
        if "rate_limits" in config:
            from failsafe.controller import update_rate_limit_config
            for name, settings in config["rate_limits"].items():
                update_rate_limit_config(name, settings)
        
        # Update feature flags
        if "feature_flags" in config:
            from failsafe.controller import update_feature_flags
            update_feature_flags(config["feature_flags"])
        
        # Update circuit breaker states
        if "circuit_breakers" in config:
            from failsafe.controller import update_circuit_breaker_config
            for name, settings in config["circuit_breakers"].items():
                update_circuit_breaker_config(name, settings)


def _get_client_id(request: "Request") -> str:
    """Extract client ID from request."""
    # Try X-Client-Id header first
    if client_id := request.headers.get("X-Client-Id"):
        return client_id
    
    # Try X-Forwarded-For
    if forwarded := request.headers.get("X-Forwarded-For"):
        return forwarded.split(",")[0].strip()
    
    # Fall back to client host
    if request.client:
        return request.client.host
    
    return "unknown"


# Convenience exports
__all__ = [
    "FailsafeController",
    "Telemetry",
    "Protection",
]