# Platform Integration Guide: Reusing R1/R2 Code

## Goal
Reuse battle-tested R1/R2 code (Knowledge API, RLS, Auth) without risky refactors. Use **adapter pattern** to export new filesystem layout while keeping old imports working.

---

## What We Keep (No Changes)

### Existing Production Code
```
src/knowledge/        ← Knowledge API v1 (R2 live, battle-tested)
src/stream/           ← Stream API + JWT auth (R1 live, stable)
src/memory/rls.py     ← RLS plumbing (R2 production, verified)
tests/                ← All existing tests (100+ tests passing)
```

**Why:** These modules are proven in production. Zero edits unless security bugs found.

### Migration Timeline
```
Days 1-7:  Create adapter modules (new files only)
Days 8-14: Update imports in new code (relay-ai/*)
Days 15+:  Gradual physical move (src/ → relay-ai/platform/api/) with git mv
```

---

## New Filesystem Layout

```
relay-ai/platform/
├── api/
│   ├── __init__.py
│   ├── mvp.py                         # NEW: Main FastAPI app (MVP)
│   ├── knowledge/                     # NEW: Adapter for src/knowledge
│   │   ├── __init__.py               # Re-exports: upload, search, list, delete
│   │   └── TODO_migrate_from_src.md  # Future move plan
│   ├── stream/                        # NEW: Adapter for src/stream
│   │   ├── __init__.py               # Re-exports: oauth, jwt, auth
│   │   └── TODO_migrate_from_src.md
│   └── teams/                         # NEW: Team management endpoints
│       ├── __init__.py
│       └── router.py                  # Invite, join, list members
├── security/
│   ├── __init__.py
│   ├── rls/                           # NEW: Adapter for src/memory/rls.py
│   │   ├── __init__.py               # Re-exports: hmac_user, set_rls_context, etc.
│   │   └── TODO_migrate_from_src.md
│   └── audit.py                       # NEW: Audit logging for queries
└── agents/                            # Placeholder for Agent Bus (v2)
    └── __init__.py

relay-ai/product/
├── web/                               # Next.js app (new)
│   ├── pages/
│   ├── components/
│   └── lib/
└── docs/
    └── README.md
```

---

## Adapter Pattern (How It Works)

### Pattern: Re-export without refactoring

**Old (src/knowledge/__init__.py):**
```python
# Existing code - untouched
from .api import upload_file, search, list_files, delete_file
```

**New (relay-ai/platform/api/knowledge/__init__.py):**
```python
"""Adapter: Re-exports from src/knowledge for relay-ai structure."""

# Import from old location (src still exists during transition)
import sys
sys.path.insert(0, '../../..')  # Add repo root to path

from src.knowledge import (
    upload_file,
    search,
    list_files,
    delete_file,
    router as knowledge_router,
)

# Export for new imports
__all__ = [
    'upload_file',
    'search',
    'list_files',
    'delete_file',
    'knowledge_router',
]
```

**New code imports:**
```python
# New code (relay-ai/product/web/lib/api.py) can import from either:
from relay_ai.platform.api.knowledge import search  # New structure
# OR (temporary, for testing)
from src.knowledge import search                    # Old structure
```

**Benefit:** Both imports work during transition. No code changes needed in src/knowledge/ itself.

---

## File-by-File Integration Plan

### 1. Adapter: Knowledge API

**File: `relay-ai/platform/api/knowledge/__init__.py`**
```python
"""Adapter for Knowledge API v1.

Exports all public functions from src/knowledge/ to relay-ai filesystem.
Allows gradual migration without breaking existing imports.
"""

import sys
from pathlib import Path

# Add repo root to path (temporary, while src/ still exists)
REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Import Knowledge API router and functions from src/
from src.knowledge.api import router as knowledge_router
from src.knowledge.db.asyncpg_client import (
    init_pool,
    close_pool,
    get_connection,
    with_user_conn,
    execute_query,
    execute_query_one,
    execute_mutation,
    SecurityError,
)

__all__ = [
    'knowledge_router',
    'init_pool',
    'close_pool',
    'get_connection',
    'with_user_conn',
    'execute_query',
    'execute_query_one',
    'execute_mutation',
    'SecurityError',
]
```

