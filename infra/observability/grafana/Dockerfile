FROM grafana/grafana:latest

# Copy provisioning configs
COPY provisioning /etc/grafana/provisioning

# Copy dashboards
COPY dashboards /var/lib/grafana/dashboards

# Copy custom entrypoint for Railway
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Environment variables for Railway
ENV GF_INSTALL_PLUGINS=grafana-worldmap-panel,grafana-piechart-panel

# Security hardening
ENV GF_SECURITY_ADMIN_USER=${GF_SECURITY_ADMIN_USER:-admin}
ENV GF_SECURITY_ADMIN_PASSWORD=${GF_SECURITY_ADMIN_PASSWORD:-canary2025}
ENV GF_SECURITY_ALLOW_EMBEDDING=true
ENV GF_SECURITY_COOKIE_SECURE=true

# Anonymous access for public dashboards (read-only)
ENV GF_AUTH_ANONYMOUS_ENABLED=false
ENV GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer

# Use our custom entrypoint
ENTRYPOINT ["/entrypoint.sh"]
