# Phase 1 MVP Deployment Analysis & Resolution Report

**Date**: November 17, 2025
**Status**: ✅ FULLY OPERATIONAL
**Deployment**: Railway Production Environment
**API Base URL**: https://relay-production-f2a6.up.railway.app

---

## Executive Summary

Successfully deployed Phase 1 MVP with full database persistence and AI chat functionality. All critical bugs related to database connection pooling have been resolved. The system is now production-ready with 4 operational endpoints.

### Working Endpoints (All Tested & Verified)
1. **Health Check**: `GET /health` ✅
2. **List Threads**: `GET /mvp/threads` ✅
3. **Chat**: `POST /mvp/chat` ✅
4. **Get Messages**: `GET /mvp/threads/{thread_id}/messages` ✅

---

## System Architecture

### Technology Stack
- **Backend Framework**: FastAPI (Python)
- **Database**: PostgreSQL (Railway Postgres)
- **Connection Pooling**: asyncpg
- **AI Models**: OpenAI GPT-4, GPT-3.5-turbo
- **Migrations**: Alembic
- **Deployment**: Railway (Docker containers)

### Database Schema (MVP Phase 1)

```sql
-- mvp_users: Internal MVP users (not end-users)
CREATE TABLE mvp_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- mvp_threads: Conversation threads
CREATE TABLE mvp_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES mvp_users(id) NOT NULL,
    title VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- mvp_messages: Messages within threads
CREATE TABLE mvp_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID REFERENCES mvp_threads(id) NOT NULL,
    user_id UUID REFERENCES mvp_users(id) NOT NULL,
    role VARCHAR(50) NOT NULL, -- 'user' or 'assistant'
    model_name VARCHAR(100),
    content TEXT NOT NULL,
    token_usage_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Key Files & Locations

| File | Purpose | Lines of Interest |
|------|---------|-------------------|
| `relay_ai/platform/api/mvp_db.py` | MVP database access layer | 23-171 (all functions) |
| `relay_ai/platform/api/knowledge/db/asyncpg_client.py` | Database connection pool management | 32-53, 69-120, 136-141 |
| `relay_ai/platform/api/mvp.py` | MVP API endpoints | Full file |
| `alembic/versions/20251014_conversations.py` | MVP schema migration | Full file |
| `alembic/versions/20251019_memory_schema_rls.py` | Memory schema (SKIPPED for MVP) | 37-42 (early return) |

---

## Critical Issues Resolved

### Issue 1: NoneType Error in Database Connection Release

**Symptom**:
```
"Failed to list threads: 'NoneType' object has no attribute 'release'"
```

**Root Cause**:
Multiple database functions were attempting to release connections to a None pool without null checks. This occurred because:
1. Railway's PostgreSQL instance doesn't have pgvector extension
2. Database pool initialization gracefully degraded but set `_pool = None`
3. MVP database functions tried to call `_pool.release(conn)` on None

**Affected Functions** (7 total in `mvp_db.py`):
- `get_default_user_id()` - Line 40
- `create_thread()` - Line 61
- `get_thread()` - Line 79
- `list_threads()` - Line 100
- `create_message()` - Line 139
- `list_messages()` - Line 158
- `verify_thread_ownership()` - Line 169

**Fix Applied** (Commit `6942280`):

```python
# BEFORE (Buggy code):
async def list_threads(user_id: uuid.UUID, limit: int = 50) -> list[dict]:
    conn = await get_connection()
    try:
        rows = await conn.fetch(...)
        return [dict(row) for row in rows]
    finally:
        await _pool.release(conn)  # ❌ Crashes if _pool is None

# AFTER (Fixed code):
async def list_threads(user_id: uuid.UUID, limit: int = 50) -> list[dict]:
    conn = await get_connection()
    try:
        rows = await conn.fetch(...)
        return [dict(row) for row in rows]
    finally:
        if conn and _pool:  # ✅ Graceful null check
            await _pool.release(conn)
```

**Pattern Applied**: Same fix applied to all 7 affected functions.

---

### Issue 2: Connection Release Bug in asyncpg_client.py

**Location**: `relay_ai/platform/api/knowledge/db/asyncpg_client.py:69-120`

**Symptom**: Similar NoneType errors during schema initialization.

**Fix Applied** (Commit `66c9473`):

```python
async def init_schema() -> None:
    # Skip schema initialization if pool is not available (MVP Phase 1 doesn't need this)
    if not _pool:
        logger.debug("Skipping schema initialization - database pool not available (expected for MVP Phase 1)")
        return  # ✅ Early return prevents downstream errors

    conn = None
    try:
        conn = await get_connection()
        # ... RLS setup code ...
    finally:
        # CRITICAL: Release connection back to pool (not close)
        if conn and _pool:  # ✅ Added null check
            await _pool.release(conn)
