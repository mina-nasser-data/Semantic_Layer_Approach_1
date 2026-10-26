"""Native semantic layer for Superset 7 (SIP-182): views defined in YAML.

Every YAML file in ./semantic_views is one semantic view (source table + joins,
dimensions, metrics). sync/semantic_views.py uploads them all into this layer's
configuration through the REST API (PUT /api/v1/semantic_layer/<uuid>), so the
definitions live in Superset and editing a file never changes a view's id.

For each chart, Superset sends a SemanticQuery; this provider compiles it to SQL
in the connection's dialect (time grains come from Superset's engine spec) and
runs it on that Superset database connection, e.g. Trino.
"""
from __future__ import annotations

import math
from datetime import date, datetime, time as dtime
from decimal import Decimal
from typing import Any, Literal

import pyarrow as pa
from pydantic import BaseModel, Field
from superset_core.semantic_layers.config import build_configuration_schema
from superset_core.semantic_layers.decorators import semantic_layer
from superset_core.semantic_layers.layer import SemanticLayer
from superset_core.semantic_layers.types import (
    AdhocExpression,
    Dimension,
    Filter,
    Grains,
    Metric,
    Operator,
    OrderDirection,
    PredicateType,
    SemanticQuery,
    SemanticRequest,
    SemanticResult,
)
from superset_core.semantic_layers.view import SemanticView

GRAINS = [Grains.DAY, Grains.WEEK, Grains.MONTH, Grains.QUARTER, Grains.YEAR]
DEFAULT_LIMIT = 10000

ARROW_TYPES = {
    "string": pa.string(),
    "number": pa.float64(),
    "integer": pa.int64(),
    "boolean": pa.bool_(),
    "time": pa.timestamp("us"),
    "date": pa.timestamp("us"),
}


# ---------------------------------------------------------------- YAML schema
class JoinDefinition(BaseModel):
    table: str
    alias: str
    condition: str                    # ON clause ("on" itself is a YAML boolean)
    type: Literal["left", "inner", "right", "full"] = "left"


class SourceDefinition(BaseModel):
    table: str | None = None          # fully qualified, e.g. warehouse.mart.fact_transaction
    alias: str = "t"
    sql: str | None = None            # alternative to table: any SELECT
    joins: list[JoinDefinition] = Field(default_factory=list)


class DimensionDefinition(BaseModel):
    name: str
    expression: str | None = None     # SQL over the source; defaults to the name
    type: Literal["string", "number", "integer", "boolean", "time", "date"] = "string"
    label: str | None = None
    description: str | None = None


class MetricDefinition(BaseModel):
    name: str
    expression: str                   # SQL aggregate, e.g. SUM(t.amount)
    type: Literal["number", "integer"] = "number"
    label: str | None = None
    description: str | None = None
    d3format: str | None = None


class ViewDefinition(BaseModel):
    name: str
    description: str | None = None
    database: str | None = None       # Superset database connection name
    source: SourceDefinition
    dimensions: list[DimensionDefinition]
    metrics: list[MetricDefinition]


class NativeConfiguration(BaseModel):
    default_database: str = Field(
        default="Trino",
        title="Default database",
        description="Superset database connection used by views that do not set one.",
    )
    views: dict[str, ViewDefinition] = Field(
        default_factory=dict,
        title="Views",
        description="View definitions, uploaded from ./semantic_views by sync/semantic_views.py.",
    )


# ---------------------------------------------------------------- helpers
def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _to_python(value: Any, dtype: pa.DataType) -> Any:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if hasattr(value, "to_pydatetime"):          # pandas Timestamp
        value = value.to_pydatetime()
    if str(value) == "NaT":
        return None
    if pa.types.is_timestamp(dtype):
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
        if isinstance(value, date):
            return datetime.combine(value, dtime())
        return datetime.fromisoformat(str(value))
    if pa.types.is_integer(dtype):
        return int(value)
    if pa.types.is_floating(dtype):
        return float(value)
    if pa.types.is_boolean(dtype):
        return bool(value)
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


