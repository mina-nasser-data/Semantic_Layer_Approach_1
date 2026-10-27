import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]

# Superset 7.0: semantic layers + the /api/v1/semantic_layer/ REST API (off by default).
FEATURE_FLAGS = {"SEMANTIC_LAYERS": True}


def FLASK_APP_MUTATOR(app):
    import semantic_layer  # noqa: F401  semantic layer "native": runs ./semantic_views on Trino
    import cube_connection  # noqa: F401  Cube datasets: saved metrics + "Add dataset" fix