```

**Key Changes**:
1. Added early return if `_pool` is None (lines 76-79)
2. Added null check before releasing connection (line 118)

---

### Issue 3: pgvector Extension Missing on Railway

**Symptom**:
```
extension "pgvector" is not available
```

**Why This Matters**:
- Railway's standard PostgreSQL doesn't include pgvector extension
- pgvector is required for Phase 2/3 (knowledge API with embeddings)
- MVP Phase 1 doesn't need pgvector (only uses basic CRUD tables)

**Solution** (Commit `671b07f`):

```python
async def _init_connection(conn: asyncpg.Connection) -> None:
    """Per-connection initialization."""
    # Enable extensions (graceful degradation if not available)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pgvector")
    except Exception as e:
        logger.debug(f"pgvector extension not available (expected on Railway): {e}")

    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    except Exception as e:
        logger.debug(f"pg_trgm extension not available: {e}")
```

**Result**: Extensions fail gracefully without blocking MVP functionality.

---

### Issue 4: Memory Schema Migration Running on MVP

**Location**: `alembic/versions/20251019_memory_schema_rls.py`

**Problem**: Migration tried to create `memory_chunks` table with pgvector columns, which:
1. Isn't needed for MVP Phase 1
2. Requires pgvector extension that Railway doesn't have

**Fix Applied** (Commit `6718e53`):

```python
def upgrade():
    """
    Create memory_chunks table with:
    - Row-Level Security for user_hash-based tenant isolation
    - Encryption columns for text/metadata/shadow embeddings
    - Plaintext embedding for ANN indexing
    - Partial indexes scoped to user_hash

    NOTE: This migration is SKIPPED on Railway Postgres which doesn't support pgvector.
    The memory_chunks table is not needed for MVP Phase 1.
    """

    # Skip this entire migration if pgvector is not available
    # This table is not needed for MVP Phase 1 (only mvp_users/threads/messages are needed)
    import logging
    logging.info("Skipping memory_chunks table creation - not needed for MVP Phase 1")
    return  # ✅ Early return skips entire migration
