#!/usr/bin/env python3
"""Sync a folder of Superset dataset YAML (the native semantic layer) into Superset.

Steps:
  1. Render  - fill ${VAR} / ${VAR:-default} placeholders from the environment.
  2. Validate - YAML parses, uuids unique, metric names valid, references resolve.
  3. Import  - POST databases/ to /api/v1/database/import/, then the whole folder to
               /api/v1/dataset/import/ (both overwrite=true).
  4. Smoke test (optional) - run every metric once through /api/v1/chart/data.

Usage:
  python sync.py ./semantic --validate-only     # CI check, no Superset needed
  python sync.py ./semantic --smoke-test        # one-shot deploy (CI/CD)
  python sync.py ./semantic --watch             # local: re-sync on every file change

Environment: SUPERSET_URL, SUPERSET_USERNAME, SUPERSET_PASSWORD,
             SUPERSET_AUTH_PROVIDER (db|ldap, default db),
             SUPERSET_DB_PASSWORDS (optional JSON: {"databases/Trino.yaml": "secret"}),
             plus any variable referenced in the YAML (e.g. TRINO_URI).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import requests
import yaml

PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
METRIC_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def log(msg: str) -> None:
    print(f"[sync] {msg}", flush=True)


# ---------------------------------------------------------------- render
def render(text: str, path: str) -> str:
    def sub(m: re.Match) -> str:
        name, default = m.group(1), m.group(2)
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            return default
        raise ValueError(f"{path}: environment variable {name} is not set")

    return PLACEHOLDER.sub(sub, text)


def load_bundle(root: Path) -> dict[str, str]:
    """Return {relative/path.yaml: rendered text} for every YAML file under root."""
    files = {}
    for p in sorted(root.rglob("*.y*ml")):
        rel = p.relative_to(root).as_posix()
        files[rel] = render(p.read_text(encoding="utf-8"), rel)
    return files


# ---------------------------------------------------------------- validate
def validate(files: dict[str, str]) -> list[dict]:
    errors: list[str] = []
    if "metadata.yaml" not in files:
        errors.append("metadata.yaml is missing at the bundle root")

    docs = {}
    for rel, text in files.items():
        try:
            docs[rel] = yaml.safe_load(text) or {}
        except yaml.YAMLError as e:
            errors.append(f"{rel}: invalid YAML: {e}")

    db_uuids = {d.get("uuid") for r, d in docs.items() if r.startswith("databases/")}
    seen: dict[str, str] = {}
    datasets = []
    for rel, d in docs.items():
        if rel == "metadata.yaml":
            continue
        uid = str(d.get("uuid") or "")
        if not uid:
            errors.append(f"{rel}: uuid is required")
        elif uid in seen:
            errors.append(f"{rel}: uuid {uid} already used by {seen[uid]}")
        else:
            seen[uid] = rel
        if not rel.startswith("datasets/"):
            continue

        if d.get("database_uuid") not in db_uuids:
            errors.append(f"{rel}: database_uuid does not match any file in databases/")
        names = set()
        for m in d.get("metrics") or []:
            name = m.get("metric_name", "")
            if not METRIC_NAME.match(name):
                errors.append(f"{rel}: metric '{name}' must be snake_case")
            if name in names:
                errors.append(f"{rel}: metric '{name}' defined twice")
            names.add(name)
            if not m.get("expression"):
                errors.append(f"{rel}: metric '{name}' has no expression")
            if not m.get("description"):
                errors.append(f"{rel}: metric '{name}' needs a description")
        cols = {c.get("column_name") for c in d.get("columns") or []}
        if d.get("main_dttm_col") and d["main_dttm_col"] not in cols:
            errors.append(f"{rel}: main_dttm_col '{d['main_dttm_col']}' is not in columns")
        datasets.append({"file": rel, "table_name": d.get("table_name"), "uuid": uid,
                         "metrics": sorted(names), "columns": sorted(c for c in cols if c)})

    if errors:
        raise ValueError("validation failed:\n  - " + "\n  - ".join(errors))
    return datasets


def make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, text in files.items():
            z.writestr(f"semantic_layer/{rel}", text)
    return buf.getvalue()


def database_files(files: dict[str, str]) -> dict[str, str]:
    """Databases-only bundle. Superset's dataset import never updates an existing
    database, so connections are imported on their own with overwrite."""
    out = {rel: t for rel, t in files.items() if rel.startswith("databases/")}
    out["metadata.yaml"] = "version: 1.0.0\ntype: Database\ntimestamp: '2026-01-01T00:00:00+00:00'\n"
    return out


# ---------------------------------------------------------------- Superset API
class Superset:
    def __init__(self, url: str, username: str, password: str, provider: str):
        self.url = url.rstrip("/")
        self.s = requests.Session()
        self.creds = {"username": username, "password": password,
                      "provider": provider, "refresh": True}

    def wait_until_up(self, timeout: int = 300) -> None:
        deadline = time.time() + timeout
        while True:
            try:
                if self.s.get(f"{self.url}/health", timeout=5).ok:
                    return
            except requests.RequestException:
                pass
            if time.time() > deadline:
                raise RuntimeError(f"Superset at {self.url} not reachable")
            time.sleep(5)

    def login(self) -> None:
        r = self.s.post(f"{self.url}/api/v1/security/login", json=self.creds, timeout=30)
        r.raise_for_status()
        self.s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        r = self.s.get(f"{self.url}/api/v1/security/csrf_token/", timeout=30)
        r.raise_for_status()
        self.s.headers.update({"X-CSRFToken": r.json()["result"], "Referer": self.url})

    def import_bundle(self, zip_bytes: bytes, kind: str) -> None:
        """kind: 'database' or 'dataset'."""
        data = {"overwrite": "true"}
        if os.environ.get("SUPERSET_DB_PASSWORDS"):
            data["passwords"] = os.environ["SUPERSET_DB_PASSWORDS"]
        r = self.s.post(f"{self.url}/api/v1/{kind}/import/",
                        files={"formData": ("semantic_layer.zip", zip_bytes, "application/zip")},
                        data=data, timeout=120)
        if not r.ok:
            raise RuntimeError(f"{kind} import failed ({r.status_code}): {r.text[:2000]}")

    def dataset_id(self, table_name: str, uuid: str) -> int:
        q = f"(filters:!((col:table_name,opr:eq,value:'{table_name}')),page_size:100)"
        r = self.s.get(f"{self.url}/api/v1/dataset/", params={"q": q}, timeout=30)
        r.raise_for_status()
        for row in r.json()["result"]:
            detail = self.s.get(f"{self.url}/api/v1/dataset/{row['id']}", timeout=30).json()
            if str(detail["result"].get("uuid")) == uuid:
                return row["id"]
        raise RuntimeError(f"dataset {table_name} ({uuid}) not found after import")

    def run_metric(self, ds_id: int, metric: str) -> None:
        self._query(ds_id, {"metrics": [metric], "columns": [], "row_limit": 1})

    def run_columns(self, ds_id: int, columns: list[str]) -> None:
        """SELECT <all declared columns> LIMIT 1: catches columns missing in the table."""
        self._query(ds_id, {"metrics": [], "columns": columns, "row_limit": 1})

    def _query(self, ds_id: int, query: dict) -> None:
        body = {"datasource": {"id": ds_id, "type": "table"}, "queries": [query],
                "result_format": "json", "result_type": "full", "force": True}
        r = self.s.post(f"{self.url}/api/v1/chart/data", json=body, timeout=120)
        if not r.ok:
            raise RuntimeError(f"{r.status_code}: {r.text[:500]}")
        for q in r.json().get("result", []):
            if q.get("error"):
                raise RuntimeError(q["error"])


# ---------------------------------------------------------------- main flow
def sync_once(root: Path, args) -> None:
    files = load_bundle(root)
    datasets = validate(files)
    n_metrics = sum(len(d["metrics"]) for d in datasets)
    log(f"valid: {len(datasets)} datasets, {n_metrics} metrics")
    if args.validate_only:
        return

    sup = Superset(os.environ["SUPERSET_URL"], os.environ["SUPERSET_USERNAME"],
                   os.environ["SUPERSET_PASSWORD"], os.environ.get("SUPERSET_AUTH_PROVIDER", "db"))
    sup.wait_until_up()
    sup.login()
    sup.import_bundle(make_zip(database_files(files)), "database")
    sup.import_bundle(make_zip(files), "dataset")
    log("imported into Superset (databases, then datasets)")

    if args.smoke_test:
        failures = []

        def attempt(label: str, fn) -> None:
            for i in range(3):
                try:
                    fn()
                    return
                except Exception as e:  # noqa: BLE001
                    if i == 2:
                        failures.append(f"{label}: {e}")
                    else:
                        time.sleep(10)

        for d in datasets:
            ds_id = sup.dataset_id(d["table_name"], d["uuid"])
            if d["columns"]:
                attempt(f"{d['table_name']} columns", lambda: sup.run_columns(ds_id, d["columns"]))
            for m in d["metrics"]:
                attempt(f"{d['table_name']}.{m}", lambda m=m: sup.run_metric(ds_id, m))
        if failures:
            raise RuntimeError("smoke test failed:\n  - " + "\n  - ".join(failures))
        log(f"smoke test passed: columns + {n_metrics} metrics ran on the warehouse")


def fingerprint(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*.y*ml")):
        h.update(p.as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle", type=Path, help="folder containing metadata.yaml, databases/, datasets/")
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--smoke-test", action="store_true")
    ap.add_argument("--watch", action="store_true", help="keep running and re-sync on changes")
    ap.add_argument("--interval", type=int, default=5, help="watch poll interval in seconds")
    args = ap.parse_args()

    if not args.watch:
        try:
            sync_once(args.bundle, args)
            return 0
        except Exception as e:  # noqa: BLE001
            log(f"ERROR {e}")
            return 1

    last = None
    log(f"watching {args.bundle} every {args.interval}s")
    while True:
        current = fingerprint(args.bundle)
        if current != last:
            try:
                sync_once(args.bundle, args)
            except Exception as e:  # noqa: BLE001
                log(f"ERROR {e}")
            last = current
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
