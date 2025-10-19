# Magic Box Security Quick Fix Guide

## CRITICAL BLOCKERS (Must Fix Before R0.5)

### 1. Add Server-Side Quota Enforcement (2-3 hours)

**File**: `src/webapi.py`

**Add after line 1786** (after message validation):

```python
# Server-side anonymous quota enforcement
if user_id and user_id.startswith("anon_"):
    from .limits.anonymous_quota import check_anonymous_quota

    quota_check = await check_anonymous_quota(user_id, get_redis_client())
    if not quota_check["allowed"]:
        reason = quota_check["reason"]
        if reason == "hourly_limit":
            reset_in = quota_check["reset_in"]
            minutes = math.ceil(reset_in / 60)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit: {quota_check['hourly_count']}/20 messages this hour. Try again in {minutes} minutes.",
                headers={"Retry-After": str(int(reset_in))}
            )
        elif reason == "total_limit":
            raise HTTPException(
                status_code=429,
                detail="You've reached the 100 message limit for anonymous users. Sign in to continue!"
            )
```

**Create new file**: `src/limits/anonymous_quota.py`

```python
"""Anonymous user quota tracking (Redis-backed)."""
import time
from typing import TypedDict


class QuotaCheckResult(TypedDict):
    allowed: bool
    reason: str
    hourly_count: int
    total_count: int
    reset_in: int


async def check_anonymous_quota(user_id: str, redis) -> QuotaCheckResult:
    """Check anonymous user quotas (20/hr, 100 total)."""
    if not user_id.startswith("anon_"):
        return {"allowed": True, "reason": "", "hourly_count": 0, "total_count": 0, "reset_in": 0}

    now = time.time()
    one_hour_ago = now - 3600

    # Check hourly limit (sorted set with timestamps)
    hour_key = f"anon:hourly:{user_id}"
    redis.zremrangebyscore(hour_key, 0, one_hour_ago)
    hourly_count = redis.zcard(hour_key)

    if hourly_count >= 20:
        oldest_timestamp = float(redis.zrange(hour_key, 0, 0, withscores=True)[0][1])
        reset_in = int((oldest_timestamp + 3600) - now)
        return {
            "allowed": False,
            "reason": "hourly_limit",
            "hourly_count": hourly_count,
            "total_count": 0,
            "reset_in": max(1, reset_in),
        }

    # Check total limit
    total_key = f"anon:total:{user_id}"
    total_count = int(redis.get(total_key) or 0)

    if total_count >= 100:
        return {
            "allowed": False,
            "reason": "total_limit",
            "hourly_count": hourly_count,
            "total_count": total_count,
            "reset_in": 0,
        }

    # Record this request
    redis.zadd(hour_key, {str(now): now})
    redis.expire(hour_key, 3600)
    redis.incr(total_key)
    redis.expire(total_key, 7 * 24 * 3600)  # 7 days

    return {
        "allowed": True,
        "reason": "",
        "hourly_count": hourly_count + 1,
        "total_count": total_count + 1,
        "reset_in": 0,
    }
```

---

### 2. Add Rate Limiting to /api/v1/stream (30 min)

**File**: `src/webapi.py`

**Add after quota check** (around line 1800):

```python
# Rate limiting for anonymous users (5/min)
if user_id and user_id.startswith("anon_"):
    from .limits.limiter import get_rate_limiter

    limiter = get_rate_limiter()
    try:
        # Use more aggressive limits for anonymous
        limiter.check_limit(f"anon_stream:{user_id}")
    except RateLimitExceeded as e:
        raise e  # Re-raise with proper headers
```

**Update**: `src/limits/limiter.py`

Change line 128:
```python
# Before:
self.limit_per_min = int(os.getenv("RATE_LIMIT_EXEC_PER_MIN", "60"))

# After:
default_limit = "60"
if "anon_stream:" in workspace_id:
    default_limit = "5"  # 5/min for anonymous SSE streams
self.limit_per_min = int(os.getenv("RATE_LIMIT_EXEC_PER_MIN", default_limit))
```

---

### 3. Add Input Validation (30 min)

**File**: `src/webapi.py`

**Replace lines 1785-1786** with:

```python
import re
import math

# Input validation
MAX_MESSAGE_LENGTH = 4000  # ~1000 tokens
ALLOWED_MODELS = {"gpt-4o-mini", "gpt-4o"}

if not message:
    raise HTTPException(status_code=400, detail="message required")

if len(message) > MAX_MESSAGE_LENGTH:
    raise HTTPException(
        status_code=400,
        detail=f"Message too long (max {MAX_MESSAGE_LENGTH} characters)"
    )

# Sanitize message (remove control characters, keep printable + newlines/tabs)
message = "".join(c for c in message if c.isprintable() or c in "\n\t")

if model not in ALLOWED_MODELS:
    raise HTTPException(
        status_code=400,
        detail=f"Invalid model. Allowed: {', '.join(ALLOWED_MODELS)}"
    )

# Validate stream_id format if provided
if stream_id and not re.match(r'^stream_[a-z0-9_]+$', stream_id):
    raise HTTPException(
        status_code=400,
        detail="Invalid stream_id format"
    )
```

---

### 4. Add Session ID Validation (1 hour)

**File**: `src/webapi.py`

**Add after model validation** (around line 1810):

```python
# Validate anonymous session ID format and expiry
if user_id and user_id.startswith("anon_"):
    from .limits.anonymous_quota import validate_session_id

    if not await validate_session_id(user_id, get_redis_client()):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session ID. Please refresh the page."
        )
```

**Add to**: `src/limits/anonymous_quota.py`