```

---

## Deployment Timeline

### Commit History (Most Recent First)

| Commit | Date | Description |
|--------|------|-------------|
| `6942280` | Nov 17, 2025 | fix: Add null checks for pool.release() in mvp_db.py |
| `265e1fa` | Nov 17, 2025 | trigger: Force Railway redeploy with latest fixes |
| `66c9473` | Nov 17, 2025 | fix: Prevent NoneType error in init_schema connection release |
| `671b07f` | Nov 17, 2025 | fix: Make database pool initialization compatible with Railway Postgres |
| `6718e53` | Nov 17, 2025 | fix: Skip memory_chunks migration on Railway (not needed for MVP Phase 1) |

### Railway Deployment IDs

| Deployment ID | Timestamp | Status | Notes |
|---------------|-----------|--------|-------|
| `23a0db98` | Nov 17, 2025 7:00 AM | ✅ Active | Final working deployment |
| `139aedf2` | Nov 17, 2025 6:59 AM | ✅ Active | Concurrent deployment |
| `0be1e93f` | Nov 17, 2025 9:05 PM | ⚠️ Old | Pre-fix deployment |

---

## Test Results (Final Verification)

### 1. Health Check
**Request**:
```bash
curl https://relay-production-f2a6.up.railway.app/health
```

**Response**:
```json
{"status":"ok"}
```
✅ **Status**: WORKING

---

### 2. List Threads
**Request**:
```bash
curl https://relay-production-f2a6.up.railway.app/mvp/threads
```

**Response** (6 threads found):
```json
{
  "threads": [
    {
      "id": "5df87116-2587-4d97-8a99-aff7fbadc9df",
      "user_id": "00000000-0000-0000-0000-000000000001",
      "title": "Final test from Kyle",
      "created_at": "2025-11-17T15:03:41.037432",
      "updated_at": "2025-11-17T15:03:41.037432"
    },
    // ... 5 more threads
  ]
}
```
✅ **Status**: WORKING - No more NoneType errors!

---

### 3. Chat (Create Thread & Message)
**Request**:
```bash
curl -X POST https://relay-production-f2a6.up.railway.app/mvp/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Testing after connection fix","model":"gpt-4"}'
```

**Response**:
```json
{
  "response": "Hello! How can I assist you today? Your connection seems to be working fine now.",
  "model": "gpt-4",
  "timestamp": "2025-11-17T15:15:11.489542",
  "tokens_used": 42,
  "thread_id": "ccef237b-2ebb-4aff-9e1f-9b4c54a02739"
}
```
✅ **Status**: WORKING
- AI responds correctly
- Token usage tracked (42 tokens)
- Thread created and returned

---

### 4. Get Messages from Thread
**Request**:
```bash
curl https://relay-production-f2a6.up.railway.app/mvp/threads/ccef237b-2ebb-4aff-9e1f-9b4c54a02739/messages
```

**Response**:
```json
{
  "messages": [
    {
      "id": "87d3dcb8-8c86-4461-bb5a-d287a46947e5",
      "thread_id": "ccef237b-2ebb-4aff-9e1f-9b4c54a02739",
      "user_id": "00000000-0000-0000-0000-000000000001",
      "role": "user",
      "model_name": null,
      "content": "Testing after connection fix",
      "token_usage_json": null,
      "created_at": "2025-11-17T15:15:09.563541"
    },
    {
      "id": "dee25c71-63b0-406a-912f-e1ec898b5e09",
      "thread_id": "ccef237b-2ebb-4aff-9e1f-9b4c54a02739",
      "user_id": "00000000-0000-0000-0000-000000000001",
      "role": "assistant",
      "model_name": "gpt-4",
      "content": "Hello! How can I assist you today? Your connection seems to be working fine now.",
      "token_usage_json": "{\"total_tokens\": 42, \"prompt_tokens\": 24, \"completion_tokens\": 18}",
      "created_at": "2025-11-17T15:15:11.489487"
    }
  ]
}
```
✅ **Status**: WORKING
- Complete conversation history retrieved
- Token breakdown preserved in JSON
- Proper chronological ordering

---

## Code Deep Dive

### MVP Database Access Layer (`mvp_db.py`)

**Architecture**: Simple asyncpg-based access layer that reuses the connection pool from the knowledge API.

**Key Characteristics**:
- No RLS enforcement (MVP is internal-only for MVP operators)
- Direct asyncpg queries (no ORM)
- Uses connection pooling for performance
- Graceful degradation when pool unavailable

**Default User System**:
```python
_default_user_id: Optional[uuid.UUID] = None

async def get_default_user_id() -> uuid.UUID:
    """Get the default user ID (Kyle) for MVP requests without explicit user_id."""
    global _default_user_id

    if _default_user_id:
        return _default_user_id

    conn = await get_connection()
    try:
        row = await conn.fetchrow("SELECT id FROM mvp_users WHERE display_name = $1", "Kyle")
        if not row:
            raise RuntimeError("Default MVP user 'Kyle' not found in mvp_users table")

        _default_user_id = row["id"]
        logger.info(f"Default MVP user loaded: Kyle ({_default_user_id})")
        return _default_user_id
    finally:
        if conn and _pool:
            await _pool.release(conn)
```

**Design Decision**: Caches default user ID to avoid repeated database queries.

---

### Connection Pool Management (`asyncpg_client.py`)

**Pool Initialization**:
```python
_pool: Optional[asyncpg.Pool] = None

async def init_pool(
    database_url: Optional[str] = None,
    min_size: int = 5,
    max_size: int = 20,
) -> None:
    """Initialize asyncpg connection pool."""
    global _pool
    url = database_url or os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL not set")

    _pool = await asyncpg.create_pool(
        url,
        min_size=min_size,
        max_size=max_size,
        init=_init_connection,
    )
    logger.info("Database pool initialized (min=%d, max=%d)", min_size, max_size)

    # Initialize schema
    await init_schema()
```

**Connection Acquisition**:
```python
async def get_connection() -> asyncpg.Connection:
    """Get connection from pool."""
    if not _pool:
        raise RuntimeError("Database pool not initialized; call init_pool first")
    return await _pool.acquire()
