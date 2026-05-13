# Plausible CE — image officielle Plausible/Community Edition v2+
# Multi-service (Plausible + Postgres + Clickhouse) géré par docker-compose
# mais Fly impose 1 process par machine → on délègue Postgres et Clickhouse
# à des apps Fly séparées OU des managed Postgres (Neon) et Clickhouse Cloud.
#
# Cette image embarque UNIQUEMENT le Plausible Phoenix app. Postgres et
# Clickhouse sont des dépendances externes (cf. fly.toml secrets).

FROM ghcr.io/plausible/community-edition:v2.1.4

ENV LANG=fr_FR.UTF-8 LC_ALL=fr_FR.UTF-8

EXPOSE 8000
