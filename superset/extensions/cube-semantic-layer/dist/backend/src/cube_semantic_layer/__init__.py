"""Cube as a Superset 7 semantic layer (SIP-182).

Superset asks the provider for views, metrics and dimensions, and sends it a
SemanticQuery for every chart. This provider answers both through Cube's REST API:

  /cubejs-api/v1/meta  -> semantic views (public Cube views), metrics, dimensions
  /cubejs-api/v1/load  -> query results

Cube does the SQL generation and the joins; Superset never sees the warehouse.
Loaded as a local extension (LOCAL_EXTENSIONS in superset_config.py).
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from typing import Any

import jwt
import pyarrow as pa
import requests
from pydantic import BaseModel, Field
from superset_core.semantic_layers.config import build_configuration_schema
from superset_core.semantic_layers.decorators import semantic_layer
from superset_core.semantic_layers.layer import SemanticLayer
from superset_core.semantic_layers.types import (
    AdhocExpression,
    AggregationType,
    Dimension,
    Filter,
    Grain,
    Grains,
    Metric,
    Operator,
    OrderDirection,
    SemanticQuery,
    SemanticRequest,
    SemanticResult,
)
from superset_core.semantic_layers.view import SemanticView

# Superset grain -> Cube granularity
GRAINS: dict[Grain, str] = {
    Grains.DAY: "day",
    Grains.WEEK: "week",
    Grains.MONTH: "month",
    Grains.QUARTER: "quarter",
    Grains.YEAR: "year",
}

AGGREGATIONS = {
    "count": AggregationType.COUNT,
    "countDistinct": AggregationType.COUNT_DISTINCT,
    "countDistinctApprox": AggregationType.COUNT_DISTINCT,
    "sum": AggregationType.SUM,
    "avg": AggregationType.AVG,
    "min": AggregationType.MIN,
    "max": AggregationType.MAX,
}

DEFAULT_LIMIT = 10000


class CubeConfiguration(BaseModel):
    cube_url: str = Field(
        default="http://cube:4000",
        title="Cube URL",
        description="Base URL of the Cube REST API (without /cubejs-api).",
    )
    api_secret: str = Field(
        title="API secret",
        description="CUBEJS_API_SECRET, used to sign the JWT sent to Cube.",
        json_schema_extra={"format": "password", "writeOnly": True},
    )
    include_cubes: bool = Field(
        default=False,
        title="Include cubes",
        description="Also expose public cubes, not only Cube views.",
    )


class CubeClient:
    def __init__(self, config: CubeConfiguration):
        self.url = config.cube_url.rstrip("/") + "/cubejs-api/v1"
        self.secret = config.api_secret

    def _headers(self) -> dict[str, str]:
        token = jwt.encode({"exp": int(time.time()) + 300}, self.secret, algorithm="HS256")
        return {"Authorization": token, "Content-Type": "application/json"}

    def meta(self) -> dict[str, Any]:
        r = requests.get(f"{self.url}/meta", headers=self._headers(), timeout=60)
        r.raise_for_status()
        return r.json()

    def load(self, query: dict[str, Any]) -> dict[str, Any]:
        """POST /load; Cube answers "Continue wait" while a query is still running."""
        deadline = time.time() + 300
        while True:
            r = requests.post(f"{self.url}/load", headers=self._headers(),
                              data=json.dumps({"query": query}), timeout=120)
            body = r.json()
            if body.get("error") == "Continue wait" and time.time() < deadline:
                time.sleep(1)
                continue
            if not r.ok or body.get("error"):
                raise RuntimeError(f"Cube /load failed ({r.status_code}): {body.get('error', r.text[:500])}")
            return body


def _short(member: str) -> str:
    return member.split(".", 1)[1]


def _arrow_type(cube_type: str) -> pa.DataType:
    return {
        "string": pa.string(),
        "number": pa.float64(),
        "boolean": pa.bool_(),
        "time": pa.timestamp("ms"),
    }.get(cube_type, pa.string())


def _convert(value: Any, dtype: pa.DataType) -> Any:
    """Cube returns numbers and timestamps as strings."""
    if value is None:
        return None
    if pa.types.is_integer(dtype):
        return int(float(value))
    if pa.types.is_floating(dtype):
        return float(value)
    if pa.types.is_boolean(dtype):
        return value if isinstance(value, bool) else str(value).lower() == "true"
    if pa.types.is_timestamp(dtype):
        return datetime.fromisoformat(str(value).replace("Z", ""))
    return str(value)


def _filter_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


class CubeView(SemanticView):
    features = frozenset()

    def __init__(self, client: CubeClient, meta: dict[str, Any]):
        self.client = client
        self.name = meta["name"]
        self.description = meta.get("description")
        self._dimensions: set[Dimension] = set()
        for d in meta["dimensions"]:
            if not d.get("public", True):
                continue
            common = {
                "name": _short(d["name"]),
                "type": _arrow_type(d["type"]),
                "description": d.get("description"),
                "verbose_name": d.get("shortTitle"),
                "metadata": {"member": d["name"]},
            }
            self._dimensions.add(Dimension(id=d["name"], definition=d["name"], **common))
            if d["type"] == "time":
                for grain, granularity in GRAINS.items():
                    self._dimensions.add(Dimension(
                        id=f"{d['name']}.{granularity}", definition=d["name"], grain=grain,
                        **{**common, "metadata": {"member": d["name"], "granularity": granularity}},
                    ))
        self._metrics: set[Metric] = set()
        for m in meta["measures"]:
            if not m.get("public", True):
                continue
            agg = m.get("aggType")
            is_count = agg in ("count", "countDistinct", "countDistinctApprox")
            self._metrics.add(Metric(
                id=m["name"],
                name=_short(m["name"]),
                type=pa.int64() if is_count else pa.float64(),
                definition=m.get("aliasMember") or m["name"],
                description=m.get("description"),
                aggregation=AGGREGATIONS.get(agg, AggregationType.OTHER),
                verbose_name=m.get("shortTitle"),
                d3format=(m.get("formatDescription") or {}).get("specifier"),
            ))

    # -- identity (views are kept in sets)
    def uid(self) -> str:
        return f"cube:{self.name}"

    def __hash__(self) -> int:
        return hash(self.uid())

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CubeView) and other.uid() == self.uid()

    # -- metadata
    def get_dimensions(self) -> set[Dimension]:
        return self._dimensions

    def get_metrics(self) -> set[Metric]:
        return self._metrics

    def get_compatible_metrics(self, selected_metrics, selected_dimensions) -> set[Metric]:
        return self._metrics  # a Cube view is pre-joined: everything is compatible

    def get_compatible_dimensions(self, selected_metrics, selected_dimensions) -> set[Dimension]:
        return self._dimensions

    # -- queries
    def get_table(self, query: SemanticQuery) -> SemanticResult:
        cube_query = self._to_cube_query(query)
        body = self.client.load(cube_query)
        return SemanticResult(requests=[self._request(cube_query)],
                              results=self._to_arrow(body["data"], query.dimensions, query.metrics))

    def get_row_count(self, query: SemanticQuery) -> SemanticResult:
        cube_query = {**self._to_cube_query(query), "limit": 1, "total": True}
        cube_query.pop("offset", None)
        body = self.client.load(cube_query)
        return SemanticResult(requests=[self._request(cube_query)],
                              results=pa.table({"rowcount": pa.array([body.get("total") or 0], pa.int64())}))

    def get_values(self, dimension: Dimension, filters: set[Filter] | None = None) -> SemanticResult:
        query = SemanticQuery(metrics=[], dimensions=[dimension], filters=filters, limit=DEFAULT_LIMIT)
        return self.get_table(query)

    # -- translation
    def _to_cube_query(self, query: SemanticQuery) -> dict[str, Any]:
        cube: dict[str, Any] = {
            "measures": [m.id for m in query.metrics],
            "dimensions": [],
            "timeDimensions": [],
            "filters": [],
            "limit": query.limit or DEFAULT_LIMIT,
        }
        for d in query.dimensions:
            if d.grain is not None:
                cube["timeDimensions"].append({"dimension": d.definition,
                                               "granularity": d.metadata["granularity"]})
            else:
                cube["dimensions"].append(d.definition)
        for f in sorted(query.filters or [], key=repr):
            cube["filters"].append(self._to_cube_filter(f))
        if query.order:
            cube["order"] = [[self._order_member(e), "asc" if d == OrderDirection.ASC else "desc"]
                             for e, d in query.order]
        if query.offset:
            cube["offset"] = query.offset
        if query.group_limit is not None:
            raise ValueError("Cube semantic layer does not support series limits")
        return cube

    @staticmethod
    def _order_member(element: Metric | Dimension | AdhocExpression) -> str:
        if isinstance(element, AdhocExpression):
            raise ValueError("Cube semantic layer does not support custom SQL in ORDER BY")
        return element.definition if isinstance(element, Dimension) else element.id

    @staticmethod
    def _to_cube_filter(f: Filter) -> dict[str, Any]:
        if f.column is None or f.operator == Operator.ADHOC:
            raise ValueError("Cube semantic layer does not support custom SQL filters")
        member = f.column.definition if isinstance(f.column, Dimension) else f.column.id
        is_time = isinstance(f.column, Dimension) and pa.types.is_timestamp(f.column.type)
        values = f.value if isinstance(f.value, (tuple, frozenset, set, list)) else (f.value,)
        values = [_filter_value(v) for v in values if v is not None]
        op = f.operator

        if op == Operator.IS_NULL:
            return {"member": member, "operator": "notSet"}
        if op == Operator.IS_NOT_NULL:
            return {"member": member, "operator": "set"}
        if op in (Operator.LIKE, Operator.ILIKE, Operator.NOT_LIKE, Operator.NOT_ILIKE):
            raw = values[0]
            negate = op in (Operator.NOT_LIKE, Operator.NOT_ILIKE)
            text = raw.strip("%")
            if raw.startswith("%") and raw.endswith("%") or "%" not in raw:
                cube_op = "notContains" if negate else "contains"
            elif raw.endswith("%"):
                cube_op = "notStartsWith" if negate else "startsWith"
            else:
                cube_op = "notEndsWith" if negate else "endsWith"
            return {"member": member, "operator": cube_op, "values": [text]}

        mapping = {
            Operator.EQUALS: "equals", Operator.IN: "equals",
            Operator.NOT_EQUALS: "notEquals", Operator.NOT_IN: "notEquals",
            Operator.GREATER_THAN: "afterDate" if is_time else "gt",
            Operator.GREATER_THAN_OR_EQUAL: "afterOrOnDate" if is_time else "gte",
            Operator.LESS_THAN: "beforeDate" if is_time else "lt",
            Operator.LESS_THAN_OR_EQUAL: "beforeOrOnDate" if is_time else "lte",
        }
        if op not in mapping:
            raise ValueError(f"Cube semantic layer does not support operator {op.value}")
        return {"member": member, "operator": mapping[op], "values": values}

    @staticmethod
    def _to_arrow(rows: list[dict[str, Any]], dimensions: list[Dimension],
                  metrics: list[Metric]) -> pa.Table:
        columns = {}
        for d in dimensions:
            key = d.definition if d.grain is None else f"{d.definition}.{d.metadata['granularity']}"
            columns[d.name] = pa.array([_convert(r.get(key), d.type) for r in rows], type=d.type)
        for m in metrics:
            columns[m.name] = pa.array([_convert(r.get(m.id), m.type) for r in rows], type=m.type)
        return pa.table(columns)

    @staticmethod
    def _request(cube_query: dict[str, Any]) -> SemanticRequest:
        return SemanticRequest(type="Cube REST /load", definition=json.dumps(cube_query, indent=2))


@semantic_layer(id="cube", name="Cube", description="Cube semantic layer through its REST API")
class CubeSemanticLayer(SemanticLayer[CubeConfiguration, CubeView]):
    configuration_class = CubeConfiguration

    def __init__(self, config: CubeConfiguration):
        self.config = config
        self.client = CubeClient(config)

    @classmethod
    def from_configuration(cls, configuration: dict[str, Any]) -> CubeSemanticLayer:
        return cls(CubeConfiguration.model_validate(configuration))

    @classmethod
    def get_configuration_schema(cls, configuration: CubeConfiguration | None = None) -> dict[str, Any]:
        return build_configuration_schema(CubeConfiguration, configuration)

    @classmethod
    def get_runtime_schema(cls, configuration: CubeConfiguration,
                           runtime_data: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"type": "object", "properties": {}}  # nothing to choose at runtime

    def _view_metas(self) -> list[dict[str, Any]]:
        kinds = {"view", "cube"} if self.config.include_cubes else {"view"}
        return [c for c in self.client.meta()["cubes"]
                if c.get("type", "cube") in kinds and c.get("public", True)]

    def get_semantic_views(self, runtime_configuration: dict[str, Any]) -> set[CubeView]:
        return {CubeView(self.client, meta) for meta in self._view_metas()}

    def get_semantic_view(self, name: str, additional_configuration: dict[str, Any]) -> CubeView:
        for meta in self._view_metas():
            if meta["name"] == name:
                return CubeView(self.client, meta)
        raise ValueError(f"Cube view {name} not found")
