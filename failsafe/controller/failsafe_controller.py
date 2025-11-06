"""
FailsafeController - Control plane for Failsafe resiliency patterns

Provides REST APIs for:
- Dynamic configuration updates
- Real-time metrics querying
- Pattern instance discovery and management
- Health/liveness checks
"""

import asyncio
import weakref
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Global registry for pattern instances
_PATTERN_REGISTRY: Dict[str, Dict[str, Any]] = defaultdict(dict)
_METRICS_STORE: Dict[str, Dict[str, Any]] = defaultdict(lambda: defaultdict(int))
_CONFIG_STORE: Dict[str, Dict[str, Any]] = {}
_DEFAULT_CONFIGS: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# Pydantic Models for API
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
# Pattern Registry and Metrics Collection
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


# Global instances
_REGISTRY = PatternRegistry()
_METRICS = MetricsCollector()


# ============================================================================
# Configuration Management
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
# Control Plane Listener (integrates with existing event system)
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





class TokenBucketControlPlaneListener(ControlPlaneListener):
    pass
    

# ============================================================================
# FailsafeController - Main Controller Class
# ============================================================================

class FailsafeController:
    """
    Main controller that integrates Failsafe patterns with FastAPI.
    
    Usage:
        app = FastAPI()
        controller = FailsafeController(app, config_path="failsafe.yaml")
    """
    
    def __init__(
        self,
        app: FastAPI,
        config_path: Optional[Path] = None,
        prefix: str = "/failsafe",
        enable_metrics: bool = True,
        enable_control: bool = True,
    ):
        self.app = app
        self.prefix = prefix
        self.config_manager = ConfigManager(config_path)
        self.registry = _REGISTRY
        self.metrics = _METRICS
        self.enable_metrics = enable_metrics
        self.enable_control = enable_control
        
        # Load configuration at initialization
        self.config_manager.load_config()
        
        # Register API routes
        self._register_routes()
        
        # Add lifecycle hooks
        self._add_lifecycle_hooks()
    
    def _add_lifecycle_hooks(self):
        """Add startup/shutdown hooks"""
        
        @self.app.on_event("startup")
        async def startup():
            print(f"FailsafeController initialized with prefix: {self.prefix}")
            print(f"Loaded configs: {list(_DEFAULT_CONFIGS.keys())}")
        
        @self.app.on_event("shutdown")
        async def shutdown():
            print("FailsafeController shutting down")
    
    def _register_routes(self):
        """Register all control plane API routes"""
        
        # Health and liveness endpoints
        @self.app.get(f"{self.prefix}/health", response_model=HealthResponse, tags=["failsafe"])
        async def health():
            """Health check endpoint"""
            patterns = self.registry.get_all_patterns()
            return HealthResponse(
                status="healthy",
                timestamp=datetime.utcnow().isoformat(),
                patterns_active=len(patterns)
            )
        
        @self.app.get(f"{self.prefix}/liveness", tags=["failsafe"])
        async def liveness():
            """Simple liveness check (ping)"""
            return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}
        
        # Pattern discovery
        @self.app.get(f"{self.prefix}/patterns", tags=["failsafe"])
        async def list_patterns(pattern_type: Optional[str] = None):
            """List all registered patterns"""
            if pattern_type:
                patterns = self.registry.list_patterns(pattern_type)
            else:
                patterns = self.registry.get_all_patterns()
            
            return {
                "patterns": patterns,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Configuration management
        if self.enable_control:
            @self.app.get(f"{self.prefix}/config/{{pattern_type}}/{{name}}", tags=["failsafe"])
            async def get_config(pattern_type: str, name: str):
                """Get configuration for a specific pattern"""
                config = self.config_manager.get_pattern_config(pattern_type, name)
                if not config:
                    # Try to get from runtime config store
                    key = f"{pattern_type}:{name}"
                    config = _CONFIG_STORE.get(key, {})
                
                return {
                    "pattern_type": pattern_type,
                    "name": name,
                    "config": config,
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            @self.app.put(f"{self.prefix}/config/{{pattern_type}}/{{name}}", tags=["failsafe"])
            async def update_config(pattern_type: str, name: str, config: Dict[str, Any]):
                """Update configuration for a specific pattern"""
                # Validate pattern exists
                pattern = self.registry.get_pattern(pattern_type, name)
                if not pattern:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Pattern {pattern_type}:{name} not found"
                    )
                
                # Update configuration
                self.config_manager.update_pattern_config(pattern_type, name, config)
                
                # Apply configuration to pattern manager (pattern-specific logic)
                await self._apply_config_to_pattern(pattern_type, name, pattern, config)
                
                return {
                    "pattern_type": pattern_type,
                    "name": name,
                    "config": config,
                    "status": "updated",
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            @self.app.get(f"{self.prefix}/config", tags=["failsafe"])
            async def get_all_configs():
                """Get all configurations"""
                return {
                    "configs": self.config_manager._configs,
                    "defaults": _DEFAULT_CONFIGS,
                    "timestamp": datetime.utcnow().isoformat()
                }
        
        # Metrics endpoints
        if self.enable_metrics:
            @self.app.get(f"{self.prefix}/metrics/{{pattern_type}}/{{name}}", response_model=MetricsResponse, tags=["failsafe"])
            async def get_metrics(pattern_type: str, name: str):
                """Get metrics for a specific pattern"""
                metrics = self.metrics.get_metrics(pattern_type, name)
                if not metrics:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No metrics found for {pattern_type}:{name}"
                    )
                
                return MetricsResponse(
                    pattern_type=pattern_type,
                    name=name,
                    metrics=metrics,
                    timestamp=datetime.utcnow().isoformat()
                )
            
            @self.app.get(f"{self.prefix}/metrics", tags=["failsafe"])
            async def get_all_metrics():
                """Get all metrics"""
                all_metrics = self.metrics.get_all_metrics()
                return {
                    "metrics": all_metrics,
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            @self.app.delete(f"{self.prefix}/metrics/{{pattern_type}}/{{name}}", tags=["failsafe"])
            async def reset_metrics(pattern_type: str, name: str):
                """Reset metrics for a specific pattern"""
                self.metrics.reset_metrics(pattern_type, name)
                return {
                    "pattern_type": pattern_type,
                    "name": name,
                    "status": "reset",
                    "timestamp": datetime.utcnow().isoformat()
                }
        
        # Pattern control endpoints
        if self.enable_control:
            @self.app.post(f"{self.prefix}/control/{{pattern_type}}/{{name}}/enable", tags=["failsafe"])
            async def enable_pattern(pattern_type: str, name: str):
                """Enable a specific pattern"""
                pattern = self.registry.get_pattern(pattern_type, name)
                if not pattern:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Pattern {pattern_type}:{name} not found"
                    )
                
                # Set enabled flag (pattern-specific logic)
                if hasattr(pattern, '_enabled'):
                    pattern._enabled = True
                
                return {
                    "pattern_type": pattern_type,
                    "name": name,
                    "status": "enabled",
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            @self.app.post(f"{self.prefix}/control/{{pattern_type}}/{{name}}/disable", tags=["failsafe"])
            async def disable_pattern(pattern_type: str, name: str):
                """Disable a specific pattern"""
                pattern = self.registry.get_pattern(pattern_type, name)
                if not pattern:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Pattern {pattern_type}:{name} not found"
                    )
                
                # Set enabled flag (pattern-specific logic)
                if hasattr(pattern, '_enabled'):
                    pattern._enabled = False
                
                return {
                    "pattern_type": pattern_type,
                    "name": name,
                    "status": "disabled",
                    "timestamp": datetime.utcnow().isoformat()
                }
    
    async def _apply_config_to_pattern(self, pattern_type: str, name: str, pattern: Any, config: Dict[str, Any]):
        """Apply configuration changes to a pattern instance"""
        # Pattern-specific configuration application
        
        if pattern_type == "retry":
            if "attempts" in config:
                pattern._attempts = config["attempts"]
            if "backoff" in config:
                from failsafe.retry.backoffs import create_backoff
                pattern._backoff = create_backoff(config["backoff"])
        
        elif pattern_type == "ratelimit":
            if hasattr(pattern, '_limiter') and pattern._limiter:
                bucket = pattern._limiter
                if "max_executions" in config:
                    bucket._max_executions = config["max_executions"]
                if "per_time_secs" in config:
                    bucket._per_time_secs = config["per_time_secs"]
                if "bucket_size" in config:
                    bucket._bucket_size = config["bucket_size"]
        
        # Add more pattern-specific logic as needed


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
    # Check if there's a runtime config
    key = f"{pattern_type}:{name}"
    if key in _CONFIG_STORE:
        return _CONFIG_STORE[key]
    
    # Check default configs loaded from YAML
    pattern_configs = _DEFAULT_CONFIGS.get(pattern_type, {})
    
    # Try exact match first
    if name in pattern_configs:
        return pattern_configs[name]
    
    # Try default config
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
        if pattern_type == "tokenbucket":
            return TokenBucketControlPlaneListener(pattern_type, name, _METRICS)
        # Add more pattern types as needed
        return ControlPlaneListener(pattern_type, name, _METRICS)
    
    return listener_factory