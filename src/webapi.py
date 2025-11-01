"""FastAPI web API for templates and triage endpoints.

Sprint 46: Added /metrics endpoint and telemetry middleware.
Sprint 49 Phase B: Added /actions endpoints with preview/confirm workflow.
"""

import asyncio
import json
import os
import time
from base64 import b64encode
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .auth.security import require_scopes
from .knowledge import router as knowledge_router
from .limits.limiter import RateLimitExceeded, get_rate_limiter

# Note: stream auth module imports deferred to avoid startup issues
# from .stream.auth import generate_anon_session_token, verify_supabase_jwt
# from .stream.limits import RateLimiter
from .telemetry import init_telemetry
from .telemetry.middleware import TelemetryMiddleware
from .templates import list_templates
from .templates import render_template as render_template_content

# Sprint 58 Slice 5: Request body size limit (512 KiB for security hardening)
MAX_BODY_BYTES = 512 * 1024


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to limit request body size (Sprint 58 hardening)."""

    async def dispatch(self, request: Request, call_next):
        """Check request body size before processing."""
        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            return Response("Request body too large (max 512 KiB)", status_code=413)

        # Re-inject body for downstream consumption
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive
        return await call_next(request)


app = FastAPI(
    title="DJP Workflow API",
    version="1.0.0",
    openapi_tags=[
        {"name": "actions", "description": "Action preview and execution endpoints"},
        {"name": "audit", "description": "Audit log queries (admin only)"},
        {"name": "health", "description": "Health and status endpoints"},
    ],
)

# Sprint 51: Add security scheme for API key authentication
app.openapi_schema = None  # Force regeneration


def custom_openapi():
    """Custom OpenAPI schema with security definitions."""
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description="""
DJP Workflow API with Sprint 51 Phase 1 security.

## Authentication

All `/actions/*` endpoints require authentication via API key:

```
Authorization: Bearer relay_sk_<key>
```

## Scopes

- `actions:preview` - Preview actions before execution
- `actions:execute` - Execute actions
- `audit:read` - Query audit logs (admin only)

## Roles

- **viewer**: Can preview actions only
- **developer**: Can preview and execute actions
- **admin**: Full access including audit logs

## Error Codes

- `401` - Missing or invalid API key
- `403` - Insufficient permissions (scope check failed)
- `409` - Idempotency conflict (duplicate request)
- `501` - Provider not configured
- `504` - Execution timeout
        """,
        routes=app.routes,
    )

    # Add security scheme
    openapi_schema["components"]["securitySchemes"] = {
        "ApiKeyBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "API-Key",
            "description": "API key in format: relay_sk_<random>",
        }
    }

    # Mark endpoints that require auth
    for path in openapi_schema["paths"]:
        for method in openapi_schema["paths"][path]:
            if path.startswith("/actions/preview") or path.startswith("/actions/execute") or path.startswith("/audit"):
                openapi_schema["paths"][path][method]["security"] = [{"ApiKeyBearer": []}]
                # Add scope hints for documentation
                if path.startswith("/audit"):
                    openapi_schema["paths"][path][method]["description"] = (
                        openapi_schema["paths"][path][method].get("description", "")
                        + "\n\n**Required scope:** `audit:read` (admin only)"
                    )

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# Sprint 46: Initialize telemetry and add middleware
init_telemetry()
app.add_middleware(TelemetryMiddleware)

# Sprint 58 Slice 5: Add request body size limit middleware
app.add_middleware(BodySizeLimitMiddleware)

# CORS configuration (Sprint 50: Hardened headers + expose X-Request-ID/X-Trace-Link)
allowed_origins = [
    "http://localhost:3000",  # Local development
    "https://relay-studio-one.vercel.app",  # Production Studio
]

# Allow all origins in development
if os.getenv("RELAY_ENV") != "production":
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,  # No cookies needed
    allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
    allow_headers=["Content-Type", "Idempotency-Key", "X-Signature", "Authorization"],  # Sprint 50: +Authorization
    expose_headers=[
        "X-Request-ID",
        "X-Trace-Link",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "Retry-After",
    ],  # Sprint 51 P2: +Rate limit headers
    max_age=600,  # Cache preflight for 10 minutes
)

# R2 Phase 3: Register Knowledge API router
app.include_router(knowledge_router)


# Sprint 51 Phase 2: Rate limit exception handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded exceptions with proper headers."""
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


# Sprint 51 Phase 2: Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)

    # HSTS: Force HTTPS for 180 days, include subdomains, preload
    response.headers["Strict-Transport-Security"] = "max-age=15552000; includeSubDomains; preload"

    # CSP: Content security policy for UI + API (Sprint 60 Phase 3)
    csp_directives = [
        "default-src 'self'",
        "connect-src 'self' https://relay-production-f2a6.up.railway.app https://*.vercel.app",
        "img-src 'self' data:",
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net",  # Allow CDN for UI libraries + inline scripts
        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com",  # Tailwind injects styles
        "frame-ancestors 'none'",  # Prevent clickjacking
        "base-uri 'self'",
        "form-action 'self'",
    ]
    response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

    # Referrer policy: Don't leak referrer information
    response.headers["Referrer-Policy"] = "no-referrer"

    # Prevent MIME sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # XSS protection (legacy, but doesn't hurt)
    response.headers["X-XSS-Protection"] = "1; mode=block"

    return response


class TemplateInfo(BaseModel):
    """Template metadata for listing."""

    name: str
    version: str
    description: str
    inputs: list[dict[str, Any]]


class RenderRequest(BaseModel):
    """Request to render a template."""

    template_name: str
    inputs: dict[str, Any]
    output_format: str = "html"  # html, docx, both


class RenderResponse(BaseModel):
    """Response from rendering a template."""

    success: bool
    html: Optional[str] = None
    docx_base64: Optional[str] = None
    artifact_path: Optional[str] = None
    error: Optional[str] = None


class TriageRequest(BaseModel):
    """Request to triage email content via DJP."""

    content: str
    subject: Optional[str] = None
    from_email: Optional[str] = None


class TriageResponse(BaseModel):
    """Response from triaging content."""

    success: bool
    artifact_id: str
    status: str
    provider: str
    preview: str
    artifact_path: str
    error: Optional[str] = None


# Sprint 49 Phase B: Actions feature flag
ACTIONS_ENABLED = os.getenv("ACTIONS_ENABLED", "false").lower() == "true"

# Mount static files for dev UI (Sprint 55 Week 3)
# Try multiple possible locations for static files
static_paths = [
    Path(__file__).parent.parent / "static",  # Development: repo root
    Path("/app/static"),  # Railway/Nixpacks: /app/static
    Path.cwd() / "static",  # Current working directory
]

