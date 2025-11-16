# Archive Rotation Demo Workflow - Demonstrates tiered storage lifecycle

import hashlib
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


def generate_markdown_artifact(index: int, tenant_id: str, include_checksum: bool = True):
    artifact_id = f"demo_doc_{index:04d}.md"
    lines = [
        f"# Archive Demo Document {index}",
        "",
        f"**Generated:** {datetime.utcnow().isoformat()}",
        f"**Tenant:** {tenant_id}",
        f"**Document ID:** {index:04d}",
        "",
        "## Summary",
        "",
        "Test document for archive rotation demo.",
        f"Document number {index} in the series.",
        "",
        "## Content",
        "",
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
    ]
    content = "\n".join(lines).encode("utf-8")
    if include_checksum:
        content += f"\n---\n**Checksum:** {hashlib.sha256(content).hexdigest()}\n".encode()
    return artifact_id, content


print("Demo stub created")