```python
import uuid


async def validate_session_id(session_id: str, redis) -> bool:
    """Validate anonymous session ID format and expiry."""
    if not session_id.startswith("anon_"):
        return False

    # Validate UUID format
    try:
        uuid_part = session_id[5:]  # Remove "anon_" prefix
        uuid.UUID(uuid_part)
    except ValueError:
        return False

    # Check session exists and is not expired
    session_key = f"session:{session_id}"
    session_data = redis.hgetall(session_key)

    if not session_data:
        # First request for this session - create it
        redis.hset(session_key, "created_at", int(time.time()))
        redis.expire(session_key, 7 * 24 * 3600)  # 7 days
        return True

    # Check if expired (7 days)
    created_at = int(session_data.get("created_at", 0))
    if time.time() - created_at > 7 * 24 * 3600:
        redis.delete(session_key)
        return False

    return True
```

---

### 5. Sanitize Error Messages (30 min)

**File**: `src/webapi.py`

**Replace lines 1874-1880** with:

```python
except asyncio.CancelledError:
    state.is_closed = True
    raise
except Exception as e:
    # Log full error server-side
    import logging
    _LOG = logging.getLogger(__name__)
    _LOG.error(f"Stream error for {stream_id}: {e}", exc_info=True)

    # Send sanitized error to client
    state.is_closed = True
    error_event_id = state.next_event_id()

    # Generic error message (no stack traces)
    safe_error = "An error occurred. Please try again later."
    if isinstance(e, HTTPException):
        safe_error = e.detail
    elif "timeout" in str(e).lower():
        safe_error = "Request timed out. Please try again."

    error_data = {"error": safe_error, "error_type": "StreamError"}
    sse_event = await format_sse_event("error", error_data, error_event_id)
    yield sse_event
```

---

## Testing Checklist

After implementing fixes, test:

1. **Quota Enforcement**:
   ```bash
   # Should fail after 20 requests in 1 hour
   for i in {1..25}; do
     curl "http://localhost:8000/api/v1/stream?user_id=anon_test&message=hi"
   done
   ```

2. **Rate Limiting**:
   ```bash
   # Should fail after 5 requests in 1 minute
   for i in {1..10}; do
     curl "http://localhost:8000/api/v1/stream?user_id=anon_12345&message=test" &
   done
   ```

3. **Input Validation**:
   ```bash
   # Should reject long messages
   curl "http://localhost:8000/api/v1/stream?user_id=anon_test&message=$(python -c 'print("x"*5000)')"

   # Should reject invalid model
   curl "http://localhost:8000/api/v1/stream?user_id=anon_test&message=hi&model=gpt-5"
   ```

4. **Session Validation**:
   ```bash
   # Should reject invalid session ID
   curl "http://localhost:8000/api/v1/stream?user_id=anon_invalid&message=hi"
   ```

5. **Error Handling**:
   ```python
   # Trigger exception and verify no stack trace in response
   # (manually break something in generate_mock_response)
   ```

---

## Redis Setup (if not already configured)

**Required for quota tracking**:

```bash
# Install Redis (macOS)
brew install redis
redis-server

# Install Redis (Ubuntu)
sudo apt install redis-server
sudo systemctl start redis

# Install Python Redis client
pip install redis
```

**Update .env**:
```bash
REDIS_URL=redis://localhost:6379/0
```

---

## GDPR Compliance Quick Fixes

### Add Privacy Policy Link

**File**: `static/magic/index.html`

Add after line 292 (inside anon-badge div):

```html
<a href="/privacy" style="margin-left:1rem; font-size:0.75rem; color:#888; text-decoration:none;">
    Privacy
</a>
```

### Add "Clear My Data" Button

**File**: `static/magic/magic.js`

Add to MagicBox class (after line 876):

```javascript
clearMyData() {
    const confirmed = confirm(
        "Delete all your session data?\n\n" +
        "This will:\n" +
        "- Clear your message history\n" +
        "- Reset your usage quota\n" +
        "- Create a new anonymous session\n\n" +
        "Continue?"
    );

    if (confirmed) {
        localStorage.removeItem('relay_anon_id');
        localStorage.removeItem('relay_anon_usage');
        window.location.reload();
    }
}
```

Add button to HTML (in anon-badge div):

```html
<button id="clear-data-btn" style="margin-left:0.5rem; font-size:0.75rem; background:none; border:none; color:#888; cursor:pointer;">
    Clear Data
</button>
```

Bind in init():

```javascript
document.getElementById('clear-data-btn').addEventListener('click', () => this.clearMyData());
```

---

## Deployment Checklist

Before deploying to production:

- [ ] All 5 critical fixes implemented
- [ ] Tests passing (see Testing Checklist)
- [ ] Redis configured and accessible
- [ ] REDIS_URL set in production environment
- [ ] RELAY_ENV=production
- [ ] HTTPS enforced (HSTS header verified)
- [ ] Rate limits tested (5/min for anonymous)
- [ ] Quota limits tested (20/hr, 100 total)
- [ ] Session validation tested
- [ ] Error messages sanitized (no stack traces)
- [ ] Privacy policy link added
- [ ] "Clear My Data" button added
- [ ] Security audit re-run after fixes

---

## Estimated Total Time: 4-6 hours

1. Server-side quota enforcement: 2-3 hours
2. Rate limiting: 30 min
3. Input validation: 30 min
4. Session ID validation: 1 hour
5. Error sanitization: 30 min
6. GDPR UI (privacy link + clear button): 30 min
7. Testing: 1 hour

---

## Need Help?

Refer to full audit: `SECURITY_AUDIT_MAGIC_BOX_R0.5.txt`

Contact: Security team / Tech lead
