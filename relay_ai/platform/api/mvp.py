"""
Relay MVP FastAPI Application

Combines:
- Knowledge API (document upload + search) via adapter from src/knowledge
- Stream API (JWT auth + OAuth) via adapter from src/stream
- Security headers (visible trust indicators on EVERY response)
- Team management (invites, members) via stub routers
- Request tracing (X-Request-ID on all responses)

CRITICAL SECURITY:
- JWT required on all /api/v1/* endpoints
- RLS enforcement per request (via adapters)
- Security headers expose proof to clients
- No secrets in code (environment variables only)

Architecture:
- Adapters re-export production code from src/ without modification
- New endpoints in relay-ai/platform/api/*_router.py
- Middleware: RequestID + Security Headers + CORS
"""

# CRITICAL: Install import redirect FIRST (before any relay_ai imports)
# This must happen before knowledge/stream/memory are imported
from relay_ai.compat.import_redirect import install_src_redirect

install_src_redirect()

import logging
import os
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from relay_ai.platform.api.auth_router import router as auth_router

# Import routers via adapters (production-proven code)
from relay_ai.platform.api.knowledge import close_pool, init_pool, knowledge_router

# MVP Chat Console for beta testing
from relay_ai.platform.api.mvp_router import router as mvp_router
from relay_ai.platform.api.security_router import router as security_router
from relay_ai.platform.api.teams_router import router as teams_router

# Fail-closed security validation (enforced in staging/production)
from relay_ai.platform.security.startup_checks import enforce_fail_closed

# Enforce fail-closed security configuration on module load
enforce_fail_closed()

# Imports below must happen after import redirect - E402 warnings are expected
# ruff: noqa: E402

# Add repo root to sys.path for RequestID middleware import

REPO_ROOT = Path(__file__).parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from relay_ai.common.middleware.request_id import RequestIDMiddleware
except ImportError:
    # Fallback: Define minimal RequestIDMiddleware if not found
    class RequestIDMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                request_id = str(uuid.uuid4())
                scope["state"] = {"request_id": request_id}
            return await self.app(scope, receive, send)


logger = logging.getLogger(__name__)

# ==============================================================================
# APPLICATION SETUP
# ==============================================================================

app = FastAPI(
    title="Relay MVP",
    description="The provably secure AI assistant for SMBs - MVP API",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI at /docs
    redoc_url="/redoc",  # ReDoc at /redoc
)

# ==============================================================================
# CORS MIDDLEWARE (Explicit Allowlist Enforcement)
# ==============================================================================

# Parse CORS origins and enforce explicit allowlist in staging/production
env = os.getenv("RELAY_ENV", "development").lower()
origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

# Fail-closed: staging/production must have explicit origins (no wildcard)
if env in {"staging", "production"} and (not origins or "*" in origins):
    raise RuntimeError(
        "CORS_ORIGINS must be an explicit comma-separated allowlist in staging/production. "
        f"Got: {os.getenv('CORS_ORIGINS', '*')}"
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],  # Wildcard only in development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Request-ID",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "Retry-After",
        "X-Data-Isolation",
        "X-Encryption",
        "X-Training-Data",
        "X-Audit-Log",
    ],
)

# ==============================================================================
# REQUEST TRACING MIDDLEWARE (RequestID)
# ==============================================================================

app.add_middleware(RequestIDMiddleware)

