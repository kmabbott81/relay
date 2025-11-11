#!/usr/bin/env python3
# Export OpenAPI v2 spec from Knowledge API (Pydantic + FastAPI)
# Usage: python scripts/export_openapi_v2.py

import json
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

# noqa: E402 - Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from relay_ai.knowledge.api import router as knowledge_router  # noqa: E402


def export_openapi_spec():
    """Generate and export OpenAPI v2 spec for Knowledge API"""

    # Create FastAPI app with Knowledge router
    app = FastAPI(
        title="Relay Knowledge API",
        description="File ingestion and vector search with JWT+RLS+AAD security",
        version="2.0.0",
    )
    app.include_router(knowledge_router)

    # Generate OpenAPI schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Save to file
    output_path = Path(__file__).parent.parent / "openapi.v2.json"

    with open(output_path, "w") as f:
        json.dump(openapi_schema, f, indent=2)

    print(f"[OK] OpenAPI spec exported to {output_path}")
    print(f"  - Endpoints: {len(openapi_schema.get('paths', {}))} paths")
    print(f"  - Schemas: {len(openapi_schema.get('components', {}).get('schemas', {}))} schemas")
    print(f"  - Size: {len(json.dumps(openapi_schema))} bytes")


if __name__ == "__main__":
    export_openapi_spec()
