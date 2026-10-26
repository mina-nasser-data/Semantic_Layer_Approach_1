#!/usr/bin/env python3
"""Sync semantic views into Superset 7's semantic layers (SEMANTIC_LAYERS flag).

Two layers, both shown in Superset's dataset list next to normal datasets:

  Trino (native) - every YAML file in ./semantic_views is one view. The files are
                   uploaded into the layer's configuration through the API
                   (PUT /api/v1/semantic_layer/<uuid>); Superset compiles each chart
                   query to SQL and runs it on the "Trino" database connection.
  Cube           - every public view in ./cube/model/views (read live from Cube's
                   REST API) becomes a semantic view; Cube writes the SQL.

Each cycle:
  1. Validate the YAML files (also the only step of --validate-only, no Superset needed).
  2. Create the two layers if missing; upload the YAML when a file changed.
  3. Reconcile each layer: add a Superset semantic view for every new view, update
     descriptions, delete views whose file / Cube view is gone (unless charts use them).
  4. Smoke test (optional) - run every native metric and all dimensions once.

Usage:
  python semantic_views.py ./semantic_views --validate-only
  python semantic_views.py ./semantic_views --smoke-test          # one shot (CI/CD)
  python semantic_views.py ./semantic_views --watch --smoke-test  # local, re-sync on change

Environment: SUPERSET_URL, SUPERSET_USERNAME, SUPERSET_PASSWORD, SUPERSET_AUTH_PROVIDER,
             CUBE_URL (default http://cube:4000), CUBE_API_SECRET (no secret = no Cube layer).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml

from sync import METRIC_NAME, Superset, fingerprint, log, render

NATIVE_LAYER = "Trino"
CUBE_LAYER = "Cube"
DIMENSION_TYPES = {"string", "number", "integer", "boolean", "date", "time"}


# ---------------------------------------------------------------- load + validate
def load_views(root: Path) -> dict[str, dict]:
    """Return {view name: definition} for every YAML file under root."""
    errors: list[str] = []
    views: dict[str, dict] = {}
    files: dict[str, str] = {}
    for p in sorted(root.rglob("*.y*ml")):
        rel = p.relative_to(root).as_posix()
        try:
            v = yaml.safe_load(render(p.read_text(encoding="utf-8"), rel)) or {}
        except (yaml.YAMLError, ValueError) as e:
            errors.append(f"{rel}: {e}")
            continue
        errors += [f"{rel}: {e}" for e in validate_view(v)]
        name = v.get("name")
        if name in files:
            errors.append(f"{rel}: view name '{name}' already used by {files[name]}")
        elif name:
            files[name] = rel
            views[name] = v
    if errors:
        raise ValueError("validation failed:\n  - " + "\n  - ".join(errors))
    return views


def validate_view(v: dict) -> list[str]:
    errors = []
    if not METRIC_NAME.match(str(v.get("name", ""))):
        errors.append("name is required and must be snake_case")
    src = v.get("source") or {}
    if bool(src.get("table")) == bool(src.get("sql")):
        errors.append("source needs exactly one of table or sql")
    for j in src.get("joins") or []:
        if not all(j.get(k) for k in ("table", "alias", "condition")):
            errors.append(f"join {j} needs table, alias and condition")
    names: set[str] = set()
    for d in v.get("dimensions") or []:
        n = d.get("name", "")
        if not METRIC_NAME.match(n):
            errors.append(f"dimension '{n}' must be snake_case")
        if d.get("type", "string") not in DIMENSION_TYPES:
            errors.append(f"dimension '{n}': type must be one of {sorted(DIMENSION_TYPES)}")
        if n in names:
            errors.append(f"'{n}' defined twice")
        names.add(n)
    for m in v.get("metrics") or []:
        n = m.get("name", "")
        if not METRIC_NAME.match(n):
            errors.append(f"metric '{n}' must be snake_case")
        if n in names:
            errors.append(f"'{n}' defined twice")
        names.add(n)
        if not m.get("expression"):
            errors.append(f"metric '{n}' has no expression")
        if not m.get("description"):
            errors.append(f"metric '{n}' needs a description")
    if not v.get("metrics"):
        errors.append("at least one metric is required")
    return errors


# ---------------------------------------------------------------- Superset API
class SemanticLayers(Superset):
    def _json(self, method: str, path: str, **kw) -> dict:
        r = self.s.request(method, f"{self.url}/api/v1/{path}", timeout=120, **kw)
        if not r.ok:
            raise RuntimeError(f"{method} {path} failed ({r.status_code}): {r.text[:1000]}")
        return r.json() if r.content else {}

    def layer_type(self, suffix: str) -> str:
        for t in self._json("GET", "semantic_layer/types")["result"]:
            if t["id"].endswith(f".{suffix}"):
                return t["id"]
        raise RuntimeError(f"semantic layer type '{suffix}' is not installed (extension not loaded?)")

    def layer(self, name: str) -> dict | None:
        for layer in self._json("GET", "semantic_layer/")["result"]:
            if layer["name"] == name:
                return self._json("GET", f"semantic_layer/{layer['uuid']}")["result"]
        return None

    def ensure_layer(self, name: str, type_suffix: str, description: str, configuration: dict) -> dict:
        layer = self.layer(name)
        if layer is None:
            self._json("POST", "semantic_layer/", json={
                "name": name, "type": self.layer_type(type_suffix),
                "description": description, "configuration": configuration})
            log(f"created semantic layer {name}")
            layer = self.layer(name)
        return layer

    def update_layer_configuration(self, uuid: str, configuration: dict) -> None:
        self._json("PUT", f"semantic_layer/{uuid}", json={"configuration": configuration})

    def available_views(self, uuid: str) -> list[str]:
        return [v["name"] for v in self._json("POST", f"semantic_layer/{uuid}/views", json={})["result"]]

    def superset_views(self, uuid: str) -> dict[str, dict]:
        """Semantic views already in Superset for this layer: {name: row}."""
        out, page = {}, 0
        while True:
            rows = self._json("GET", "datasource/", params={"q": f"(page:{page},page_size:100)"})["result"]
            for row in rows:
                if row.get("kind") == "semantic_view" and (row.get("database") or {}).get("id") == uuid:
                    out[row["table_name"]] = row
            if len(rows) < 100:
                return out
            page += 1

    def charts_using(self, view_id: int) -> int:
        count, page = 0, 0
        while True:
            q = f"(columns:!(id,datasource_id,datasource_type),page:{page},page_size:100)"
            rows = self._json("GET", "chart/", params={"q": q})["result"]
            count += sum(1 for c in rows if c.get("datasource_type") == "semantic_view"
                         and c.get("datasource_id") == view_id)
            if len(rows) < 100:
                return count
            page += 1

    def reconcile(self, layer: dict, descriptions: dict[str, str | None]) -> dict[str, int]:
        """Make the layer's Superset views match what the provider offers. Returns {name: id}."""
        uuid, name = layer["uuid"], layer["name"]
        wanted = set(self.available_views(uuid))
        current = self.superset_views(uuid)

        new = sorted(wanted - current.keys())
        if new:
            body = {"views": [{"name": v, "semantic_layer_uuid": uuid, "configuration": {},
                               "description": descriptions.get(v)} for v in new]}
            result = self._json("POST", "semantic_view/", json=body)["result"]
            for err in result.get("errors", []):
                log(f"ERROR {name}.{err['name']}: {err['error']}")
            for v in result.get("created", []):
                log(f"added semantic view {name}.{v['name']}")
            current = self.superset_views(uuid)

        for v in sorted(current.keys() - wanted):
            charts = self.charts_using(current[v]["id"])
            if charts:
                log(f"WARNING {name}.{v}: source removed but {charts} chart(s) use it, not deleted")
                continue
            self._json("DELETE", f"semantic_view/{current[v]['id']}")
            log(f"deleted semantic view {name}.{v}: its source was removed")
            del current[v]

        for v, row in current.items():
            if v in descriptions and descriptions[v] != row.get("description"):
                self._json("PUT", f"semantic_view/{row['id']}", json={"description": descriptions[v]})
                log(f"updated description of {name}.{v}")
        return {v: row["id"] for v, row in current.items()}

    def smoke_test(self, view_id: int, view: dict) -> list[str]:
        """Run every metric alone, then all dimensions with the first metric."""
        failures = []
        dims = [d["name"] for d in view.get("dimensions") or []]
        queries = [(f"metric {m['name']}", {"metrics": [m["name"]], "columns": [], "row_limit": 1})
                   for m in view["metrics"]]
        if dims:
            queries.append(("all dimensions", {"metrics": [view["metrics"][0]["name"]],
                                               "columns": dims, "row_limit": 1}))
        for label, q in queries:
            body = {"datasource": {"id": view_id, "type": "semantic_view"}, "queries": [q],
                    "result_format": "json", "result_type": "full", "force": True}
            r = self.s.post(f"{self.url}/api/v1/chart/data", json=body, timeout=120)
            error = None if r.ok else f"{r.status_code}: {r.text[:300]}"
            if r.ok:
                error = next((x["error"] for x in r.json().get("result", []) if x.get("error")), None)
            if error:
                failures.append(f"{view['name']} {label}: {error}")
        return failures


