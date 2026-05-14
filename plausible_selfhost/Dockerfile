# Plausible CE — image officielle Plausible/Community Edition v2+
#
# Cette image embarque UNIQUEMENT le Plausible Phoenix app. Postgres et
# Clickhouse sont des dépendances externes (cf. fly.toml secrets).
#
# Le script deploy.ps1 exécute la migration UNE FOIS dans une machine
# ephemere (fly machine run /app/migrate.sh) AVANT d'autoriser l'app
# principale à démarrer. Du coup ici la CMD reste "run" (= start direct).

FROM ghcr.io/plausible/community-edition:v2.1.4

ENV LANG=fr_FR.UTF-8 LC_ALL=fr_FR.UTF-8

EXPOSE 8000
