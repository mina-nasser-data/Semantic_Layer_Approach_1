import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]

# The sync script logs in through the REST API with a database (AUTH_DB) user.
# If production uses LDAP/OAuth, keep a dedicated service account that can
# log in through /api/v1/security/login (LDAP works with provider "ldap").