# ---------------------------------------------------------------- main flow
def connect() -> SemanticLayers:
    sup = SemanticLayers(os.environ["SUPERSET_URL"], os.environ["SUPERSET_USERNAME"],
                         os.environ["SUPERSET_PASSWORD"], os.environ.get("SUPERSET_AUTH_PROVIDER", "db"))
    sup.wait_until_up()
    sup.login()
    return sup


def sync_native(sup: SemanticLayers, views: dict[str, dict], smoke: bool) -> None:
    layer = sup.ensure_layer(NATIVE_LAYER, "native",
                             "Native semantic views from ./semantic_views, run on the Trino connection",
                             {"default_database": "Trino", "views": {}})
    current = (layer.get("configuration") or {}).get("views") or {}
    upload = dict(views)
    # A removed file whose view still has charts keeps its last definition, so the charts keep working.
    used = sup.superset_views(layer["uuid"])
    for name in current.keys() - views.keys():
        if name in used and sup.charts_using(used[name]["id"]):
            upload[name] = current[name]
    if json.dumps(upload, sort_keys=True, default=str) != json.dumps(current, sort_keys=True, default=str):
        sup.update_layer_configuration(layer["uuid"], {**layer["configuration"], "views": upload})
        log(f"uploaded {len(views)} view definition(s) into semantic layer {NATIVE_LAYER}")
    ids = sup.reconcile(layer, {n: v.get("description") for n, v in upload.items()})

    if smoke:
        failures = [f for name, v in views.items() if name in ids for f in sup.smoke_test(ids[name], v)]
        if failures:
            raise RuntimeError("smoke test failed:\n  - " + "\n  - ".join(failures))
        n = sum(len(v["metrics"]) for v in views.values())
        log(f"smoke test passed: {len(views)} native view(s), {n} metrics ran on Trino")


