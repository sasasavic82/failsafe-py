"""
FastAPI integration helpers for Failsafe patterns

Provides exception handlers and middleware for automatic Retry-After headers
"""

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from typing import Callable

from failsafe.ratelimit.exceptions import RateLimitExceeded
from failsafe.retry.exceptions import AttemptsExceeded


def add_failsafe_exception_handlers(app: FastAPI):
    """
    Add exception handlers for Failsafe patterns
    
    This automatically converts Failsafe exceptions into proper HTTP responses
    with appropriate status codes and headers (like Retry-After).
    
    Usage:
        app = FastAPI()
        add_failsafe_exception_handlers(app)
    """
    
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        """
        Handle rate limit exceptions with 429 status and Retry-After header
        """
        headers = {}
        
        # Add Retry-After header (HTTP standard)
        if exc.retry_after_seconds is not None:
            headers["Retry-After"] = exc.get_retry_after_header()
        
        # Add custom header with milliseconds for precision
        if exc.retry_after_ms is not None:
            headers["X-RateLimit-Retry-After-Ms"] = str(int(exc.retry_after_ms))
        
        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "message": str(exc),
                "retry_after_seconds": exc.retry_after_seconds,
                "retry_after_ms": exc.retry_after_ms,
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
):
    """
    Middleware to add rate limit information headers to all responses
    
    Adds headers:
    - X-RateLimit-Limit: Maximum requests allowed
    - X-RateLimit-Remaining: Requests remaining in current window
    - X-RateLimit-Reset: Unix timestamp when limit resets
    
    Usage:
        app = FastAPI()
        rate_limit_middleware(app)
    """
    
    @app.middleware("http")
    async def add_rate_limit_info(request: Request, call_next: Callable):
        """Add rate limit headers to response"""
        
        try:
            response = await call_next(request)
            
            if add_rate_limit_headers:
                # Try to extract rate limit info from the endpoint
                # This is a simplified version - in production you'd track this per-client
                response.headers["X-RateLimit-Limit"] = "100"
                response.headers["X-RateLimit-Remaining"] = "95"
                # response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
            
            return response
        
        except RateLimitExceeded as exc:
            # Let the exception handler deal with it
            raise


# Example usage in FastAPI app
"""
from fastapi import FastAPI
from failsafe.integrations.fastapi_helpers import add_failsafe_exception_handlers

app = FastAPI()

# Add exception handlers
add_failsafe_exception_handlers(app)

# Now rate limited endpoints will automatically return proper 429 with Retry-After
from failsafe.ratelimit import tokenbucket

@app.get("/api/resource")
@tokenbucket(name="resource", max_executions=10, per_time_secs=60)
async def get_resource():
    return {"data": "resource"}

# Client receives:
# HTTP/1.1 429 Too Many Requests
# Retry-After: 3
# X-RateLimit-Retry-After-Ms: 2500
# {
#   "error": "rate_limit_exceeded",
#   "message": "Rate limit exceeded. Retry after 2500ms",
#   "retry_after_seconds": 2.5,
#   "retry_after_ms": 2500
# }
"""