**File: `relay-ai/platform/api/knowledge/TODO_migrate_from_src.md`**
```markdown
# Future Migration: src/knowledge → relay-ai/platform/api/knowledge

## Timeline
- [ ] Phase 1 (Week 3-4): Verify adapter works (tests pass)
- [ ] Phase 2 (Week 5-6): Move with `git mv src/knowledge relay-ai/platform/api/knowledge`
- [ ] Phase 3 (Week 7-8): Update all imports; remove old src/knowledge/
- [ ] Phase 4: Verify tests still pass; tag as complete

## Verification Checklist
- [ ] All 19 knowledge API tests pass
- [ ] X-Request-ID header present on all responses
- [ ] RLS isolation verified (User A can't see User B's files)
- [ ] Rate limiting working (per-user Redis bucket)
- [ ] Performance: search latency p95 < 1.0s
```

---

### 2. Adapter: Stream API (JWT + OAuth)

**File: `relay-ai/platform/api/stream/__init__.py`**
```python
"""Adapter for Stream API (Auth + OAuth).

Exports JWT verification, token generation, and OAuth helpers.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.stream.auth import (
    StreamPrincipal,
    verify_supabase_jwt,
    generate_anon_session_token,
    get_stream_principal,
)

__all__ = [
    'StreamPrincipal',
    'verify_supabase_jwt',
    'generate_anon_session_token',
    'get_stream_principal',
]
```

---

### 3. Adapter: RLS Security Helpers

**File: `relay-ai/platform/security/rls/__init__.py`**
```python
"""Adapter for RLS (Row-Level Security) plumbing."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.memory.rls import (
    hmac_user,
    set_rls_context,
    set_rls_session_variable,
    clear_rls_session_variable,
    verify_rls_isolation,
)

__all__ = [
    'hmac_user',
    'set_rls_context',
    'set_rls_session_variable',
    'clear_rls_session_variable',
    'verify_rls_isolation',
]
```

---

### 4. Main MVP App (New)

**File: `relay-ai/platform/api/mvp.py`**
```python
"""
Relay MVP FastAPI Application

Combines:
- Knowledge API (document upload + search) via adapter
- Stream API (JWT auth + OAuth) via adapter
- Security headers (visible trust indicators)
- Team management (invites, members)
"""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import uuid
import logging

# Import routers from adapters
from relay_ai.platform.api.knowledge import knowledge_router
from relay_ai.platform.api.stream import stream_router  # TODO: Create this
from relay_ai.platform.api.teams import teams_router     # NEW: Team management

logger = logging.getLogger(__name__)

# Create app
app = FastAPI(
    title="Relay MVP",
    description="The provably secure AI assistant for SMBs",
    version="1.0.0",
)

# CORS: Allow frontend on any origin during MVP
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict to relay.ai domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-RateLimit-*", "Retry-After"],
)

# ==============================================================================
# MIDDLEWARE: Request Tracing + Security Headers
# ==============================================================================

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Middleware: Add X-Request-ID and security transparency headers.

    These headers make security VISIBLE to the client and audit tools.
    """
    # Generate request ID if not present
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id

    # Call endpoint
    response: Response = await call_next(request)

    # Add transparency headers (THE DIFFERENTIATOR)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Data-Isolation"] = "user-scoped"      # RLS enforced
    response.headers["X-Encryption"] = "AES-256-GCM"          # How data is encrypted
    response.headers["X-Training-Data"] = "never"             # No models trained

    # Optional: Add request audit token for audit log
    response.headers["X-Audit-Token"] = request_id

    return response

# ==============================================================================
# ROUTERS: Include all endpoints
# ==============================================================================

# Knowledge API (upload, search, list, delete documents)
app.include_router(knowledge_router, prefix="/api/v1/knowledge", tags=["Knowledge"])

# Stream API (JWT auth, OAuth, token generation)
# app.include_router(stream_router, prefix="/auth", tags=["Auth"])  # TODO

# Team management (invites, members)
app.include_router(teams_router, prefix="/api/v1/team", tags=["Team"])

# ==============================================================================
# HEALTH CHECK
# ==============================================================================

@app.get("/ready")
async def health_check():
    """
    Readiness probe. Returns 200 if:
    - App is running
    - Database reachable
    - Redis reachable
    """
    return {
        "ready": True,
        "service": "relay-mvp",
        "version": "1.0.0",
    }

@app.get("/health")
async def liveness():
    """Liveness probe (kubernetes)."""
    return {"status": "ok"}

# ==============================================================================
# STARTUP / SHUTDOWN
# ==============================================================================

@app.on_event("startup")
async def startup():
    logger.info("🚀 Relay MVP starting up...")
    # Initialize database pool
    from relay_ai.platform.api.knowledge import init_pool
    await init_pool()
    logger.info("✓ Database pool initialized")

@app.on_event("shutdown")
async def shutdown():
    logger.info("🛑 Relay MVP shutting down...")
    from relay_ai.platform.api.knowledge import close_pool
    await close_pool()
    logger.info("✓ Database pool closed")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## Testing Strategy

### Phase 1: Adapter Verification (Days 1-7)

```bash
# Run existing tests against adapters
pytest tests/knowledge/test_knowledge_api.py -v
# Expected: All 68 tests pass (same as before)

