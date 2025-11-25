"""
FastAPI integration helpers for Failsafe patterns

Provides exception handlers and middleware for automatic Retry-After headers
with per-client tracking support.
"""

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from typing import Callable, Optional
import hashlib

from failsafe.ratelimit.exceptions import RateLimitExceeded
from failsafe.retry.exceptions import AttemptsExceeded


def get_client_id_from_request(request: Request) -> str:
    """
    Extract a client identifier from the request.
    
    Priority:
    1. X-Client-Id header
    2. Authorization header (hashed)
    3. IP address
    4. Fallback to "anonymous"
    """
    # Try X-Client-Id header
    client_id = request.headers.get("X-Client-Id")
    if client_id:
        return client_id
    
    # Try Authorization header (hash it for privacy)
    auth = request.headers.get("Authorization")
    if auth:
        return hashlib.sha256(auth.encode()).hexdigest()[:16]
    
    # Try X-Forwarded-For (behind proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    # Try direct client IP
    if request.client:
        return f"{request.client.host}"
    
    return "anonymous"


def add_failsafe_exception_handlers(
    app: FastAPI,
    include_backpressure: bool = True,
    client_id_extractor: Optional[Callable[[Request], str]] = None,
):
    """
    Add exception handlers for Failsafe patterns with per-client Retry-After.
    
    This automatically converts Failsafe exceptions into proper HTTP responses
    with appropriate status codes and headers (like Retry-After).
    
    Usage:
        app = FastAPI()
        add_failsafe_exception_handlers(app)
        
        # Or with custom client ID extraction
        def my_client_extractor(request: Request) -> str:
            return request.headers.get("X-API-Key", "anonymous")
        
        add_failsafe_exception_handlers(app, client_id_extractor=my_client_extractor)
    
    Args:
        app: FastAPI application
        include_backpressure: Include X-Backpressure header in responses
        client_id_extractor: Custom function to extract client ID from request
    """
    
    # Use provided extractor or default
    extractor = client_id_extractor or get_client_id_from_request
    
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        """
        Handle rate limit exceptions with 429 status and per-client Retry-After header.
        
        The Retry-After value is specific to each client based on their rejection history
        and latency patterns (when using backpressure strategy).
        """
        headers = {}
        
        # Add Retry-After header (HTTP standard)
        if exc.retry_after_seconds is not None:
            headers["Retry-After"] = exc.get_retry_after_header()
        
        # Add custom header with milliseconds for precision
        if exc.retry_after_ms is not None:
            headers["X-RateLimit-Retry-After-Ms"] = str(int(exc.retry_after_ms))
        
        # Add backpressure header if enabled
        if include_backpressure:
            # Try to get backpressure from the limiter that caused the exception
            # This requires storing a reference in the exception or extracting from request state
            client_id = extractor(request)
            
            # Check if there's a limiter attached to the request state
            if hasattr(request.state, "rate_limiter"):
                limiter = request.state.rate_limiter
                if hasattr(limiter, "get_backpressure"):
                    bp_score = limiter.get_backpressure(client_id=client_id)
                    if bp_score is not None:
                        headers["X-Backpressure"] = f"{bp_score:.3f}"
            
            # Fallback: assume high backpressure on rate limit
            if "X-Backpressure" not in headers:
                headers["X-Backpressure"] = "1.000"
        
        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "message": str(exc),
                "retry_after_seconds": exc.retry_after_seconds,
                "retry_after_ms": exc.retry_after_ms,
                "client_id": extractor(request),  # Include for debugging
            },
            headers=headers,
        )
    
    @app.exception_handler(AttemptsExceeded)
    async def retry_exhausted_handler(request: Request, exc: AttemptsExceeded):
        """
        Handle retry exhaustion with 503 status
        """
        return JSONResponse(
            status_code=503,
            content={
                "error": "service_unavailable",
                "message": "Service temporarily unavailable - all retry attempts failed",
            },
            headers={
                "Retry-After": "60",  # Suggest retry in 60 seconds
            },
        )