static_dir = None
for path in static_paths:
    if path.exists() and path.is_dir():
        static_dir = path
        break

if static_dir:
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    print(f"[OK] Mounted static files from: {static_dir}")
else:
    print(f"[WARN] No static directory found. Tried: {[str(p) for p in static_paths]}")


@app.get("/")
def root():
    """API root endpoint."""
    endpoints = {
        "templates": "/api/templates",
        "render": "/api/render",
        "triage": "/api/triage",
        "health": "/_stcore/health",
        "ready": "/ready",
        "version": "/version",
        "metrics": "/metrics",
        "magic": "/magic",
    }

    # Add actions endpoints if enabled
    if ACTIONS_ENABLED:
        endpoints["actions"] = "/actions"
        endpoints["actions_preview"] = "/actions/preview"
        endpoints["actions_execute"] = "/actions/execute"

    return {
        "name": "DJP Workflow API",
        "version": "1.0.0",
        "endpoints": endpoints,
        "features": {
            "actions": ACTIONS_ENABLED,
            "magic_box": True,
        },
    }


@app.get("/_stcore/health")
def health():
    """Health check endpoint."""
    return {"ok": True}


@app.get("/version")
def version():
    """
    Version and build metadata endpoint.

    Returns git SHA, version, and build timestamp.
    """
    import subprocess

    git_sha = "unknown"
    git_branch = "unknown"

    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        pass

    try:
        git_branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        pass

    return {
        "version": app.version,
        "git_sha": git_sha,
        "git_branch": git_branch,
        "build_time": os.environ.get("BUILD_TIME", "unknown"),
        "environment": os.environ.get("RAILWAY_ENVIRONMENT", "local"),
    }


@app.get("/ready")
def ready():
    """
    Readiness check endpoint.

    Returns 200 if service is ready to accept traffic.
    Checks filesystem and basic dependencies.
    """
    checks = {
        "telemetry": False,
        "templates": False,
        "filesystem": False,
        "redis": False,
    }

    # Check telemetry initialized
    try:
        from .telemetry.prom import generate_metrics_text

        metrics = generate_metrics_text()
        checks["telemetry"] = len(metrics) > 0
    except Exception:
        pass

    # Check templates loadable
    try:
        templates = list_templates()
        checks["templates"] = len(templates) > 0
    except Exception:
        pass

    # Check filesystem writable
    try:
        artifact_dir = Path("runs/api")
        artifact_dir.mkdir(parents=True, exist_ok=True)
        test_file = artifact_dir / ".readiness_check"
        test_file.write_text("ok")
        test_file.unlink()
        checks["filesystem"] = True
    except Exception:
        pass

    # Check Redis connection (optional - used for rate limiting and OAuth caching)
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis

            client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
            client.ping()
            checks["redis"] = True
        except Exception:
            # Redis is optional - service can run without it (uses in-process fallback)
            checks["redis"] = False
    else:
        # Redis not configured - mark as true since it's optional
        checks["redis"] = True

    all_ready = all(checks.values())

    return {
        "ready": all_ready,
        "checks": checks,
    }


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus text exposition format.
    If telemetry is disabled or prometheus-client is not installed,
    returns empty response.

    Sprint 46: Phase 1 (Metrics) implementation.
    """
    from .telemetry.prom import generate_metrics_text

    return generate_metrics_text()


@app.get("/api/templates", response_model=list[TemplateInfo])
def get_templates():
    """
    List available templates.

    Returns:
        List of template metadata with inputs schema
    """
    try:
        templates = list_templates()

        return [
            TemplateInfo(
                name=t.name,
                version=t.version,
                description=t.description,
                inputs=[
                    {
                        "id": inp.id,
                        "label": inp.label,
                        "type": inp.type,
                        "required": inp.required,
                        "help": getattr(inp, "help", ""),
                        "enum": getattr(inp, "enum", None),
                    }
                    for inp in t.inputs
                ],
            )
            for t in templates
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list templates: {str(e)}") from e


@app.post("/api/render", response_model=RenderResponse)
def render_template(request: RenderRequest):
    """
    Render a template with provided inputs.

    Args:
        request: Template name, inputs, and output format

    Returns:
        Rendered HTML and/or DOCX (base64 encoded)
    """
    try:
        # Get template
        templates = list_templates()
        template = next((t for t in templates if t.name == request.template_name), None)

        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{request.template_name}' not found")

        # Render template
        rendered = render_template_content(template, request.inputs)

        # Generate HTML
        html_content = None
        if request.output_format in ("html", "both"):
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 20px; }}
        h1, h2, h3 {{ color: #333; }}
        pre {{ background: #f4f4f4; padding: 10px; border-radius: 4px; }}
    </style>
</head>
<body>
{rendered}
</body>
</html>
"""

        # Generate DOCX (stub - would use python-docx in production)
        docx_base64 = None
        if request.output_format in ("docx", "both"):
            # Placeholder: In production, use python-docx to create proper DOCX
            # For now, return base64-encoded text content
            docx_base64 = b64encode(rendered.encode("utf-8")).decode("ascii")

        # Save dry-run artifact
        artifact_dir = Path("runs/api")
        artifact_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        artifact_path = artifact_dir / f"render-{timestamp}.html"

        if html_content:
            artifact_path.write_text(html_content, encoding="utf-8")

        return RenderResponse(
            success=True,
            html=html_content,
            docx_base64=docx_base64,
            artifact_path=str(artifact_path),
        )

    except HTTPException:
        raise
    except Exception as e:
        return RenderResponse(success=False, error=str(e))


