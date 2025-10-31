#!/bin/sh
# Railway-compliant Grafana entrypoint
# Binds to $PORT environment variable from Railway

# Default to 3000 if PORT not set
PORT=${PORT:-3000}

# Set Grafana server configuration for Railway
export GF_SERVER_HTTP_PORT=${PORT}
export GF_SERVER_DOMAIN=${RAILWAY_STATIC_URL:-localhost}
export GF_SERVER_ROOT_URL=https://${RAILWAY_STATIC_URL:-localhost}/
export GF_SERVER_SERVE_FROM_SUB_PATH=false

echo "Starting Grafana on port $PORT..."
echo "Domain: $GF_SERVER_DOMAIN"
echo "Root URL: $GF_SERVER_ROOT_URL"

# Start Grafana
exec /run.sh