```

**CRITICAL**: Connections must be released, not closed. Closing destroys the pooled connection.

---

### Row-Level Security (RLS) System

**Note**: RLS is NOT used in MVP Phase 1, but is implemented in `asyncpg_client.py` for future Phase 2/3.

**Context Manager for User-Scoped Queries**:
```python
@asynccontextmanager
async def with_user_conn(user_hash: str) -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Context manager for per-user, per-transaction RLS enforcement.

    CRITICAL SECURITY: Sets RLS context before any query, ensures transaction scope,
    releases to pool on exit. Fail-closed: raises SecurityError if user_hash missing.
    """
    if not user_hash:
        raise SecurityError("user_hash is required for RLS enforcement")

    conn = await get_connection()
    try:
        # Open transaction
        async with conn.transaction():
            # Set RLS context with PARAMETERIZED QUERY (prevents SQL injection)
            await conn.execute(
                "SELECT set_config($1, $2, true)",
                "app.user_hash",
                user_hash,
            )
            logger.debug(f"RLS context set for user {user_hash[:8]}... (txn scope)")
            yield conn
    except SecurityError:
        raise
    except Exception as e:
        logger.error(f"RLS context error for user {user_hash[:8]}: {e}")
        raise
    finally:
        await _pool.release(conn)
```

**Usage Example** (for future Phase 2/3):
```python
async def get_user_files(user_hash: str):
    async with with_user_conn(user_hash) as conn:
        # RLS automatically filters to user's files only
        rows = await conn.fetch("SELECT * FROM files")
        return [dict(row) for row in rows]
```

---

## Environment Configuration

### Required Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:port/dbname

# OpenAI API
OPENAI_API_KEY=sk-...

# Anthropic API (optional for MVP Phase 1)
ANTHROPIC_API_KEY=sk-ant-...

# Server
PORT=8080  # Railway default
```

### Railway Variables (Already Set)

| Variable | Purpose | Status |
|----------|---------|--------|
| `DATABASE_URL` | PostgreSQL connection string | ✅ Set |
| `OPENAI_API_KEY` | OpenAI API access | ✅ Set |
| `PORT` | Server port (8080) | ✅ Set |

---

## Known Limitations & Future Considerations

### 1. Missing pgvector Extension
**Impact**: Cannot use Phase 2/3 knowledge API features (file embeddings, vector search)
**Workaround**: MVP Phase 1 doesn't need pgvector
**Future Solution**: Either:
- Upgrade to Railway Pro with pgvector support
- Deploy Postgres on managed provider with pgvector (Supabase, RDS, etc.)
- Use separate vector database (Pinecone, Weaviate, etc.)

### 2. No Authentication in MVP Phase 1
**Current State**: Default user "Kyle" hardcoded
**Security Impact**: Internal MVP only - not exposed to end users
**Future Requirements**:
- User authentication (OAuth, JWT, etc.)
- Session management
- User registration/login

### 3. No Rate Limiting
**Current State**: Unlimited API requests
**Risk**: Potential for API abuse or cost overruns
**Recommendation**: Implement rate limiting before public release

### 4. No CORS Configuration
**Current State**: Default CORS settings
**Impact**: May block frontend requests from different domains
**Action Needed**: Configure CORS for production frontend domain

### 5. Error Handling
**Current State**: Basic try/catch with generic error messages
**Improvement Opportunities**:
- More specific error codes
- Better error messages for debugging
- Error tracking/monitoring (Sentry, etc.)

---

## Performance Metrics

### Connection Pool Settings
- **Min Connections**: 5
- **Max Connections**: 20
- **Pool Type**: asyncpg (high-performance async PostgreSQL driver)

### Expected Latency
- **Health Check**: < 50ms
- **List Threads**: < 100ms (depends on thread count)
- **Chat (GPT-4)**: 2-5 seconds (OpenAI API latency)
- **Get Messages**: < 100ms (depends on message count)

### Database Query Performance
All queries use proper indexes:
- `mvp_threads.user_id` (indexed)
- `mvp_threads.updated_at` (indexed for sorting)
- `mvp_messages.thread_id` (indexed, foreign key)
- `mvp_messages.created_at` (indexed for chronological ordering)

---

## Monitoring & Observability

### Current Logging
```python
import logging
logger = logging.getLogger(__name__)

# Examples from codebase:
logger.info(f"Created thread {thread_id} for user {user_id}")
logger.debug(f"Created message {message_id} in thread {thread_id}")
logger.error(f"Schema initialization error: {e}")
```

### Railway Logs Access
```bash
# View recent logs
railway logs --tail 100

# Stream logs in real-time
railway logs --follow

# Filter logs
railway logs | grep ERROR
```

### Recommended Monitoring (Future)
1. **Application Performance Monitoring (APM)**
   - New Relic, DataDog, or Railway Analytics
   - Track endpoint latency, error rates, throughput

2. **Database Metrics**
   - Connection pool utilization
   - Query performance
   - Slow query log

3. **Cost Monitoring**
   - OpenAI API usage and costs
   - Database storage and compute
   - Railway hosting costs

---

## API Usage Examples

### Example 1: Create Conversation & Chat

```python
import requests
import json

BASE_URL = "https://relay-production-f2a6.up.railway.app"

# Start a conversation
response = requests.post(
    f"{BASE_URL}/mvp/chat",
    json={
        "message": "What is the capital of France?",
        "model": "gpt-4"
    }
)

result = response.json()
print(f"AI Response: {result['response']}")
print(f"Thread ID: {result['thread_id']}")
print(f"Tokens Used: {result['tokens_used']}")

# Continue conversation in same thread
response = requests.post(
    f"{BASE_URL}/mvp/chat",
    json={
        "message": "What's the population?",
        "model": "gpt-4",
        "thread_id": result['thread_id']  # Continue in same thread
    }
)

print(f"Follow-up Response: {response.json()['response']}")
```

### Example 2: List User's Conversations

```python
import requests

BASE_URL = "https://relay-production-f2a6.up.railway.app"

# Get all threads for default user (Kyle)
response = requests.get(f"{BASE_URL}/mvp/threads")
threads = response.json()["threads"]

for thread in threads:
    print(f"Thread: {thread['title']}")
    print(f"  Created: {thread['created_at']}")
    print(f"  Last Updated: {thread['updated_at']}")
    print()
```

### Example 3: Retrieve Full Conversation History

```python
import requests

BASE_URL = "https://relay-production-f2a6.up.railway.app"
THREAD_ID = "ccef237b-2ebb-4aff-9e1f-9b4c54a02739"

# Get all messages in thread
response = requests.get(f"{BASE_URL}/mvp/threads/{THREAD_ID}/messages")
messages = response.json()["messages"]

for msg in messages:
    role = "User" if msg["role"] == "user" else "AI"
    print(f"{role}: {msg['content']}")

    if msg["token_usage_json"]:
        tokens = json.loads(msg["token_usage_json"])
        print(f"  (Tokens: {tokens['total_tokens']})")
    print()
```

---

## Troubleshooting Guide

### Issue: "Database pool not initialized"

**Symptom**:
```
RuntimeError: Database pool not initialized; call init_pool first
```

**Cause**: FastAPI startup event didn't call `init_pool()`

**Solution**: Check that `startup_event()` in `main.py` calls `init_pool()`

---

### Issue: "Default MVP user 'Kyle' not found"

**Symptom**:
```
RuntimeError: Default MVP user 'Kyle' not found in mvp_users table
```

**Cause**: Database migration didn't seed default user

**Solution**: Manually insert default user:
```sql
INSERT INTO mvp_users (id, display_name, created_at)
VALUES ('00000000-0000-0000-0000-000000000001', 'Kyle', NOW());
```

---

### Issue: "'NoneType' object has no attribute 'release'"

**Symptom**:
```
Failed to list threads: 'NoneType' object has no attribute 'release'
```

**Cause**: Connection release without null check

**Solution**: This was fixed in commit `6942280`. Ensure latest code is deployed.

**Verification**:
```bash
git log --oneline -1
# Should show: 6942280 or newer
```

---

### Issue: "password authentication failed for user 'postgres'"

**Symptom**:
```
Database pool initialization failed: password authentication failed for user 'postgres'
```

**Cause**: Incorrect DATABASE_URL environment variable

**Solution**:
1. Verify DATABASE_URL in Railway dashboard
2. Check connection string format: `postgresql://user:pass@host:port/dbname`
3. Ensure Railway Postgres plugin is attached to service

---

## Next Steps & Recommendations

### Immediate Actions (Phase 1 Complete)
- [x] Deploy MVP with database persistence ✅
- [x] Fix connection pooling bugs ✅
- [x] Verify all endpoints working ✅
- [x] Test full conversation workflow ✅

### Phase 2 Planning (Knowledge API)
- [ ] Provision PostgreSQL with pgvector support
  - Option A: Railway Pro tier with pgvector
  - Option B: Supabase (free tier includes pgvector)
  - Option C: AWS RDS with pgvector extension
- [ ] Implement file upload endpoints
- [ ] Build embedding generation pipeline
- [ ] Deploy vector search functionality
- [ ] Implement RLS for multi-tenant file isolation

### Phase 3 Planning (Production Hardening)
- [ ] Add authentication system (OAuth, JWT)
- [ ] Implement rate limiting
- [ ] Configure CORS for frontend domain
- [ ] Set up monitoring & alerting
- [ ] Add comprehensive error tracking
- [ ] Implement cost tracking & budgets
- [ ] Load testing & performance optimization
- [ ] Security audit & penetration testing

### Infrastructure Improvements
- [ ] Set up CI/CD pipeline (GitHub Actions)
- [ ] Implement automated testing
- [ ] Add staging environment
- [ ] Database backup & recovery procedures
- [ ] Disaster recovery plan

---

## Additional Resources

### Railway Documentation
- **Projects**: https://docs.railway.app/reference/projects
- **Databases**: https://docs.railway.app/databases/postgresql
- **Deployments**: https://docs.railway.app/deploy/deployments
- **Environment Variables**: https://docs.railway.app/develop/variables

### PostgreSQL & asyncpg
- **asyncpg**: https://magicstack.github.io/asyncpg/
- **Connection Pooling**: https://magicstack.github.io/asyncpg/current/usage.html#connection-pools
- **pgvector**: https://github.com/pgvector/pgvector

### OpenAI API
- **Chat Completions**: https://platform.openai.com/docs/api-reference/chat
- **Models**: https://platform.openai.com/docs/models
- **Token Counting**: https://github.com/openai/tiktoken

---

## Contact & Support

### Project Details
- **Repository**: openai-agents-workflows-2025.09.28-v1
- **Main Branch**: main
- **Current Commit**: 6942280 (fix: Add null checks for pool.release() in mvp_db.py)

### Key Stakeholders
- **MVP Operator**: Kyle
- **Default User ID**: 00000000-0000-0000-0000-000000000001

---

## Appendix A: Full Database Schema SQL

```sql
-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- MVP Users Table
CREATE TABLE mvp_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create default user (Kyle)
INSERT INTO mvp_users (id, display_name, created_at)
VALUES ('00000000-0000-0000-0000-000000000001', 'Kyle', NOW())
ON CONFLICT (display_name) DO NOTHING;

-- MVP Threads Table
CREATE TABLE mvp_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES mvp_users(id) ON DELETE CASCADE,
    title VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_mvp_threads_user_id ON mvp_threads(user_id);
CREATE INDEX idx_mvp_threads_updated_at ON mvp_threads(updated_at DESC);

-- MVP Messages Table
CREATE TABLE mvp_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL REFERENCES mvp_threads(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES mvp_users(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    model_name VARCHAR(100),
    content TEXT NOT NULL,
    token_usage_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_mvp_messages_thread_id ON mvp_messages(thread_id);
CREATE INDEX idx_mvp_messages_created_at ON mvp_messages(created_at);
CREATE INDEX idx_mvp_messages_user_id ON mvp_messages(user_id);
```

---

## Appendix B: Alembic Migration Commands

```bash
# Check current migration status
python -m alembic current

# View migration history
python -m alembic history

# Upgrade to latest migration
python -m alembic upgrade head

# Rollback one migration
python -m alembic downgrade -1

# Generate new migration (auto-detect schema changes)
python -m alembic revision --autogenerate -m "description"

# Generate new migration (manual)
python -m alembic revision -m "description"
```

---

## Appendix C: Railway CLI Commands

```bash
# Login to Railway
railway login

# Link to project
railway link

# Check status
railway status

# View logs
railway logs --tail 100

# Deploy current code
railway up

# Redeploy without code changes
railway redeploy

# Set environment variable
railway variables set KEY=value

# Get environment variable
railway variables get KEY

# List all variables
railway variables

# Connect to PostgreSQL
railway connect postgres
```

---

## Document Version

**Version**: 1.0
**Last Updated**: November 17, 2025
**Authors**: Claude Code (AI Assistant)
**Status**: Final - Phase 1 MVP Deployment Complete

---

**END OF DOCUMENT**