@app.post("/api/triage", response_model=TriageResponse)
async def triage_content(request: TriageRequest):
    """
    Triage email content via DJP workflow.

    Args:
        request: Email content and metadata

    Returns:
        DJP result with artifact path
    """
    try:
        # Check if real mode is available
        real_mode = bool(os.environ.get("OPENAI_API_KEY"))

        if real_mode:
            # Run real DJP workflow
            from .debate import run_debate
            from .judge import judge_drafts
            from .publish import select_publish_text

            # Construct task prompt
            task = f"Analyze and summarize this email:\n\n{request.content}"
            if request.subject:
                task = f"Subject: {request.subject}\n\n" + task

            # Run workflow
            drafts = await run_debate(
                task=task,
                max_tokens=1000,
                temperature=0.3,
                corpus_docs=None,
                allowed_models=["openai/gpt-4o", "anthropic/claude-3-5-sonnet-20241022"],
            )

            judgment = await judge_drafts(drafts=drafts, task=task, require_citations=0)

            status, provider, text, reason, redaction_meta = select_publish_text(
                judgment, drafts, allowed_models=["openai/gpt-4o", "anthropic/claude-3-5-sonnet-20241022"]
            )

        else:
            # Mock mode
            status = "published"
            provider = "mock/gpt-4o"
            text = f"[Mock analysis]\n\nThis email appears to be about: {request.subject or 'general inquiry'}\n\nKey points:\n1. Content received\n2. Analysis pending\n3. Mock response generated"
            reason = ""

        # Save artifact
        artifact_dir = Path("runs/api/triage")
        artifact_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        artifact_id = f"triage-{timestamp}"
        artifact_path = artifact_dir / f"{artifact_id}.json"

        import json

        artifact_data = {
            "artifact_id": artifact_id,
            "timestamp": datetime.now().isoformat(),
            "request": {
                "content": request.content[:500],  # Truncate for storage
                "subject": request.subject,
                "from_email": request.from_email,
            },
            "result": {"status": status, "provider": provider, "text": text, "reason": reason},
        }

        artifact_path.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")

        return TriageResponse(
            success=True,
            artifact_id=artifact_id,
            status=status,
            provider=provider,
            preview=text[:300] + "..." if len(text) > 300 else text,
            artifact_path=str(artifact_path),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Triage failed: {str(e)}") from e


# ============================================================================
# Sprint 49 Phase B: Actions Endpoints
# ============================================================================


@app.get("/actions")
def list_actions(request: Request):
    """
    List available actions.

    Returns list of action definitions with schemas.
    Requires ACTIONS_ENABLED=true.
    """
    if not ACTIONS_ENABLED:
        raise HTTPException(status_code=404, detail="Actions feature not enabled")

    from .actions import get_executor

    executor = get_executor()
    actions = executor.list_actions()

    return {
        "actions": actions,
        "request_id": request.state.request_id if hasattr(request.state, "request_id") else str(uuid4()),
    }


@app.post("/actions/preview")
@require_scopes(["actions:preview"])
async def preview_action(
    request: Request,
    body: dict[str, Any],
):
    """
    Preview an action before execution.

    Returns preview_id for use in /actions/execute.
    Requires ACTIONS_ENABLED=true.
    Requires scope: actions:preview
    """
    import time

    from .actions import PreviewRequest, get_executor
    from .audit.logger import write_audit

    if not ACTIONS_ENABLED:
        raise HTTPException(status_code=404, detail="Actions feature not enabled")

    start_time = time.time()
    status = "ok"
    error_reason = "none"
    http_status = 200
    preview_result = None

    try:
        preview_req = PreviewRequest(**body)
        executor = get_executor()
        preview = executor.preview(preview_req.action, preview_req.params)
        preview_result = preview

        return {
            **preview.model_dump(),
            "request_id": request.state.request_id if hasattr(request.state, "request_id") else str(uuid4()),
        }

    except ValueError as e:
        status = "error"
        error_reason = "validation"
        http_status = 400
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        status = "error"
        error_reason = "other"
        http_status = 500
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}") from e
    finally:
        # Write audit log
        duration_ms = int((time.time() - start_time) * 1000)

        # Extract action details
        try:
            action = body.get("action", "unknown")
            params = body.get("params", {})

            # Parse provider and action_id
            if "." in action:
                parts = action.split(".", 1)
                provider = parts[0]
                action_id = parts[1] if len(parts) > 1 else action
            else:
                provider = "unknown"
                action_id = action

            request_id = request.state.request_id if hasattr(request.state, "request_id") else str(uuid4())
            workspace_id = request.state.workspace_id if hasattr(request.state, "workspace_id") else uuid4()
            actor_type = request.state.actor_type if hasattr(request.state, "actor_type") else "user"
            actor_id = request.state.actor_id if hasattr(request.state, "actor_id") else "unknown"
            signature_present = "X-Signature" in request.headers

            await write_audit(
                run_id=None,  # Preview has no run_id
                request_id=request_id,
                workspace_id=workspace_id,
                actor_type=actor_type,
                actor_id=actor_id,
                provider=provider,
                action_id=action_id,
                preview_id=preview_result.preview_id if preview_result else None,
                idempotency_key=None,  # Preview doesn't use idempotency
                signature_present=signature_present,
                params=params,
                status=status,
                error_reason=error_reason,
                http_status=http_status,
                duration_ms=duration_ms,
            )
        except Exception:
            # Audit logging failure should not break the request
            pass