def sync_cube(sup: SemanticLayers) -> None:
    secret = os.environ.get("CUBE_API_SECRET")
    if not secret:
        return
    layer = sup.ensure_layer(CUBE_LAYER, "cube", "Cube views (./cube/model/views) through the Cube REST API",
                             {"cube_url": os.environ.get("CUBE_URL", "http://cube:4000"), "api_secret": secret})
    sup.reconcile(layer, {})


def run_once(root: Path, args, native_changed: bool) -> None:
    views = load_views(root)
    if native_changed:
        log(f"valid: {len(views)} native view(s)")
    if args.validate_only:
        return
    sup = connect()
    if native_changed:
        sync_native(sup, views, args.smoke_test)
    sync_cube(sup)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("views", type=Path, help="folder of native semantic view YAML files")
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--smoke-test", action="store_true")
    ap.add_argument("--watch", action="store_true", help="keep running; pick up new YAML files and Cube views")
    ap.add_argument("--interval", type=int, default=10, help="watch poll interval in seconds")
    args = ap.parse_args()

    if not args.watch:
        try:
            run_once(args.views, args, native_changed=True)
            return 0
        except Exception as e:  # noqa: BLE001
            log(f"ERROR {e}")
            return 1

    last = None
    log(f"watching {args.views} and Cube every {args.interval}s")
    while True:
        current = fingerprint(args.views)
        try:
            run_once(args.views, args, native_changed=current != last)
        except Exception as e:  # noqa: BLE001
            log(f"ERROR {e}")
        last = current
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