def rate_limit_middleware(
    app: FastAPI,
    add_rate_limit_headers: bool = True,
    add_backpressure_headers: bool = True,
    client_id_extractor: Optional[Callable[[Request], str]] = None,
):
    """
    Middleware to add rate limit and backpressure information headers to all responses.
    
    Adds headers:
    - X-RateLimit-Limit: Maximum requests allowed
    - X-RateLimit-Remaining: Requests remaining in current window
    - X-RateLimit-Reset: Unix timestamp when limit resets
    - X-Backpressure: Current backpressure score (0.0-1.0)
    - X-Client-Id: Client identifier used for rate limiting
    
    Usage:
        app = FastAPI()
        rate_limit_middleware(app)
    
    Args:
        app: FastAPI application
        add_rate_limit_headers: Add X-RateLimit-* headers
        add_backpressure_headers: Add X-Backpressure header
        client_id_extractor: Custom function to extract client ID
    """
    
    extractor = client_id_extractor or get_client_id_from_request
    
    @app.middleware("http")
    async def add_rate_limit_info(request: Request, call_next: Callable):
        """Add rate limit and backpressure headers to response"""
        
        # Extract client ID and store in request state
        client_id = extractor(request)
        request.state.client_id = client_id
        
        try:
            response = await call_next(request)
            
            # Add client ID header for transparency
            response.headers["X-Client-Id"] = client_id
            
            # Try to get limiter from request state (set by decorator/context manager)
            if hasattr(request.state, "rate_limiter"):
                limiter = request.state.rate_limiter
                
                if add_rate_limit_headers:
                    # Add rate limit info
                    if hasattr(limiter, "_limiter"):
                        bucket_limiter = limiter._limiter
                        response.headers["X-RateLimit-Limit"] = str(int(bucket_limiter.max_executions))
                        response.headers["X-RateLimit-Remaining"] = str(int(bucket_limiter.current_tokens))
                
                # Add backpressure header
                if add_backpressure_headers:
                    if hasattr(limiter, "get_backpressure"):
                        bp_score = limiter.get_backpressure(client_id=client_id)
                        if bp_score is not None:
                            response.headers["X-Backpressure"] = f"{bp_score:.3f}"
            
            return response
        
        except RateLimitExceeded:
            # Let the exception handler deal with it
            raise


# FastAPI dependency for extracting client ID
def get_client_id(request: Request) -> str:
    """
    FastAPI dependency to get client ID.
    
    Usage:
        from fastapi import Depends
        
        @app.get("/resource")
        async def get_resource(client_id: str = Depends(get_client_id)):
            # Use client_id
            pass
    """
    if hasattr(request.state, "client_id"):
        return request.state.client_id
    return get_client_id_from_request(request)


# Context var for storing client ID in async context
from contextvars import ContextVar

_client_id_context: ContextVar[Optional[str]] = ContextVar('client_id', default=None)


def set_client_id_context(client_id: str):
    """Set client ID in context for the current async task"""
    _client_id_context.set(client_id)


def get_client_id_context() -> Optional[str]:
    """Get client ID from context"""
    return _client_id_context.get()


def create_client_id_extractor(request: Request) -> Callable[[], Optional[str]]:
    """
    Create a client ID extractor function that can be used by tokenbucket.
    
    Usage:
        from failsafe.ratelimit import tokenbucket
        
        @app.get("/resource")
        async def get_resource(request: Request):
            # Create extractor for this request
            extractor = create_client_id_extractor(request)
            
            # Use with tokenbucket
            limiter = tokenbucket(
                max_executions=10,
                per_time_secs=60,
                enable_per_client_tracking=True,
                client_id_extractor=extractor
            )
            
            async with limiter:
                return {"data": "resource"}
    """
    client_id = get_client_id_from_request(request)
    
    def extractor():
        return client_id
    
    return extractor


# Example usage patterns
"""
# Pattern 1: Basic setup with automatic per-client tracking
from fastapi import FastAPI
from failsafe.integrations.fastapi_helpers import add_failsafe_exception_handlers, rate_limit_middleware

app = FastAPI()
add_failsafe_exception_handlers(app)
rate_limit_middleware(app)

# Pattern 2: Per-client rate limiting with decorator
from failsafe.ratelimit import tokenbucket
from fastapi import Request

@app.get("/api/resource")
async def get_resource(request: Request):
    limiter = tokenbucket(
        name="resource",
        max_executions=10,
        per_time_secs=60,
        enable_per_client_tracking=True,
        client_id_extractor=create_client_id_extractor(request)
    )
    
    # Store in request state for middleware
    request.state.rate_limiter = limiter
    
    async with limiter:
        return {"data": "resource"}

# Pattern 3: Global rate limiter with context
from contextvars import ContextVar

# Create global limiter
global_limiter = tokenbucket(
    name="global",
    max_executions=100,
    per_time_secs=60,
    enable_per_client_tracking=True,
    client_id_extractor=get_client_id_context
)

@app.middleware("http")
async def inject_client_id(request: Request, call_next):
    client_id = get_client_id_from_request(request)
    set_client_id_context(client_id)
    request.state.client_id = client_id
    response = await call_next(request)
    return response

@app.get("/api/resource")
@global_limiter
async def get_resource():
    return {"data": "resource"}

# Client receives per-client Retry-After:
# HTTP/1.1 429 Too Many Requests
# Retry-After: 5
# X-RateLimit-Retry-After-Ms: 4800
# X-Backpressure: 0.750
# X-Client-Id: 192.168.1.100
# {
#   "error": "rate_limit_exceeded",
#   "message": "Rate limit exceeded. Retry after 4800ms",
#   "retry_after_seconds": 4.8,
#   "retry_after_ms": 4800,
#   "client_id": "192.168.1.100"
# }
"""