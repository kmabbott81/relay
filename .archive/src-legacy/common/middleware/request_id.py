"""
Request-ID middleware for FastAPI.

Ensures every request has a unique X-Request-ID for tracing and support correlation.
- Reads X-Request-ID from request headers
- Generates UUID4 if missing
- Stores in request.state.request_id for endpoint access
- Sets X-Request-ID header on all responses
"""

import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add X-Request-ID to request/response for tracing."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Extract/generate request ID and propagate to response."""
        # Read X-Request-ID from request headers; generate if missing
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Store in request.state for endpoint access
        request.state.request_id = request_id

        # Call endpoint
        response = await call_next(request)

        # Set X-Request-ID header on response
        response.headers["X-Request-ID"] = request_id

        return response