@app.post("/actions/execute")
@require_scopes(["actions:execute"])
async def execute_action(
    request: Request,
    body: dict[str, Any],
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """
    Execute a previewed action.

    Requires preview_id from /actions/preview.
    Optionally accepts Idempotency-Key header for deduplication.
    Requires ACTIONS_ENABLED=true.
    Requires scope: actions:execute
    """
    import time

    from .actions import get_executor
    from .audit.logger import write_audit

    if not ACTIONS_ENABLED:
        raise HTTPException(status_code=404, detail="Actions feature not enabled")

    start_time = time.time()
    status = "ok"
    error_reason = "none"
    http_status = 200
    execute_result = None
    preview_id = body.get("preview_id")
    final_idempotency_key = idempotency_key or body.get("idempotency_key")

    try:
        # Parse request
        if not preview_id:
            status = "error"
            error_reason = "validation"
            http_status = 400
            raise HTTPException(status_code=400, detail="preview_id required")

        # Get workspace_id from auth context
        workspace_id = request.state.workspace_id if hasattr(request.state, "workspace_id") else "default"

        # Get actor_id from auth context
        actor_id = request.state.actor_id if hasattr(request.state, "actor_id") else "system"

        # Get request ID from telemetry middleware
        request_id = request.state.request_id if hasattr(request.state, "request_id") else str(uuid4())

        # Check rate limit (per workspace)
        limiter = get_rate_limiter()
        limiter.check_limit(workspace_id)

        # Execute
        executor = get_executor()
        result = await executor.execute(
            preview_id=preview_id,
            idempotency_key=final_idempotency_key,
            workspace_id=workspace_id,
            actor_id=actor_id,
            request_id=request_id,
        )
        execute_result = result

        return result.model_dump()

    except ValueError as e:
        status = "error"
        error_reason = "validation"
        http_status = 400
        raise HTTPException(status_code=400, detail=str(e)) from e
    except NotImplementedError as e:
        status = "error"
        error_reason = "provider_unconfigured"
        http_status = 501
        raise HTTPException(status_code=501, detail=str(e)) from e
    except TimeoutError as e:
        status = "error"
        error_reason = "timeout"
        http_status = 504
        raise HTTPException(status_code=504, detail=f"Execution timeout: {str(e)}") from e
    except Exception as e:
        status = "error"
        # Check if it's a 5xx from downstream
        if "5" in str(e) and "xx" in str(e).lower():
            error_reason = "downstream_5xx"
        else:
            error_reason = "other"
        http_status = 500
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}") from e
    finally:
        # Write audit log
        duration_ms = int((time.time() - start_time) * 1000)

        # Extract action details from execute result or preview store
        try:
            # Get action info from result or try to extract from body
            if execute_result:
                provider = execute_result.provider
                action_id = execute_result.action
                run_id = execute_result.run_id
            else:
                # Fallback if result not available
                provider = "unknown"
                action_id = "unknown"
                run_id = None

            # Reconstruct params (not available in execute, use empty dict)
            params = body.copy()
            params.pop("preview_id", None)
            params.pop("idempotency_key", None)

            request_id = request.state.request_id if hasattr(request.state, "request_id") else str(uuid4())
            workspace_id = request.state.workspace_id if hasattr(request.state, "workspace_id") else uuid4()
            actor_type = request.state.actor_type if hasattr(request.state, "actor_type") else "user"
            actor_id = request.state.actor_id if hasattr(request.state, "actor_id") else "unknown"
            signature_present = "X-Signature" in request.headers

            await write_audit(
                run_id=run_id,
                request_id=request_id,
                workspace_id=workspace_id,
                actor_type=actor_type,
                actor_id=actor_id,
                provider=provider,
                action_id=action_id,
                preview_id=preview_id,
                idempotency_key=final_idempotency_key,
                signature_present=signature_present,
                params=params if params else {},
                status=status,
                error_reason=error_reason,
                http_status=http_status,
                duration_ms=duration_ms,
            )
        except Exception:
            # Audit logging failure should not break the request
            pass


@app.get("/audit")
@require_scopes(["audit:read"])
async def get_audit_logs(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    provider: Optional[str] = None,
    action_id: Optional[str] = None,
    status: Optional[str] = None,
    actor_type: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
):
    """
    Query audit logs (admin only).

    Requires scope: audit:read

    Args:
        limit: Number of records to return (1-200, default 50)
        offset: Offset for pagination (>=0, default 0)
        provider: Filter by provider (e.g., 'independent')
        action_id: Filter by action ID (e.g., 'webhook.save')
        status: Filter by status ('ok' or 'error')
        actor_type: Filter by actor type ('user' or 'api_key')
        from_date: Start date (ISO8601)
        to_date: End date (ISO8601)

    Returns:
        List of audit log entries (redacted, no secrets)
    """
    from datetime import datetime

    from src.db.connection import get_connection

    # Validate limit
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")

    # Validate offset
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")

    # Validate status enum
    if status and status not in ["ok", "error"]:
        raise HTTPException(status_code=400, detail="status must be 'ok' or 'error'")

    # Validate actor_type enum
    if actor_type and actor_type not in ["user", "api_key"]:
        raise HTTPException(status_code=400, detail="actor_type must be 'user' or 'api_key'")

    # Get workspace_id from auth context
    workspace_id = request.state.workspace_id if hasattr(request.state, "workspace_id") else None
    if not workspace_id:
        raise HTTPException(status_code=403, detail="workspace_id not found in auth context")

    # Build query
    query = """
        SELECT
            id,
            run_id,
            request_id,
            workspace_id,
            actor_type,
            actor_id,
            provider,
            action_id,
            preview_id,
            signature_present,
            params_prefix64,
            status,
            error_reason,
            http_status,
            duration_ms,
            created_at
        FROM action_audit
        WHERE workspace_id = $1
    """
    params = [workspace_id]
    param_idx = 2

    # Add filters
    if provider:
        query += f" AND provider = ${param_idx}"
        params.append(provider)
        param_idx += 1

    if action_id:
        query += f" AND action_id = ${param_idx}"
        params.append(action_id)
        param_idx += 1

    if status:
        query += f" AND status = ${param_idx}::audit_status_enum"
        params.append(status)
        param_idx += 1

    if actor_type:
        query += f" AND actor_type = ${param_idx}::actor_type_enum"
        params.append(actor_type)
        param_idx += 1

    if from_date:
        try:
            from_dt = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
            query += f" AND created_at >= ${param_idx}"
            params.append(from_dt)
            param_idx += 1
        except ValueError:
            raise HTTPException(status_code=400, detail="from_date must be valid ISO8601") from None

    if to_date:
        try:
            to_dt = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
            query += f" AND created_at <= ${param_idx}"
            params.append(to_dt)
            param_idx += 1
        except ValueError:
            raise HTTPException(status_code=400, detail="to_date must be valid ISO8601") from None

    # Order by created_at DESC (uses index)
    query += " ORDER BY created_at DESC"

    # Pagination
    query += f" LIMIT ${param_idx} OFFSET ${param_idx + 1}"
    params.append(limit)
    params.append(offset)

    # Execute query
    async with get_connection() as conn:
        rows = await conn.fetch(query, *params)

    # Convert to dict list (redacted - no params_hash, no idempotency_key_hash)
    items = [
        {
            "id": str(row["id"]),
            "run_id": row["run_id"],
            "request_id": row["request_id"],
            "workspace_id": str(row["workspace_id"]),
            "actor_type": row["actor_type"],
            "actor_id": row["actor_id"],
            "provider": row["provider"],
            "action_id": row["action_id"],
            "preview_id": row["preview_id"],
            "signature_present": row["signature_present"],
            "params_prefix64": row["params_prefix64"],
            "status": row["status"],
            "error_reason": row["error_reason"],
            "http_status": row["http_status"],
            "duration_ms": row["duration_ms"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]

    # Calculate next_offset
    next_offset = offset + len(items) if len(items) == limit else None

    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        "next_offset": next_offset,
        "count": len(items),
    }


# ============================================================================
# OAuth Endpoints - Sprint 53 Phase B
# ============================================================================


@app.get("/oauth/google/authorize")
async def oauth_google_authorize(
    request: Request,
    workspace_id: str,
    redirect_uri: Optional[str] = None,
):
    """
    Initiate Google OAuth flow.

    Args:
        workspace_id: Workspace UUID
        redirect_uri: Optional redirect URI (defaults to RELAY_PUBLIC_BASE_URL/oauth/google/callback)

    Returns:
        authorize_url: Google OAuth authorization URL with state parameter
    """
    import urllib.parse

    from src.auth.oauth.state import OAuthStateManager

    # Get environment variables
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=501, detail="Google OAuth not configured (GOOGLE_CLIENT_ID missing)")

    # Default redirect URI
    if not redirect_uri:
        base_url = os.getenv("RELAY_PUBLIC_BASE_URL", "https://relay-production-f2a6.up.railway.app")
        redirect_uri = f"{base_url}/oauth/google/callback"

    # Create state with PKCE
    state_mgr = OAuthStateManager()
    state_data = state_mgr.create_state(
        workspace_id=workspace_id, provider="google", redirect_uri=redirect_uri, use_pkce=True
    )

    # Build Google OAuth URL
    auth_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/gmail.send openid email profile",
        "state": state_data["state"],
        "code_challenge": state_data["code_challenge"],
        "code_challenge_method": "S256",
        "access_type": "offline",  # Request refresh token
        # Note: prompt=consent not compatible with OAuth apps in test mode
    }

    authorize_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(auth_params)}"

    # Emit metric
    from src.telemetry import oauth_events

    oauth_events.labels(provider="google", event="authorize_started").inc()

    return {
        "authorize_url": authorize_url,
        "state": state_data["state"],
        "expires_in": 600,  # State valid for 10 minutes
    }


