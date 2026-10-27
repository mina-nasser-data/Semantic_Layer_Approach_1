"""Two fixes for the "Cube" database connection (Cube's SQL API, Postgres protocol).

1. Saved metrics: a dataset created on the Cube connection (or "Sync columns from source")
   gets one saved metric per measure of the Cube view: net_amount = MEASURE(net_amount),
   with the title and description from cube/model.
2. Cube has no pg_catalog.pg_opclass, which SQLAlchemy 2 (Superset 7) reads to list a
   table's indexes; that broke "Add dataset" on Cube. Superset does not need the indexes,
   so a database that can't list them has none.

superset_config.py imports this file at startup.
"""
import os

import jwt
import requests
from sqlalchemy.dialects.postgresql.base import PGDialect
from sqlalchemy.exc import DBAPIError
from superset.db_engine_specs.postgres import PostgresEngineSpec

default_metrics = PostgresEngineSpec.get_metrics
default_indexes = PGDialect.get_multi_indexes


def get_metrics(database, inspector, table):
    if database.database_name != "Cube":
        return default_metrics(database, inspector, table)
    token = jwt.encode({}, os.environ["CUBE_API_SECRET"])
    meta = requests.get(os.environ["CUBE_URL"] + "/cubejs-api/v1/meta", headers={"Authorization": token}).json()
    measures = next(view["measures"] for view in meta["cubes"] if view["name"] == table.table)
    return [{"metric_name": m["name"].split(".")[1], "expression": f"MEASURE({m['name'].split('.')[1]})",
             "verbose_name": m.get("shortTitle"), "description": m.get("description")} for m in measures]


def get_multi_indexes(self, connection, schema=None, filter_names=None, **kw):
    try:
        return default_indexes(self, connection, schema=schema, filter_names=filter_names, **kw)
    except DBAPIError:
        return {(schema, name): [] for name in filter_names or []}


PostgresEngineSpec.get_metrics = staticmethod(get_metrics)
PGDialect.get_multi_indexes = get_multi_indexes
