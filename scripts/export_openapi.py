"""Export OpenAPI schema from FastAPI memory router."""
import json

from fastapi import FastAPI

from src.memory.api import router as memory_router

# Create minimal FastAPI app
app = FastAPI(
    title="Memory APIs", description="R1 Task D - Memory chunk indexing and retrieval", version="v1.0.0-phase4"
)

# Include memory router
app.include_router(memory_router, prefix="/api/v1/memory", tags=["Memory"])

# Export OpenAPI schema
schema = app.openapi()

# Write to file
with open("openapi.v1.json", "w") as f:
    json.dump(schema, f, indent=2)

# Print summary
endpoints = schema.get("paths", {})
print(f"[PASS] OpenAPI schema exported: {len(endpoints)} endpoints")
for path in endpoints:
    methods = list(endpoints[path].keys())
    print(f"  - {path}: {', '.join(methods).upper()}")

components = schema.get("components", {}).get("schemas", {})
print(f"[INFO] Schemas defined: {len(components)}")
print("[INFO] Schema saved to: openapi.v1.json")