@app.get("/oauth/google/callback")
async def oauth_google_callback(
    request: Request,
    code: str,
    state: str,
    error: Optional[str] = None,
):
    """
    Handle Google OAuth callback.

    Args:
        code: Authorization code from Google
        state: State token for CSRF protection (contains workspace_id)
        error: Optional error from Google

    Returns:
        success: True if tokens stored successfully
        scopes: Granted OAuth scopes
    """
    import httpx

    from src.auth.oauth.tokens import OAuthTokenCache

    # Check for OAuth error
    if error:
        from src.telemetry import oauth_events

        oauth_events.labels(provider="google", event="callback_error").inc()
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    # Sprint 54: Validate state and retrieve context
    from src.auth.oauth.state import validate_and_retrieve_context

    state_context = validate_and_retrieve_context(state)
    if not state_context:
        from src.telemetry import oauth_events

        oauth_events.labels(provider="google", event="invalid_state").inc()
        raise HTTPException(status_code=400, detail="Invalid or expired state token")

    # Extract workspace_id, actor_id, pkce_verifier from state context
    workspace_id = state_context["workspace_id"]
    actor_id = state_context["actor_id"]
    pkce_verifier = state_context["pkce_verifier"]
    state_data = state_context.get("extra", {})

    # Get environment variables
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")

    # Exchange code for tokens
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": state_data.get("redirect_uri", ""),
        "grant_type": "authorization_code",
        "code_verifier": pkce_verifier,  # PKCE from state context
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(token_url, data=token_data)
            if response.status_code != 200:
                from src.telemetry import oauth_events

                oauth_events.labels(provider="google", event="token_exchange_failed").inc()
                raise HTTPException(
                    status_code=502, detail=f"Token exchange failed: {response.status_code} {response.text[:200]}"
                )

            token_response = response.json()
    except httpx.TimeoutException as e:
        from src.telemetry import oauth_events

        oauth_events.labels(provider="google", event="token_exchange_timeout").inc()
        raise HTTPException(status_code=504, detail="Token exchange timeout") from e

    # Extract tokens
    access_token = token_response.get("access_token")
    refresh_token = token_response.get("refresh_token")
    expires_in = token_response.get("expires_in")
    scope = token_response.get("scope")

    if not access_token:
        from src.telemetry import oauth_events

        oauth_events.labels(provider="google", event="missing_access_token").inc()
        raise HTTPException(status_code=502, detail="No access token in response")

    # Store tokens (encrypted) - actor_id from state context
    token_cache = OAuthTokenCache()
    await token_cache.store_tokens(
        provider="google",
        workspace_id=workspace_id,
        actor_id=actor_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        scope=scope,
    )

    # Emit metric
    from src.telemetry import oauth_events

    oauth_events.labels(provider="google", event="tokens_stored").inc()

    return {"success": True, "scopes": scope, "has_refresh_token": bool(refresh_token)}


@app.get("/oauth/google/status")
async def oauth_google_status(
    request: Request,
    workspace_id: str,
):
    """
    Check if workspace has Google OAuth connection.

    Args:
        workspace_id: Workspace UUID

    Returns:
        linked: True if OAuth tokens exist for this workspace
        scopes: Granted OAuth scopes (if linked)
    """
    from src.auth.oauth.tokens import OAuthTokenCache

    # TODO: Get actor_id from request context
    actor_id = "user_temp_001"

    token_cache = OAuthTokenCache()
    tokens = await token_cache.get_tokens(provider="google", workspace_id=workspace_id, actor_id=actor_id)

    if tokens:
        return {"linked": True, "scopes": tokens.get("scope", "")}
    else:
        return {"linked": False, "scopes": None}


# ============================================================================
# Sprint 55 Week 3: AI Agent Endpoints
# ============================================================================


@app.post("/ai/plan")
@require_scopes(["actions:preview"])
async def plan_with_ai(
    request: Request,
    body: dict[str, Any],
):
    """
    Generate action plan from natural language prompt with RBAC filtering.

    Args:
        prompt: Natural language description of what to do
        context: Optional context (calendar, email history, etc.)

    Returns:
        Structured action plan with steps (filtered by user permissions)

    Requires scope: actions:preview
    """
    from src.ai import ActionPlanner
    from src.ai.orchestrator import get_orchestrator

    if not ACTIONS_ENABLED:
        raise HTTPException(status_code=404, detail="Actions feature not enabled")

    prompt = body.get("prompt")
    context = body.get("context")

    if not prompt:
        raise HTTPException(status_code=400, detail="prompt required")

    # Get user_id from auth context for RBAC filtering
    user_id = request.state.actor_id if hasattr(request.state, "actor_id") else "system"

    # Generate plan with orchestrator (applies RBAC guards)
    planner = ActionPlanner()
    orchestrator = get_orchestrator()
    plan, plan_id = await orchestrator.plan(user_id, prompt, planner, context)

    # Return plan with sensitive data redacted
    return {
        **plan.model_dump(),  # Uses model_dump() for Pydantic models
        "plan_id": plan_id,  # Correlation ID for job tracking
        "request_id": request.state.request_id if hasattr(request.state, "request_id") else str(uuid4()),
    }