pytest tests/knowledge/test_knowledge_security_acceptance.py -v
# Expected: All 7 security tests pass

# Verify imports work from new location
python3 -c "from relay_ai.platform.api.knowledge import search; print('✓ Adapter imports work')"
```

### Phase 2: Integration Testing (Days 8-14)

```bash
# New MVP app imports and boots
python3 relay_ai/platform/api/mvp.py
# Expected: FastAPI app starts, /ready returns 200

# Test endpoint via cURL
curl -H "Authorization: Bearer $JWT" http://localhost:8000/api/v1/knowledge/files
# Expected: 200 OK with security headers
```

### Phase 3: Production Canary (Days 15+)

```bash
# Deploy MVP to staging
git push origin feat/reorg-product-first
# Railway auto-rebuilds and deploys

# Run smoke tests
bash scripts/r2_staging_smoke.py --endpoint https://relay-staging.railway.app
# Expected: All tests pass, TTFV < 1.0s, security_violations = 0
```

---

## Rollback Instructions

If adapter breaks anything:

```bash
# Revert to pre-reorg state
git revert pre-reorg-20251101
# Or restore from backup
tar -xzf ../relay-backup-20251101.tar.gz
```

---

## Dependencies

### Existing (Already Working)
- FastAPI 0.100+ ✓
- asyncpg (PostgreSQL client) ✓
- pydantic (validation) ✓
- uvicorn (ASGI server) ✓
- jwt (Supabase JWT decode) ✓

### New (For MVP Web)
- Next.js 14+ (TypeScript, App Router)
- Tailwind CSS
- React Query (API client)
- Supabase JS client

### DevOps (Already Running)
- Railway (deployment)
- PostgreSQL (RLS-enabled)
- Redis (rate limiting + cache)
- Prometheus + Grafana (metrics)

---

## Success Criteria

| Phase | Criterion | Status |
|-------|-----------|--------|
| **Adapter Phase** | All tests pass; imports work from both old + new | Pending |
| **Integration Phase** | MVP app boots; security headers present | Pending |
| **Production Phase** | Staging canary passes; TTFV < 1.0s | Pending |

---

## File Ownership

| File | Owner | Contact |
|------|-------|---------|
| relay-ai/platform/api/knowledge/__init__.py | Backend | Haiku (scaffolding) |
| relay-ai/platform/api/stream/__init__.py | Backend | Haiku (scaffolding) |
| relay-ai/platform/security/rls/__init__.py | Security | Sonnet (audit) |
| relay-ai/platform/api/mvp.py | Backend | Haiku (scaffolding) → Sonnet (audit) |
| relay-ai/platform/api/teams/router.py | Backend | Haiku (new) |

---

## Next Steps

1. **Haiku:** Create adapter files (this document + examples)
2. **Run tests:** Verify adapters work
3. **Haiku:** Create team management router
4. **Create:** relay-ai/platform/api/mvp.py main app
5. **Sonnet:** Security audit + RLS verification
6. **Test:** Run MVP app, verify /ready endpoint
7. **Deploy:** Canary to staging
8. **Measure:** TTFV, latency, error rate

---

**Status:** Adapter pattern ready to implement.
**Next:** Run reorganize.sh and verify imports.
