"""Keeps Superset in sync with two folders, checked every 5 seconds:

  semantic/        datasets and their saved metrics (Superset's YAML export format)
  semantic_views/  one YAML file = one semantic view, stored in the semantic layer "Trino"

Usage: python sync.py ./semantic ./semantic_views
Environment: SUPERSET_URL, SUPERSET_USERNAME, SUPERSET_PASSWORD
"""
import io
import os
import sys
import time
import zipfile
from pathlib import Path

import requests
import yaml

URL = os.environ.get("SUPERSET_URL", "http://localhost:8088")
DATASETS, VIEWS = Path(sys.argv[1]), Path(sys.argv[2])


def login():
    s = requests.Session()
    r = s.post(f"{URL}/api/v1/security/login", json={
        "username": os.environ["SUPERSET_USERNAME"], "password": os.environ["SUPERSET_PASSWORD"],
        "provider": "db", "refresh": True})
    r.raise_for_status()
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    s.headers["X-CSRFToken"] = s.get(f"{URL}/api/v1/security/csrf_token/").json()["result"]
    s.headers["Referer"] = URL
    return s


def api(s, method, path, **kwargs):
    r = s.request(method, f"{URL}/api/v1/{path}", **kwargs)
    if not r.ok:
        raise RuntimeError(f"{method} {path}: {r.status_code} {r.text[:500]}")
    return r.json()


def sync_datasets(s):
    """Zip semantic/ and import it (creates or overwrites the datasets)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for file in DATASETS.rglob("*.y*ml"):
            z.write(file, f"bundle/{file.relative_to(DATASETS).as_posix()}")
    api(s, "POST", "dataset/import/", data={"overwrite": "true"},
        files={"formData": ("bundle.zip", buf.getvalue(), "application/zip")})
    print("imported the datasets in semantic/")


def sync_views(s):
    """Store the YAML in the layer "Trino", create a view per new file, delete removed ones."""
    views = {}
    for file in VIEWS.glob("*.y*ml"):
        view = yaml.safe_load(file.read_text(encoding="utf-8"))
        views[view["name"]] = view

    layer = next((l for l in api(s, "GET", "semantic_layer/")["result"] if l["name"] == "Trino"), None)
    if layer:
        api(s, "PUT", f"semantic_layer/{layer['uuid']}", json={"configuration": {"views": views}})
    else:  # first run (type "native" comes from superset/semantic_layer.py)
        layer = api(s, "POST", "semantic_layer/", json={"name": "Trino", "type": "native",
                                                        "configuration": {"views": views}})["result"]

    existing = {row["table_name"]: row["id"] for row in api(s, "GET", "datasource/?q=(page_size:100)")["result"]
                if row.get("kind") == "semantic_view" and row["database"]["id"] == layer["uuid"]}
    new = [{"name": name, "semantic_layer_uuid": layer["uuid"], "configuration": {}}
           for name in views if name not in existing]
    if new:
        api(s, "POST", "semantic_view/", json={"views": new})
    for name, view_id in existing.items():
        if name not in views:
            api(s, "DELETE", f"semantic_view/{view_id}")
    print(f"semantic views: {', '.join(views)}")


last = None
while True:
    files = [(f, f.stat().st_mtime) for folder in (DATASETS, VIEWS) for f in sorted(folder.rglob("*.y*ml"))]
    if files != last:
        try:
            s = login()
            sync_datasets(s)
            sync_views(s)
            last = files
        except Exception as e:  # Superset still starting, bad YAML, ...: retry next round
            print(f"ERROR {e}")
    time.sleep(5)
