"""
Fail-Closed Startup Security Validation

Enforces that staging/production deployments have proper security configuration.
Will HALT startup with RuntimeError if critical secrets are missing or insecure.

Environment Variable Requirements (staging/production only):
- SUPABASE_JWT_SECRET: Must be set, not "dev-*", length >= 32
- MEMORY_TENANT_HMAC_KEY: Must be set, not "dev-*", length >= 32
- CORS_ORIGINS: Must be explicit comma-separated list (no wildcard "*")

Development mode (RELAY_ENV=development or unset):
- No validation performed (allows default values for local dev)
"""

import os


def enforce_fail_closed() -> None:
    """
    Validate security configuration on startup.

    Raises:
        RuntimeError: If in staging/production and security config is invalid

    Examples:
        Valid staging config:
        - RELAY_ENV=staging
        - SUPABASE_JWT_SECRET=<64-char hex string>
        - MEMORY_TENANT_HMAC_KEY=<64-char hex string>
        - CORS_ORIGINS=https://relay.ai,https://app.relay.ai

        Invalid (will raise):
        - SUPABASE_JWT_SECRET=dev-secret-key
        - MEMORY_TENANT_HMAC_KEY=dev-hmac-key
        - CORS_ORIGINS=*
    """
    env = os.getenv("RELAY_ENV", "development").lower()

    # Only enforce in staging/production
    if env not in {"staging", "production"}:
        return

    problems: list[str] = []

    # Validate SUPABASE_JWT_SECRET
    supa = os.getenv("SUPABASE_JWT_SECRET", "")
    if not supa or supa == "dev-secret-key" or len(supa) < 32:
        problems.append("SUPABASE_JWT_SECRET invalid (must be set, not 'dev-*', len >= 32)")

    # Validate MEMORY_TENANT_HMAC_KEY
    hmac_key = os.getenv("MEMORY_TENANT_HMAC_KEY", "")
    if not hmac_key or hmac_key.startswith("dev-") or len(hmac_key) < 32:
        problems.append("MEMORY_TENANT_HMAC_KEY invalid (must be set, not 'dev-*', len >= 32)")

    # Validate CORS_ORIGINS
    cors = os.getenv("CORS_ORIGINS", "")
    if not cors or cors.strip() == "*":
        problems.append("CORS_ORIGINS must be an explicit allowlist (no wildcard '*')")
    elif "," not in cors:
        problems.append("CORS_ORIGINS must be comma-separated list of origins")

    # Fail closed if any problems
    if problems:
        raise RuntimeError(
            f"Fail-closed startup validation failed in {env.upper()} environment:\n"
            + "\n".join(f"  - {p}" for p in problems)
            + "\n\nSet RELAY_ENV=development to bypass for local development."
        )
