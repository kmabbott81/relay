"""Magic Box streaming module (Sprint 61b - R0.5).

Security-hardened SSE streaming with:
- Supabase JWT auth + anonymous session tokens
- Server-side rate limiting (per-user, per-IP)
- Quota enforcement (hourly + total)
- Input validation (length, format, whitelist)
- Error sanitization (no stack traces)
"""
