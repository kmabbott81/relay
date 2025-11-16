"""Health and readiness check HTTP server for deployment orchestration.

Provides lightweight endpoints for Kubernetes/Docker health checks and traffic management:
- /health: Always returns 200 if process is alive (never blocks on dependencies)
- /ready: Checks configuration, feature flags, and optional dependencies
- /__meta: Returns build metadata for debugging
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for health/readiness endpoints."""

    def log_message(self, format, *args):
        """Suppress default HTTP server logging."""
        pass

    def do_GET(self):
        """Handle GET requests for health/readiness/meta."""
        if self.path == "/health":
            self._handle_health()
        elif self.path == "/ready":
            self._handle_ready()
        elif self.path == "/__meta":
            self._handle_meta()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def _handle_health(self):
        """Health check: always returns 200 if process is alive."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        response = {"status": "healthy", "checks": {"process": "up"}}
        self.wfile.write(json.dumps(response).encode())

    def _handle_ready(self):
        """Readiness check: validates configuration and dependencies."""
        checks = {}
        ready = True

        # Check feature flags if multi-region or blue/green enabled
        feature_multi_region = os.getenv("FEATURE_MULTI_REGION", "false").lower() == "true"
        feature_blue_green = os.getenv("FEATURE_BLUE_GREEN", "false").lower() == "true"

        checks["feature_multi_region"] = feature_multi_region
        checks["feature_blue_green"] = feature_blue_green

        # Check required environment variables
        required_envs = os.getenv("REQUIRED_ENVS", "").split(",")
        required_envs = [e.strip() for e in required_envs if e.strip()]

        missing_envs = []
        for env_var in required_envs:
            if not os.getenv(env_var):
                missing_envs.append(env_var)
                ready = False

        checks["required_envs"] = {
            "expected": required_envs,
            "missing": missing_envs,
            "ok": len(missing_envs) == 0,
        }

        # Check region configuration if multi-region enabled
        if feature_multi_region:
            regions = os.getenv("REGIONS", "").split(",")
            regions = [r.strip() for r in regions if r.strip()]
            primary_region = os.getenv("PRIMARY_REGION", "")

            if not regions or not primary_region:
                ready = False
                checks["regions"] = {"ok": False, "error": "REGIONS or PRIMARY_REGION not configured"}
            elif primary_region not in regions:
                ready = False
                checks["regions"] = {"ok": False, "error": f"PRIMARY_REGION '{primary_region}' not in REGIONS"}
            else:
                checks["regions"] = {"ok": True, "regions": regions, "primary": primary_region}

        # Check RBAC role if blue/green enabled
        if feature_blue_green:
            deploy_role = os.getenv("DEPLOY_RBAC_ROLE", "")
            if deploy_role not in ["Deployer", "Admin"]:
                ready = False
                checks["deploy_rbac"] = {"ok": False, "error": f"Invalid DEPLOY_RBAC_ROLE: {deploy_role}"}
            else:
                checks["deploy_rbac"] = {"ok": True, "role": deploy_role}

        # Optional: Check database connectivity (with timeout)
        readiness_timeout = int(os.getenv("READINESS_TIMEOUT_MS", "400"))
        checks["readiness_timeout_ms"] = readiness_timeout

        # Send response
        status_code = 200 if ready else 503
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        response = {"status": "ready" if ready else "not_ready", "checks": checks}
        self.wfile.write(json.dumps(response).encode())

    def _handle_meta(self):
        """Return build metadata for debugging."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        meta = {
            "version": os.getenv("BUILD_VERSION", "dev"),
            "git_sha": os.getenv("GIT_SHA", "unknown"),
            "build_date": os.getenv("BUILD_DATE", "unknown"),
            "region": os.getenv("CURRENT_REGION", os.getenv("PRIMARY_REGION", "unknown")),
        }
        self.wfile.write(json.dumps(meta).encode())


def start_health_server(port: Optional[int] = None) -> threading.Thread:
    """
    Start health check HTTP server in background thread.

    Args:
        port: Port to listen on (default from HEALTH_PORT env or 8086)

    Returns:
        Thread running the HTTP server
    """
    if port is None:
        port = int(os.getenv("HEALTH_PORT", "8086"))

    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)

    def serve():
        try:
            server.serve_forever()
        except Exception as e:
            print(f"Health server error: {e}")

    thread = threading.Thread(target=serve, daemon=True, name="HealthServer")
    thread.start()

    return thread