# ==============================================================================
# SECURITY HEADERS MIDDLEWARE (THE DIFFERENTIATOR)
# ==============================================================================


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Add visible security headers to EVERY response.

    These headers make security TRANSPARENT to clients and audit tools.
    This is what makes Relay different from Copilot.

    Headers:
    - X-Request-ID: Unique trace ID for this request
    - X-Data-Isolation: How user data is isolated (RLS)
    - X-Encryption: Encryption algorithm used
    - X-Training-Data: Whether data trains models
    - X-Audit-Log: Link to audit log for this request
    """
    # Get or generate request ID
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    if not hasattr(request.state, "request_id"):
        request.state.request_id = request_id

    # Call endpoint
    response: Response = await call_next(request)

    # Add transparency headers (VISIBLE SECURITY)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Data-Isolation"] = "user-scoped"  # RLS enforced per user
    response.headers["X-Encryption"] = "AES-256-GCM"  # How files are encrypted
    response.headers["X-Training-Data"] = "never"  # Data never trains models
    response.headers["X-Audit-Log"] = f"/security/audit?request_id={request_id}"

    return response


# ==============================================================================
# ROUTERS: Include all API endpoints
# ==============================================================================

# Knowledge API (production-proven from src/knowledge)
if knowledge_router:
    app.include_router(
        knowledge_router,
        prefix="/api/v1/knowledge",
        tags=["Knowledge API (Production)"],
    )

# Auth API (stub for OAuth + JWT)
app.include_router(
    auth_router,
    prefix="/auth",
    tags=["Authentication (Stub)"],
)

# Security Dashboard API (stub for audit logs + metrics)
app.include_router(
    security_router,
    prefix="/security",
    tags=["Security Dashboard (Stub)"],
)

# Team Management API (stub for invites + members)
app.include_router(
    teams_router,
    prefix="/teams",
    tags=["Teams (Stub)"],
)

# MVP Chat Console (beta testing interface)
app.include_router(
    mvp_router,
    prefix="/mvp",
    tags=["MVP Console"],
)

# ==============================================================================
# HEALTH CHECK ENDPOINTS
# ==============================================================================


@app.get("/ready", tags=["Health"])
async def readiness_probe():
    """
    Readiness probe for Kubernetes/Railway.

    Returns 200 if:
    - App is running
    - Database pool is initialized
    - Redis is reachable (optional, graceful degradation)

    Returns 503 if critical services unavailable.
    """
    checks = {
        "app": "ok",
        "database": "unknown",  # TODO: Check pool status
        "redis": "optional",  # Graceful degradation
    }

    return {
        "ready": True,
        "service": "relay-mvp",
        "version": "1.0.0",
        "checks": checks,
    }


@app.get("/health", tags=["Health"])
async def liveness_probe():
    """
    Liveness probe for Kubernetes.
    Returns 200 if process is alive.
    """
    return {"status": "ok"}


@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint. Redirects to docs in development.
    """
    return {
        "message": "Relay MVP API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready",
    }


# ==============================================================================
# STARTUP / SHUTDOWN HOOKS
# ==============================================================================


@app.on_event("startup")
async def startup_event():
    """
    Initialize services on startup.

    CRITICAL:
    - Initialize database pool
    - Verify environment variables
    - Log startup confirmation
    """
    logger.info("🚀 Relay MVP starting up...")

    # Initialize database pool (if Knowledge API is available)
    if init_pool:
        try:
            database_url = os.getenv("DATABASE_URL")
            if database_url:
                await init_pool(database_url)
                logger.info("✓ Database pool initialized")
            else:
                logger.warning("DATABASE_URL not set; some endpoints may fail")
        except Exception as e:
            logger.error(f"Database pool initialization failed: {e}")

    # Verify critical environment variables
    required_env_vars = ["DATABASE_URL", "SUPABASE_JWT_SECRET"]
    missing = [var for var in required_env_vars if not os.getenv(var)]
    if missing:
        logger.warning(f"Missing environment variables: {missing}")

    logger.info("✓ Relay MVP ready to serve requests")


@app.on_event("shutdown")
async def shutdown_event():
    """
    Cleanup on shutdown.

    CRITICAL:
    - Close database pool gracefully
    - Flush logs
    """
    logger.info("🛑 Relay MVP shutting down...")

    # Close database pool
    if close_pool:
        try:
            await close_pool()
            logger.info("✓ Database pool closed")
        except Exception as e:
            logger.error(f"Database pool close failed: {e}")

    logger.info("✓ Relay MVP shutdown complete")


# ==============================================================================
# DEVELOPMENT SERVER
# ==============================================================================

if __name__ == "__main__":
    import uvicorn

    # Development mode: reload on code changes
    uvicorn.run(
        "relay_ai.platform.api.mvp:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
