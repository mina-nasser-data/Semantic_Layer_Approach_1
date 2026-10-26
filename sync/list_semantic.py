import json
import os
import requests

URL = os.environ.get("SUPERSET_URL", "http://localhost:8088").rstrip("/")
s = requests.Session()

# Login
r = s.post(f"{URL}/api/v1/security/login", json={
    "username": os.environ.get("SUPERSET_USERNAME", "admin"),
    "password": os.environ.get("SUPERSET_PASSWORD", "admin"),
    "provider": os.environ.get("SUPERSET_AUTH_PROVIDER", "db"),
    "refresh": True,
}, timeout=30)
r.raise_for_status()
s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"

# Fetch all semantic layers (paginated)
layers, page = [], 0
while True:
    r = s.get(f"{URL}/api/v1/semantic_layer/",
              params={"q": f"(page:{page},page_size:100)"}, timeout=30)
    print(f"GET /api/v1/semantic_layer/ -> {r.status_code}")
    r.raise_for_status()
    body = r.json()
    batch = body.get("result", body if isinstance(body, list) else [])
    layers += batch
    if len(batch) < 100:
        break
    page += 1

# Raw response, so you can see every field the API returns
print(json.dumps(layers, indent=2, default=str))

# Short summary
print(f"\n=== {len(layers)} SEMANTIC LAYER(S) ===")
for l in layers:
    name = l.get("name") or l.get("semantic_layer_name") or l.get("title")
    print(f"  id={l.get('id')}  uuid={l.get('uuid')}  name={name}  type={l.get('type')}")
