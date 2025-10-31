FROM prom/prometheus:latest

# Copy configuration files
COPY prometheus.yml /etc/prometheus/prometheus.yml
COPY alerts.yml /etc/prometheus/alerts.yml

# Copy and set up entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose default port
EXPOSE $PORT

# Use shell form to allow environment variable expansion
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
