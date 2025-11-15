"""
Memory/RLS Security Adapter Module

Re-exports production-proven RLS (Row-Level Security) helpers from src/memory/rls.py.
This adapter allows new code to import from relay_ai.platform.security.memory
while the physical file remains in src/memory until gradual migration.

CRITICAL: This is read-only. Do NOT modify src/memory/rls.py through this adapter.
"""

import sys
from pathlib import Path

# Add repository root to Python path
REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import RLS helpers from src/memory/rls.py
# These are production-proven R2 modules. Do NOT modify.
try:
    from relay_ai.memory.rls import (
        RLSMiddlewareContext,
        clear_rls_session_variable,
        get_rls_context,
        hmac_user,
        set_rls_context,
        set_rls_session_variable,
        verify_rls_isolation,
    )
except ImportError as e:
    import warnings

    warnings.warn(f"RLS module import failed: {e}. Ensure src/memory/rls.py exists.")
    # Define stubs
    hmac_user = None
    set_rls_context = None
    set_rls_session_variable = None
    clear_rls_session_variable = None
    verify_rls_isolation = None
    RLSMiddlewareContext = None
    get_rls_context = None

__all__ = [
    "hmac_user",
    "set_rls_context",
    "set_rls_session_variable",
    "clear_rls_session_variable",
    "verify_rls_isolation",
    "RLSMiddlewareContext",
    "get_rls_context",
]
