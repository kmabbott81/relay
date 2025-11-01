"""Knowledge API module - file ingestion and vector search with JWT+RLS+AAD security."""

from .api import router
from .schemas import (
    ErrorResponse,
    FileIndexRequest,
    FileUploadRequest,
    SearchRequest,
)

__all__ = [
    "router",
    "FileUploadRequest",
    "FileIndexRequest",
    "SearchRequest",
    "ErrorResponse",
]
