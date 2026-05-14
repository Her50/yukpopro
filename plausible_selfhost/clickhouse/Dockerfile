FROM clickhouse/clickhouse-server:24.3-alpine

# Override config pour autoriser les connexions inter-app Fly (interne)
# et limiter la conso mémoire ~1.6Go (sur RAM 2Go).
COPY clickhouse-config.xml /etc/clickhouse-server/config.d/yukpo.xml
COPY clickhouse-users.xml /etc/clickhouse-server/users.d/yukpo.xml

# Healthcheck Fly va prober TCP 9000 via le service défini dans fly.toml.
EXPOSE 8123 9000
