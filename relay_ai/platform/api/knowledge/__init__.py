"""Knowledge API module - file ingestion and vector search with JWT+RLS+AAD security."""

from .api import router as knowledge_router
from .db.asyncpg_client import close_pool, init_pool, with_user_conn, SecurityError
from .schemas import (
    ErrorResponse,
    FileIndexRequest,
    FileUploadRequest,
    SearchRequest,
)

__all__ = [
    "knowledge_router",
    "FileUploadRequest",
    "FileIndexRequest",
    "SearchRequest",
    "ErrorResponse",
    "close_pool",
    "init_pool",
    "with_user_conn",
    "SecurityError",
]
