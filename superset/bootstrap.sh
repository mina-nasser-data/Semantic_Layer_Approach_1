#!/usr/bin/env bash
# Prepares the metadata DB and admin user, then starts the web server.
# Every step is safe to re-run on each container start.
set -euo pipefail

superset db upgrade
superset fab create-admin \
  --username "${ADMIN_USERNAME}" --password "${ADMIN_PASSWORD}" \
  --firstname Admin --lastname User --email admin@example.local || true
superset init

exec /app/docker/entrypoints/run-server.sh
