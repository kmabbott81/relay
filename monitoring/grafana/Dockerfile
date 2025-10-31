FROM grafana/grafana:latest

EXPOSE 3000

ENV GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:-admin}
ENV GF_SECURITY_ADMIN_USER=${GRAFANA_ADMIN_USER:-admin}
ENV GF_SERVER_ROOT_URL=${GF_SERVER_ROOT_URL:-https://grafana.railway.app}
ENV GF_INSTALL_PLUGINS=grafana-worldmap-panel

# Copy provisioning configs
COPY provisioning/datasources /etc/grafana/provisioning/datasources
COPY provisioning/dashboards /etc/grafana/provisioning/dashboards

RUN mkdir -p /var/lib/grafana/dashboards
