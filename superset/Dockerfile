ARG SUPERSET_VERSION=6.0.0
FROM apache/superset:${SUPERSET_VERSION}

USER root
# The default image already has the Postgres driver for the metadata DB.
# Add the Trino driver for the warehouse.
RUN . /app/.venv/bin/activate && uv pip install --no-cache trino

COPY --chmod=755 bootstrap.sh /app/bootstrap.sh

USER superset
CMD ["/app/bootstrap.sh"]
