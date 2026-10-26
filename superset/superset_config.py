import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]

# Superset 7.0: semantic layers (SIP-182) as a datasource type, plus the
# /api/v1/semantic_layer/ REST API. Off by default upstream.
# Superset ships no semantic layer provider; ENABLE_EXTENSIONS loads ours from
# ./superset/extensions:
#   native-semantic-layer - views from ./semantic_views YAML, run as SQL on Trino
#   cube-semantic-layer   - views from Cube's REST API
FEATURE_FLAGS = {"SEMANTIC_LAYERS": True, "ENABLE_EXTENSIONS": True}
LOCAL_EXTENSIONS = [
    "/app/extensions/native-semantic-layer",
    "/app/extensions/cube-semantic-layer",
]

# The sync script logs in through the REST API with a database (AUTH_DB) user.
# If production uses LDAP/OAuth, keep a dedicated service account that can
# log in through /api/v1/security/login (LDAP works with provider "ldap").
