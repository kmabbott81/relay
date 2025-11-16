"""
Stream API Adapter Module

Re-exports production-proven Stream API (auth, JWT) from src/stream without modification.
This adapter allows new code to import from relay_ai.platform.api.stream
while the physical files remain in src/stream until gradual migration.

CRITICAL: This is read-only. Do NOT modify src/stream code through this adapter.
"""

import sys
from pathlib import Path

# Add repository root to Python path
REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import Stream API auth and JWT functions from src/stream
# These are production-proven R1 modules. Do NOT modify.
try:
    from relay_ai.platform.api.stream.auth import (
        StreamPrincipal,
        check_jwt_and_get_user_hash,
        generate_anon_session_token,
        get_stream_principal,
        verify_supabase_jwt,
    )
except ImportError as e:
    import warnings

    warnings.warn(f"Stream API import failed: {e}. Ensure src/stream exists.")
    # Define stubs
    StreamPrincipal = None
    verify_supabase_jwt = None
    generate_anon_session_token = None
    get_stream_principal = None
    check_jwt_and_get_user_hash = None

__all__ = [
    "StreamPrincipal",
    "verify_supabase_jwt",
    "generate_anon_session_token",
    "get_stream_principal",
    "check_jwt_and_get_user_hash",
]