class NativeView(SemanticView):
    features = frozenset()

    def __init__(self, definition: ViewDefinition, default_database: str):
        self.definition = definition
        self.name = definition.name
        self.description = definition.description
        self.database_name = definition.database or default_database
        self._grain_sql: dict[str, str] | None = None

        self._dimensions: set[Dimension] = set()
        for d in definition.dimensions:
            expr = d.expression or d.name
            common = {"name": d.name, "type": ARROW_TYPES[d.type], "description": d.description,
                      "verbose_name": d.label}
            self._dimensions.add(Dimension(id=d.name, definition=expr, **common))
            if d.type in ("time", "date"):
                for grain in GRAINS:
                    self._dimensions.add(Dimension(id=f"{d.name}__{grain.representation}",
                                                   definition=expr, grain=grain, **common))
        self._metrics = {
            Metric(id=m.name, name=m.name, type=ARROW_TYPES[m.type], definition=m.expression,
                   description=m.description, verbose_name=m.label, d3format=m.d3format)
            for m in definition.metrics
        }

    # -- identity (views are kept in sets)
    def uid(self) -> str:
        return f"native:{self.name}"

    def __hash__(self) -> int:
        return hash(self.uid())

    def __eq__(self, other: object) -> bool:
        return isinstance(other, NativeView) and other.uid() == self.uid()

    # -- metadata
    def get_dimensions(self) -> set[Dimension]:
        return self._dimensions

    def get_metrics(self) -> set[Metric]:
        return self._metrics

    def get_compatible_metrics(self, selected_metrics, selected_dimensions) -> set[Metric]:
        return self._metrics  # one flat view: everything is compatible

    def get_compatible_dimensions(self, selected_metrics, selected_dimensions) -> set[Dimension]:
        return self._dimensions

    # -- database access
    def _database(self):
        from superset import db
        from superset.models.core import Database

        database = db.session.query(Database).filter_by(database_name=self.database_name).one_or_none()
        if database is None:
            raise ValueError(f"Database connection '{self.database_name}' not found in Superset")
        return database

    def _run(self, sql: str, columns: list[tuple[str, pa.DataType]]) -> SemanticResult:
        df = self._database().get_df(sql)
        table = pa.table({
            name: pa.array([_to_python(v, dtype) for v in df[name].tolist()], type=dtype)
            for name, dtype in columns
        })
        return SemanticResult(requests=[SemanticRequest(type="SQL", definition=sql)], results=table)

    # -- queries
    def get_table(self, query: SemanticQuery) -> SemanticResult:
        sql = self._select(query, with_limit=True)
        columns = [(d.name, d.type) for d in query.dimensions] + [(m.name, m.type) for m in query.metrics]
        return self._run(sql, columns)

    def get_row_count(self, query: SemanticQuery) -> SemanticResult:
        sql = f"SELECT COUNT(*) AS rowcount FROM (\n{self._select(query, with_limit=False)}\n) q"
        return self._run(sql, [("rowcount", pa.int64())])

    def get_values(self, dimension: Dimension, filters: set[Filter] | None = None) -> SemanticResult:
        query = SemanticQuery(metrics=[], dimensions=[dimension], filters=filters,
                              order=[(dimension, OrderDirection.ASC)], limit=DEFAULT_LIMIT)
        return self.get_table(query)

    # -- SQL compilation
    def _from(self) -> str:
        src = self.definition.source
        if src.sql:
            sql = f"FROM (\n{src.sql.strip().rstrip(';')}\n) {src.alias}"
        elif src.table:
            sql = f"FROM {src.table} {src.alias}"
        else:
            raise ValueError(f"View {self.name}: source needs table or sql")
        for j in src.joins:
            sql += f"\n{j.type.upper()} JOIN {j.table} {j.alias} ON {j.condition}"
        return sql

    def _dimension_sql(self, d: Dimension) -> str:
        if pa.types.is_timestamp(d.type):
            if d.grain is None:
                return f"CAST({d.definition} AS TIMESTAMP)"
            if self._grain_sql is None:
                self._grain_sql = self._database().db_engine_spec.get_time_grain_expressions()
            template = self._grain_sql.get(d.grain.representation)
            if template is None:
                raise ValueError(f"Time grain {d.grain.name} is not supported by {self.database_name}")
            return template.format(col=d.definition)
        return d.definition

    def _literal(self, value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, (int, float, Decimal)):
            return str(value)
        if isinstance(value, datetime):
            return f"TIMESTAMP '{value.replace(tzinfo=None).isoformat(sep=' ')}'"
        if isinstance(value, date):
            return f"DATE '{value.isoformat()}'"
        return "'" + str(value).replace("'", "''") + "'"

    def _predicate(self, f: Filter) -> str:
        if f.column is None or f.operator == Operator.ADHOC:
            raise ValueError("Custom SQL filters are not supported on semantic views")
        col = (f.column.definition if isinstance(f.column, Metric)
               else (f"CAST({f.column.definition} AS TIMESTAMP)" if pa.types.is_timestamp(f.column.type)
                     else f.column.definition))
        op, value = f.operator, f.value
        if op == Operator.IS_NULL:
            return f"{col} IS NULL"
        if op == Operator.IS_NOT_NULL:
            return f"{col} IS NOT NULL"
        if op in (Operator.IN, Operator.NOT_IN):
            values = value if isinstance(value, (tuple, list, set, frozenset)) else (value,)
            items = ", ".join(self._literal(v) for v in sorted(values, key=str))
            return f"{col} {op.value} ({items})"
        if op in (Operator.ILIKE, Operator.NOT_ILIKE):
            neg = "NOT " if op == Operator.NOT_ILIKE else ""
            return f"LOWER({col}) {neg}LIKE LOWER({self._literal(value)})"
        return f"{col} {op.value} {self._literal(value)}"

    def _select(self, query: SemanticQuery, with_limit: bool) -> str:
        if query.group_limit is not None:
            raise ValueError("Series limit is not supported on native semantic views")
        select = [f"{self._dimension_sql(d)} AS {_quote(d.name)}" for d in query.dimensions]
        select += [f"{m.definition} AS {_quote(m.name)}" for m in query.metrics]
        if not select:
            raise ValueError("Query needs at least one dimension or metric")
        filters = sorted(query.filters or [], key=repr)
        where = [self._predicate(f) for f in filters if f.type == PredicateType.WHERE]
        having = [self._predicate(f) for f in filters if f.type == PredicateType.HAVING]

        sql = "SELECT " + ",\n       ".join(select) + "\n" + self._from()
        if where:
            sql += "\nWHERE " + "\n  AND ".join(where)
        if query.dimensions and query.metrics:
            sql += "\nGROUP BY " + ", ".join(str(i + 1) for i in range(len(query.dimensions)))
        elif query.dimensions:
            sql = sql.replace("SELECT ", "SELECT DISTINCT ", 1)
        if having:
            sql += "\nHAVING " + "\n   AND ".join(having)
        if query.order:
            parts = []
            for element, direction in query.order:
                if isinstance(element, AdhocExpression):
                    raise ValueError("Custom SQL in ORDER BY is not supported on semantic views")
                parts.append(f"{_quote(element.name)} {direction.value}")
            sql += "\nORDER BY " + ", ".join(parts)
        if with_limit:
            if query.offset:
                sql += f"\nOFFSET {int(query.offset)}"
            sql += f"\nLIMIT {int(query.limit or DEFAULT_LIMIT)}"
        return sql