@app.post("/ai/plan2")
@require_scopes(["actions:preview"])
async def plan_with_ai_v2(
    request: Request,
    body: dict[str, Any],
):
    """
    AI Orchestrator v0.1: Generate action plan with strict JSON schema and cost control.

    Args:
        prompt: Natural language description (e.g., "Send email to john@example.com thanking him for the meeting")

    Returns:
        {
          "plan": PlanResult with strict schema,
          "meta": {"model": "gpt-4o-mini", "duration": 1.23, "tokens_in": 150, "tokens_out": 200}
        }

    Recommended over /ai/plan for production use.
    Requires scope: actions:preview
    """
    from src.ai.planner_v2 import plan_actions

    if not ACTIONS_ENABLED:
        raise HTTPException(status_code=404, detail="Actions feature not enabled")

    prompt = body.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing 'prompt' field")

    try:
        # Plan with v2 planner (strict JSON + cost control)
        plan, meta = plan_actions(prompt)

        return {
            "plan": plan.model_dump(),
            "meta": meta,
        }

    except ValueError as e:
        # Configuration or validation error
        raise HTTPException(status_code=400, detail=str(e)) from e

    except Exception as e:
        # Unexpected error
        raise HTTPException(status_code=500, detail=f"Planning failed: {str(e)}") from e


@app.post("/ai/execute")
@require_scopes(["actions:execute"])
async def execute_ai_plan(
    request: Request,
    body: dict[str, Any],
):
    """
    AI Orchestrator v0.1: Enqueue planned actions for async execution.

    Args:
        actions: List of PlannedAction from /ai/plan2
        workspace_id: Optional workspace ID (defaults to request context)
        actor_id: Optional actor ID (defaults to request context)

    Returns:
        {
          "job_ids": ["job-uuid-1", "job-uuid-2"],
          "queue_depth": 5
        }

    Requires scope: actions:execute
    """
    from src.queue.simple_queue import SimpleQueue
    from src.security.permissions import can_execute
    from src.telemetry.prom import ai_jobs_total

    if not ACTIONS_ENABLED:
        raise HTTPException(status_code=404, detail="Actions feature not enabled")

    # Parse request
    actions = body.get("actions")
    if not actions:
        raise HTTPException(status_code=400, detail="Missing 'actions' field")

    # Sprint 60 Phase 2: Workspace isolation enforcement (CRITICAL-3)
    from src.security.workspace import ensure_same_workspace, get_authenticated_workspace

    auth_workspace_id = get_authenticated_workspace(request)
    body_workspace_id = body.get("workspace_id")
    ensure_same_workspace(auth_workspace_id, body_workspace_id)

    # Get context - always use authenticated workspace (not client-provided)
    workspace_id = auth_workspace_id
    actor_id = body.get("actor_id") or (request.state.actor_id if hasattr(request.state, "actor_id") else "system")

    # Initialize queue
    try:
        queue = SimpleQueue()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"Queue unavailable: {str(e)}") from e

    # Enqueue each action
    job_ids = []
    for action in actions:
        action_name = action.get("action")
        action_provider = action.get("provider")
        params = action.get("params", {})
        client_request_id = action.get("client_request_id")

        # Check permissions
        if not can_execute(action_name):
            raise HTTPException(status_code=403, detail=f"Action '{action_name}' not allowed")

        # Generate job ID
        job_id = str(uuid4())

        # Enqueue
        was_enqueued = queue.enqueue(
            job_id=job_id,
            action_provider=action_provider,
            action_name=action_name,
            params=params,
            workspace_id=workspace_id,
            actor_id=actor_id,
            client_request_id=client_request_id,
        )

        if was_enqueued:
            job_ids.append(job_id)
            ai_jobs_total.labels(workspace_id=workspace_id, status="pending").inc()
        else:
            # Idempotency hit - return existing job_id
            # (SimpleQueue.enqueue returns False on duplicate)
            pass

    return {
        "job_ids": job_ids,
        "queue_depth": queue.get_queue_depth(),
    }


