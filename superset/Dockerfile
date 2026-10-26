ARG SUPERSET_VERSION=7.0.0rc2
FROM apache/superset:${SUPERSET_VERSION}

USER root
# The official image is "lean": it has no Postgres driver, so add psycopg2
# for the metadata DB, plus the Trino driver for the warehouse.
RUN . /app/.venv/bin/activate && uv pip install --no-cache psycopg2-binary trino

COPY --chmod=755 bootstrap.sh /app/bootstrap.sh

USER superset
CMD ["/app/bootstrap.sh"]