@semantic_layer(id="native", name="Native (YAML)",
                description="Semantic views defined in YAML, run as SQL on a Superset database")
class NativeSemanticLayer(SemanticLayer[NativeConfiguration, NativeView]):
    configuration_class = NativeConfiguration

    def __init__(self, config: NativeConfiguration):
        self.config = config

    @classmethod
    def from_configuration(cls, configuration: dict[str, Any]) -> NativeSemanticLayer:
        return cls(NativeConfiguration.model_validate(configuration))

    @classmethod
    def get_configuration_schema(cls, configuration: NativeConfiguration | None = None) -> dict[str, Any]:
        return build_configuration_schema(NativeConfiguration, configuration)

    @classmethod
    def get_runtime_schema(cls, configuration: NativeConfiguration,
                           runtime_data: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"type": "object", "properties": {}}  # nothing to choose at runtime

    def get_semantic_views(self, runtime_configuration: dict[str, Any]) -> set[NativeView]:
        return {NativeView(v, self.config.default_database) for v in self.config.views.values()}

    def get_semantic_view(self, name: str, additional_configuration: dict[str, Any]) -> NativeView:
        if name not in self.config.views:
            raise ValueError(f"Semantic view {name} is not defined in this layer")
        return NativeView(self.config.views[name], self.config.default_database)