@app.get("/ai/jobs")
@require_scopes(["actions:preview"])
async def list_ai_jobs(
    request: Request,
    limit: int = 50,
    workspace_id: str | None = None,
):
    """
    AI Orchestrator v0.1: List recent jobs (workspace-scoped).

    Args:
        limit: Maximum number of jobs to return (1-100, default 50)
        workspace_id: Optional workspace filter (must match authenticated workspace)

    Returns:
        {
          "jobs": [{"job_id": "uuid", "status": "completed", ...}],
          "count": 10,
          "queue_depth": 5
        }

    Security: Only returns jobs for authenticated workspace.
    Requires scope: actions:preview
    """
    if not ACTIONS_ENABLED:
        raise HTTPException(status_code=404, detail="Actions feature not enabled")

    # Sprint 60 Phase 2: Workspace isolation enforcement (CRITICAL-2, HIGH-4)
    from src.security.workspace import ensure_same_workspace, get_authenticated_workspace

    auth_workspace_id = get_authenticated_workspace(request)
    ensure_same_workspace(auth_workspace_id, workspace_id)

    # Validate limit
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")

    # Initialize queue
    try:
        from src.queue.simple_queue import SimpleQueue

        queue = SimpleQueue()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"Queue unavailable: {str(e)}") from e

    # Sprint 60 Phase 2.2: Use queue.list_jobs() for read-routing and workspace isolation
    try:
        # Get jobs using workspace-scoped list (handles read-routing + isolation)
        result = queue.list_jobs(workspace_id=auth_workspace_id, limit=limit)
        jobs_data = result["items"]

        # Format jobs for API response
        jobs = []
        for job_data in jobs_data:
            # Calculate duration if finished
            duration_ms = None
            if job_data.get("finished_at") and job_data.get("started_at"):
                from datetime import datetime

                started = datetime.fromisoformat(job_data["started_at"])
                finished = datetime.fromisoformat(job_data["finished_at"])
                duration_ms = int((finished - started).total_seconds() * 1000)

            jobs.append(
                {
                    "job_id": job_data.get("job_id"),
                    "status": job_data.get("status"),
                    "action": f"{job_data.get('action_provider')}.{job_data.get('action_name')}",
                    "result": job_data.get("result"),
                    "error": job_data.get("error"),
                    "duration_ms": duration_ms,
                    "enqueued_at": job_data.get("enqueued_at"),
                    "started_at": job_data.get("started_at"),
                    "finished_at": job_data.get("finished_at"),
                }
            )

        return {
            "jobs": jobs[:limit],
            "count": len(jobs),
            "queue_depth": queue.get_queue_depth(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list jobs: {str(e)}") from e


@app.get("/ai/jobs/{job_id}")
@require_scopes(["actions:preview"])
async def get_ai_job_status(
    request: Request,
    job_id: str,
):
    """
    AI Orchestrator v0.1: Get job status and result.

    Args:
        job_id: Job identifier from /ai/execute

    Returns:
        {
          "job_id": "uuid",
          "status": "pending|running|completed|error",
          "result": {...},
          "error": null,
          "duration_ms": 1234
        }

    Requires scope: actions:preview
    """
    from src.queue.simple_queue import SimpleQueue

    if not ACTIONS_ENABLED:
        raise HTTPException(status_code=404, detail="Actions feature not enabled")

    # Sprint 60 Phase 2: Workspace isolation enforcement
    from src.security.workspace import get_authenticated_workspace

    auth_workspace_id = get_authenticated_workspace(request)

    # Initialize queue
    try:
        queue = SimpleQueue()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"Queue unavailable: {str(e)}") from e

    # Get job data - Sprint 60 Phase 2.2: Pass workspace_id for read-routing
    job_data = queue.get_job(job_id, workspace_id=auth_workspace_id)

    if not job_data:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    # Validate workspace isolation: reject cross-workspace access with 403 (not 404)
    # Use helper for consistency with other endpoints
    from src.security.workspace import ensure_same_workspace

    job_workspace_id = job_data.get("workspace_id")
    ensure_same_workspace(auth_workspace_id, job_workspace_id)

    # Calculate duration if finished
    duration_ms = None
    if job_data.get("finished_at") and job_data.get("started_at"):
        from datetime import datetime

        started = datetime.fromisoformat(job_data["started_at"])
        finished = datetime.fromisoformat(job_data["finished_at"])
        duration_ms = int((finished - started).total_seconds() * 1000)

    return {
        "job_id": job_id,
        "status": job_data.get("status"),
        "action": f"{job_data.get('action_provider')}.{job_data.get('action_name')}",
        "result": job_data.get("result"),
        "error": job_data.get("error"),
        "duration_ms": duration_ms,
        "enqueued_at": job_data.get("enqueued_at"),
        "started_at": job_data.get("started_at"),
        "finished_at": job_data.get("finished_at"),
    }


# ============================================================================
# Dev Mode Endpoints - Sprint 55 Week 3
# ============================================================================


@app.get("/dev/outbox")
def get_demo_outbox():
    """
    List demo mode outbox (emails saved instead of sent).

    Returns list of saved email artifacts for testing.
    """
    outbox_dir = Path("runs/dev/outbox")
    if not outbox_dir.exists():
        return {"items": []}

    import json

    items = []
    for file_path in sorted(outbox_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(file_path.read_text())
            items.append(data)
        except Exception:
            pass

    return {"items": items, "count": len(items)}


# ============================================================================
# Sprint 61a: Magic Box Interface & SSE Streaming
# ============================================================================


class SSEEventBuffer:
    """Buffer for SSE events with backpressure handling."""

    def __init__(self, max_buffer_size: int = 1000, backpressure_timeout: float = 30.0):
        self.buffer = asyncio.Queue(maxsize=max_buffer_size)
        self.backpressure_timeout = backpressure_timeout
        self.last_event_id = -1

    async def send_event(self, event_type: str, data: dict, event_id: int) -> bool:
        """
        Queue an event. Returns False if backpressure detected (client stalled).
        """
        event = {"event": event_type, "id": event_id, "data": json.dumps(data)}
        try:
            # Try to add with timeout to detect stalled clients
            self.buffer.put_nowait(event)
            return True
        except asyncio.QueueFull:
            # Buffer full - client is stalled
            return False

    async def get_event(self) -> dict:
        """Get next event from buffer."""
        return await asyncio.wait_for(self.buffer.get(), timeout=self.backpressure_timeout)


class SSEStreamState:
    """Tracks per-stream state for deduplication and recovery."""

    def __init__(self, stream_id: str):
        self.stream_id = stream_id
        self.event_id = 0
        self.last_acked_id = -1
        self.created_at = time.time()
        self.chunks_sent = []
        self.is_closed = False

    def next_event_id(self) -> int:
        """Get next event ID (monotonically increasing)."""
        event_id = self.event_id
        self.event_id += 1
        return event_id

    def add_chunk(self, content: str, tokens: int, cost: float) -> None:
        """Record a chunk for potential replay."""
        self.chunks_sent.append({"event_id": self.event_id - 1, "content": content, "tokens": tokens, "cost": cost})

    def get_chunks_after(self, last_event_id: int) -> list:
        """Get all chunks after given event ID for replay."""
        return [chunk for chunk in self.chunks_sent if chunk["event_id"] > last_event_id]


# Global stream state (in production: use Redis)
_stream_states = {}


def get_stream_state(stream_id: str) -> SSEStreamState:
    """Get or create stream state."""
    if stream_id not in _stream_states:
        _stream_states[stream_id] = SSEStreamState(stream_id)
    return _stream_states[stream_id]


async def format_sse_event(event_type: str, data: dict, event_id: int) -> str:
    """Format event as SSE (Server-Sent Events) format."""
    sse = f"event: {event_type}\n"
    sse += f"id: {event_id}\n"
    sse += "retry: 10000\n"  # 10 second retry for stalled clients
    sse += f"data: {json.dumps(data)}\n\n"
    return sse


@app.post("/api/v1/anon_session")
async def create_anon_session():
    """Create anonymous session token (7-day TTL)."""
    try:
        from .stream.auth import generate_anon_session_token

        token, expires_at = generate_anon_session_token()
        return {
            "token": token,
            "expires_at": expires_at,
            "expires_in": 604800,  # 7 days in seconds
        }
    except Exception as e:
        import traceback

        print(f"Error creating anon session: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error creating session: {str(e)}",
        ) from e


@app.get("/api/v1/stream")
@app.post("/api/v1/stream")
async def stream_response(
    request: Request,
    user_id: Optional[str] = None,
    message: Optional[str] = None,
    model: Optional[str] = None,
    stream_id: Optional[str] = None,
    last_event_id: Optional[int] = None,
    body: Optional[dict[str, Any]] = None,
) -> Any:
    """
    SSE streaming endpoint for Magic Box.

    Handles:
    - Message streaming with incremental event IDs
    - Last-Event-ID recovery and replay
    - Heartbeat for stalled connection detection
    - Backpressure detection and graceful closure

    Accepts both GET (query params) and POST (JSON body):
    - user_id: "anon_xxx"
    - message: "Your prompt here"
    - model: "gpt-4o-mini"
    - stream_id: "stream_xxx" (optional, auto-generated if missing)
    - last_event_id: last event ID for recovery

    Response: SSE stream with events:
    - event: message_chunk (incremental content)
    - event: heartbeat (keep-alive)
    - event: done (completion)
    """
    from fastapi.responses import StreamingResponse

    # Authenticate via Authorization header or reject with 401
    auth_header = request.headers.get("Authorization", "")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header",
        )

    # Verify JWT token and extract principal (deferred import)
    from .stream.auth import verify_supabase_jwt

    token = auth_header.split(" ", 1)[1]
    principal = await verify_supabase_jwt(token)

    # For POST, extract from JSON body
    if request.method == "POST" and body:
        message = message or body.get("message", "")
        model = model or body.get("model", "gpt-4o-mini")
        stream_id = stream_id or body.get("stream_id")
        last_event_id = last_event_id or body.get("last_event_id")

    # Use authenticated user_id from principal
    user_id = principal.user_id
    message = message or ""
    model = model or "gpt-4o-mini"
    stream_id = stream_id or str(uuid4())

    if not message:
        raise HTTPException(status_code=400, detail="message required")

    # Validate message length and model
    if len(message) > 8192:
        raise HTTPException(status_code=422, detail="Message too long (max 8192 characters)")

    valid_models = ["gpt-4o-mini", "gpt-4", "gpt-4-turbo", "claude-3-5-sonnet", "claude-3-opus"]
    if model not in valid_models:
        raise HTTPException(status_code=422, detail=f"Invalid model: {model}. Valid models: {valid_models}")

    # Check rate limits (per-user and per-IP) - deferred import
    try:
        from .stream.limits import RateLimiter

        client_ip = request.client.host if request.client else "0.0.0.0"
        limiter = RateLimiter()

        # Check rate limits (raises HTTPException 429 if exceeded)
        await limiter.check_rate_limit(user_id, client_ip)

        # Check quotas for anonymous users (raises HTTPException 429 if exceeded)
        if principal.is_anonymous:
            await limiter.check_anonymous_quotas(principal.user_id)
    except HTTPException:
        raise  # Re-raise auth/rate limit exceptions
    except Exception as e:
        # Log but don't fail on rate limiter connection issues during development
        import traceback

        print(f"[WARN] Rate limiter check failed (non-blocking): {e}")
        traceback.print_exc()

    # Get stream state
    state = get_stream_state(stream_id)

    # Determine starting point for replay
    replay_from_id = last_event_id if last_event_id is not None else -1

    async def generate_sse_stream() -> AsyncIterator[str]:
        """Generate SSE stream with backpressure handling."""
        try:
            # Emit replay of previous chunks if reconnecting
            if replay_from_id >= 0:
                replayed_chunks = state.get_chunks_after(replay_from_id)
                for chunk in replayed_chunks:
                    event_data = {
                        "content": chunk["content"],
                        "tokens": chunk["tokens"],
                        "cost_usd": chunk["cost"],
                        "replayed": True,
                    }
                    sse_event = await format_sse_event("message_chunk", event_data, chunk["event_id"])
                    yield sse_event

            # Emit heartbeat every 10 seconds (keep connection alive)
            heartbeat_task = asyncio.create_task(emit_heartbeat_loop(state))

            # Simulate streaming response (in production: call LLM API)
            response_text = await generate_mock_response(message, model)

            # Stream response in chunks
            chunk_size = 7  # Characters per chunk
            current_pos = 0

            while current_pos < len(response_text):
                if state.is_closed:
                    break

                # Extract chunk
                chunk = response_text[current_pos : current_pos + chunk_size]
                current_pos += chunk_size

                # Get event ID
                event_id = state.next_event_id()

                # Approximate tokens (4 chars = 1 token)
                tokens = max(1, len(chunk) // 4)

                # Calculate cost based on model
                cost_per_token = 0.00060 / 1000 if model == "gpt-4o-mini" else 0.01000 / 1000
                cost_usd = tokens * cost_per_token

                # Record chunk
                state.add_chunk(chunk, tokens, cost_usd)

                # Emit event
                event_data = {
                    "content": chunk,
                    "tokens": tokens,
                    "cost_usd": cost_usd,
                }
                sse_event = await format_sse_event("message_chunk", event_data, event_id)
                yield sse_event

                # Small delay between chunks for demo
                await asyncio.sleep(0.05)

            # Emit done event
            final_event_id = state.next_event_id()
            done_data = {
                "total_tokens": sum(c["tokens"] for c in state.chunks_sent),
                "total_cost": sum(c["cost"] for c in state.chunks_sent),
                "latency_ms": int((time.time() - state.created_at) * 1000),
            }
            sse_event = await format_sse_event("done", done_data, final_event_id)
            yield sse_event

            # Cancel heartbeat task
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

        except asyncio.CancelledError:
            # Client disconnected
            state.is_closed = True
            raise
        except Exception as e:
            # Error during streaming
            state.is_closed = True
            error_event_id = state.next_event_id()
            error_data = {"error": str(e), "error_type": type(e).__name__}
            sse_event = await format_sse_event("error", error_data, error_event_id)
            yield sse_event

    async def emit_heartbeat_loop(state: SSEStreamState, interval: float = 10.0) -> None:
        """Emit heartbeat events to keep connection alive."""
        try:
            while not state.is_closed:
                await asyncio.sleep(interval)
                if not state.is_closed:
                    event_id = state.next_event_id()
                    await format_sse_event("heartbeat", {}, event_id)
                    # Note: In real implementation, would queue this to the stream
                    # For now, heartbeats are implicit in streaming
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        generate_sse_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )


async def generate_mock_response(message: str, model: str) -> str:
    """Generate mock response for demo."""
    responses = {
        "default": "I'm here to help you with that task. As an AI assistant, I can analyze, explain, search, and provide recommendations. For actions that modify external systems or send messages, I may need additional permissions. What specifically would you like me to help you with?",
    }

    return responses.get(model, responses["default"])


@app.get("/magic")
def magic_box():
    """
    Magic Box interface - Sprint 61a.

    Pure HTML/JS interface with SSE streaming, cost tracking, and anonymous sessions.
    No authentication required for anonymous use.
    """
    from fastapi.responses import FileResponse

    # Find magic/index.html in static directory
    if static_dir:
        magic_path = static_dir / "magic" / "index.html"
        if magic_path.exists():
            return FileResponse(magic_path)

    raise HTTPException(status_code=404, detail="Magic Box interface not found")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
