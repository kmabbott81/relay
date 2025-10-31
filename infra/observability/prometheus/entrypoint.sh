#!/bin/sh
# Railway-compliant Prometheus entrypoint
# Binds to $PORT environment variable from Railway

# Default to 9090 if PORT not set
PORT=${PORT:-9090}

echo "Starting Prometheus on port $PORT..."

# Start Prometheus with Railway's PORT
exec /bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/prometheus \
  --web.console.libraries=/usr/share/prometheus/console_libraries \
  --web.console.templates=/usr/share/prometheus/consoles \
  --web.listen-address=0.0.0.0:${PORT} \
  --web.enable-lifecycle \
  --web.enable-admin-api
