"""
Knowledge API Adapter Module

Re-exports production-proven Knowledge API from src/knowledge without modification.
This adapter allows new code to import from relay_ai.platform.api.knowledge
while the physical files remain in src/knowledge until gradual migration.

CRITICAL: This is read-only. Do NOT modify src/knowledge code through this adapter.
"""

import sys
from pathlib import Path

# Add repository root to Python path to find src/
REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import Knowledge API router and functions from src/knowledge
# These are production-proven R2 modules. Do NOT modify.
try:
    from src.knowledge.api import router as knowledge_router
    from src.knowledge.db.asyncpg_client import (
        SecurityError,
        close_pool,
        execute_mutation,
        execute_query,
        execute_query_one,
        get_connection,
        init_pool,
        with_user_conn,
    )
except ImportError as e:
    import warnings

    warnings.warn(f"Knowledge API import failed: {e}. Ensure src/knowledge exists.")
    # Define stub to prevent import failures during testing
    knowledge_router = None
    init_pool = None
    close_pool = None
    get_connection = None
    with_user_conn = None
    execute_query = None
    execute_query_one = None
    execute_mutation = None
    SecurityError = Exception

__all__ = [
    "knowledge_router",
    "init_pool",
    "close_pool",
    "get_connection",
    "with_user_conn",
    "execute_query",
    "execute_query_one",
    "execute_mutation",
    "SecurityError",
]
