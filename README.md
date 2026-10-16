# Superset native semantic layer as code

Datasets and metrics live as YAML in `semantic/`. A small sync script pushes them
into Superset through its REST API, locally on every file save, and from CI on
every merge. Nobody imports by hand.

```
semantic/*.yaml ──(git push)──► CI: validate → staging + smoke test → prod
      │
      └─(local, docker compose)──► semantic-sync container (watch) ──► Superset ──► Trino
```

## Layout

| Path | What it is |
|---|---|
| `semantic/metadata.yaml` | Bundle header Superset expects (`type: SqlaTable`) |
| `semantic/databases/*.yaml` | Warehouse connection; URI comes from `${TRINO_URI}` |
| `semantic/datasets/<db>/*.yaml` | One file per dataset: table or SQL, columns, **metrics** |
| `sync/sync.py` | Render `${VAR}` → validate → zip → `POST /api/v1/dataset/import/` → smoke test |
| `superset/` | Superset image + Trino driver, config, bootstrap |
| `trino/catalog/` | Trino catalogs (sample `tpch`; add your real sources here) |
| `.gitlab-ci.yml` | validate on MR, deploy to staging on MR, deploy to prod on merge |

## Run locally

```bash
cp .env.example .env          # set passwords / secret key
docker compose up -d --build
docker compose logs -f semantic-sync
```

Open http://localhost:8088. The datasets `orders` and `orders_by_customer`
appear with their metrics. Edit any file in `semantic/`, save, and within a
few seconds the sync container re-imports it.

## Add or change a metric

1. Edit the dataset file in `semantic/datasets/...` (or add a new file).
2. `docker compose logs semantic-sync` shows `valid`, `imported`, `smoke test passed`.
3. Commit, open a merge request. CI validates and deploys to staging; merge deploys to prod.

## Start from an existing dataset

Build it once in the Superset UI, then **Datasets → ⋮ → Export**. Unzip and
copy `datasets/...yaml` into `semantic/datasets/`, keep its `uuid`, point
`database_uuid` at `semantic/databases/Trino.yaml`, and add descriptions.

## Rules

- **`uuid` never changes.** A new uuid = a new duplicate dataset.
- **Don't rename metrics.** Charts reference metrics by name. Add a new one instead.
- **Deleting a metric in Git deletes it in Superset** (import runs with overwrite +
  sync). Check no chart uses it first.
- **Datasets removed from Git are not deleted** from Superset; remove them manually.
- **Credentials never go in Git**: use `${VAR}` placeholders and CI variables, or
  `SUPERSET_DB_PASSWORDS`.
- **Lock editing with permissions.** `is_managed_externally: true` marks the dataset as
  Git-owned, but Superset does not block edits through it. Give business users roles
  without write access to datasets; anything edited anyway is reset on the next deploy.
- Every metric needs `description` and `snake_case` name (enforced by `sync.py`).

## Production notes

- Use a dedicated service account for CI. Set `SUPERSET_AUTH_PROVIDER=ldap` if
  Superset authenticates against LDAP. OAuth-only logins can't be used by the script.
- Pin `SUPERSET_VERSION` / `TRINO_VERSION` to what the bank runs.
