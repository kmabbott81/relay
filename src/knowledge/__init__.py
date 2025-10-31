"""Knowledge API module - file ingestion and vector search with JWT+RLS+AAD security."""

from src.knowledge.api import router
from src.knowledge.schemas import (
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
