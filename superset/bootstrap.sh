#!/usr/bin/env bash
# Prepares the metadata DB and admin user, then starts the web server.
# Every step is safe to re-run on each container start.
set -euo pipefail

superset db upgrade
superset fab create-admin \
  --username "${ADMIN_USERNAME}" --password "${ADMIN_PASSWORD}" \
  --firstname Admin --lastname User --email admin@example.local || true
superset init

# Connection to Cube (external semantic layer). Creates it on the first start,
# updates the URI on later starts. Cube views then appear as tables in schema "public".
if [ -n "${CUBE_URI:-}" ]; then
  superset set-database-uri --database_name Cube --uri "${CUBE_URI}"
fi

exec /app/docker/entrypoints/run-server.sh
