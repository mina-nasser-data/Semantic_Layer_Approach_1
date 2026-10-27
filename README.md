# Semantic layer POC: Superset native vs. Cube

This repo runs two ways of defining business metrics (net amount, reversal rate,
active customers, ...) once and using them in Superset, side by side on the same
Trino warehouse:

| | Approach 1: Native semantic layer | Approach 2: External semantic layer (Cube) |
|---|---|---|
| Where metrics live | Superset datasets, as YAML in `semantic/` | Cube data model, as YAML in `cube/model/` |
| How they reach Superset | `sync.py` imports them through the Superset REST API | Superset queries Cube live through a database connection |
| Who runs the SQL | Superset → Trino | Superset → Cube → Trino |

```
Approach 1   semantic/*.yaml ──(sync.py)──► Superset datasets + metrics ──────────► Trino ──► warehouse
Approach 2   cube/model/*.yml ──► Cube ◄──(SQL API, Postgres protocol)── Superset
                                   └──────────────────────────────────────────► Trino ──► warehouse
```

## Architecture

Everything runs in one `docker compose` stack. Both approaches share Superset,
Trino and the warehouse; they differ in where the metric definitions live and
how Superset gets them.

```
       Approach 1: Native                         Approach 2: Cube (external)

          Business user                                  Business user
                │                                              │
                ▼                                              ▼
semantic/ ──► Superset                                     Superset
(YAML)  sync  holds the metrics                            asks Cube for measures by name
                │                                              │  Postgres protocol :15432
                │                                              ▼
                │                              cube/model/ ──► Cube
                │                              (YAML)          holds the metrics, writes the joins
                ▼                                              ▼
              Trino                                          Trino
                │                                              │
                ▼                                              ▼
            Warehouse                                      Warehouse
```

The only difference is **where the semantic layer sits**: inside Superset
(Approach 1) or in Cube, between Superset and Trino (Approach 2).

| Component | Role | Approach |
|---|---|---|
| `sync` | Watches `semantic/` (imports datasets and metrics) and `semantic_views/` (one semantic view per file) | 1, Superset 7 |
| Superset | BI tool. Approach 1: holds the metrics. Approach 2: only queries Cube | both |
| `superset-db` | Superset's own metadata (users, charts, datasets, the imported metrics) | both |
| Cube | External semantic layer: reads `cube/model/`, turns semantic queries into Trino SQL | 2 |
| Trino | Query engine in front of the warehouse (and any future source) | both |
| `warehouse` | Sample banking star schema (`fact_transaction` + `dim_*`), stand-in for the bank's warehouse | both |

## Layout

| Path | What it is |
|---|---|
| `semantic/metadata.yaml` | Approach 1: bundle header Superset expects (`type: SqlaTable`) |
| `semantic/databases/*.yaml` | Approach 1: warehouse connection (Trino URI, no password) |
| `semantic/datasets/<db>/*.yaml` | Approach 1: one file per dataset: table or SQL, columns, **metrics** |
| `sync/sync.py` | Imports `semantic/` (datasets, overwrite) and syncs `semantic_views/` into the "Trino" semantic layer |
| `cube/model/cubes/*.yml` | Approach 2: one cube per warehouse table: dimensions, measures, joins |
| `cube/model/views/*.yml` | Approach 2: what Superset sees: flat "tables" assembled from the cubes |
| `semantic_views/*.yaml` | Superset 7: one file per semantic view (source, dimensions, metrics) |
| `superset/semantic_layer.py` | Superset 7: the semantic layer type "native" that turns chart queries into SQL on Trino |
| `superset/` | Superset image (Postgres + Trino drivers), config, bootstrap (also registers the Cube connection) |
| `trino/catalog/` | Trino catalog `warehouse` (sample star schema) |
| `warehouse/init/` | Sample banking star schema loaded into the `warehouse` Postgres |

## Getting started: from clone to Superset

You need **Git** and **Docker Desktop** (with Docker Compose), and these ports
free: 8088, 8080, 4000, 5433, 15432.

**1. Clone the project**

```bash
git clone <repo-url>
cd Semantic_Layer_POC
```

**2. Create your `.env` from the example**

```bash
cp .env.example .env                 # PowerShell: Copy-Item .env.example .env
```

Open `.env` and replace every `change-me` with your own value (letters and digits
only). To generate one: `python -c "import secrets; print(secrets.token_hex(32))"`.
`.env` is in `.gitignore`; never commit it.

**3. Start the stack**

```bash
docker compose up -d --build
```

The first run downloads and builds images, which takes a few minutes. The sample
warehouse is created automatically on the first start.

**4. Wait until the datasets are loaded**

```bash
docker compose logs -f sync
```

Wait for these lines, then press `Ctrl+C`:

```
imported the datasets in semantic/
semantic views: branch_performance, customer_segments, reversal_risk
```

**5. Open Superset**

Go to http://localhost:8088 and log in with `SUPERSET_ADMIN_USERNAME` /
`SUPERSET_ADMIN_PASSWORD` from your `.env`. Open **Datasets**: you see one dataset
per file in `semantic/datasets/`, each with its metrics. The **Cube** connection
(Approach 2) is under **Settings → Database Connections**.

**6. Add a new dataset (new YAML file)**

Every new YAML file needs its **own new `uuid`**. Never copy the `uuid` from another
file: two files with the same uuid overwrite each other, and an invalid uuid fails
the import, which blocks the whole sync. Generate one with:

```bash
python -c "import uuid; print(uuid.uuid4())"
```

Put it in the file's `uuid:` line, give the dataset its own `table_name`, save the
file in `semantic/datasets/Trino/`, and check `docker compose logs sync`.
Once a dataset is deployed, never change its uuid.

To stop: `docker compose down` (data is kept). To start again: `docker compose up -d`.

## Run locally

Variables in `.env` (see `.env.example`):

| Variable | Used by |
|---|---|
| `SUPERSET_VERSION`, `TRINO_VERSION` | Image versions (defaults: `7.0.0rc2`, `476`) |
| `SUPERSET_SECRET_KEY`, `SUPERSET_DB_PASSWORD` | Superset |
| `SUPERSET_ADMIN_USERNAME`, `SUPERSET_ADMIN_PASSWORD` | Superset admin; also used by `sync.py` |
| `WAREHOUSE_DB_PASSWORD` | Sample warehouse Postgres, read by Trino |
| `CUBE_API_SECRET` | Cube (signs API tokens) |
| `CUBE_SQL_PASSWORD` | Cube SQL API password; Superset's Cube connection uses it |

```bash
docker compose up -d --build
docker compose logs -f sync
```

| URL | What |
|---|---|
| http://localhost:8088 | Superset |
| http://localhost:4000 | Cube Playground: browse the model, run queries, see the SQL Cube generates |
| http://localhost:8080 | Trino |
| `localhost:5433` | Sample warehouse Postgres (DBeaver) |
| `localhost:15432` | Cube SQL API (Postgres protocol) |

---

## Approach 1: Native semantic layer (Superset datasets as code)

Datasets and metrics live as YAML in `semantic/`. A small sync script pushes them
into Superset through its REST API on every file save. Nobody imports by hand.

```
semantic/*.yaml ──► sync container (watch) ──► Superset ──► Trino
```

Locally, edit any file in `semantic/`, save, and within a few seconds the sync
container re-imports it. Datasets appear in Superset under **Datasets** with
their metrics, ready for charts.

### Flow

```
  semantic/datasets/*.yaml        1. Define datasets and metrics as YAML in Git
            │
            ▼
  sync.py                         2. Import (on every save)
            │  REST API
            ▼
  Superset datasets + metrics     3. The semantic layer lives here
            │  metric SQL inlined    A chart picks "net_amount"; Superset pastes its SQL
            ▼                        SUM(CASE WHEN NOT is_reversed THEN amount ELSE 0 END)
  Trino                           4. Runs the query
            │
            ▼
  Warehouse (mart.*)              5. Data
```

The metric's SQL is stored inside Superset, so the definition can only be used
by Superset.

### Add or change a metric

1. Edit the dataset file in `semantic/datasets/...` (or add a new file).
2. `docker compose logs sync` shows `imported the datasets in semantic/`.

### Start from an existing dataset

Build it once in the Superset UI, then **Datasets → ⋮ → Export**. Unzip and
copy `datasets/...yaml` into `semantic/datasets/`, keep its `uuid`, point
`database_uuid` at `semantic/databases/Trino.yaml`, and add descriptions.

### Rules

- **`uuid` never changes.** A new uuid = a new duplicate dataset. A new file needs a new,
  valid uuid (`[guid]::NewGuid()` in PowerShell).
- **One invalid file blocks the whole sync.** Superset imports the folder as one bundle;
  if one file fails, nothing is imported. Check `docker compose logs sync`.
- **Don't rename metrics.** Charts reference metrics by name. Add a new one instead.
- **Deleting a metric in Git deletes it in Superset** (import runs with overwrite).
  Check no chart uses it first.
- **Deleting a dataset file does not delete the dataset in Superset.** Superset's import
  only creates and updates; delete the dataset in the UI.
- **Only files inside `semantic/` are synced.** Copies kept elsewhere (e.g. drafts outside the
  repo) are not seen; edit the file in `semantic/datasets/`.
- **The database file only creates the connection.** Superset's dataset import never
  updates an existing connection; change its URI in the Superset UI.
- **Credentials never go in Git.** The Trino URI in `semantic/databases/Trino.yaml` has no
  password; a connection that needs one is set up in the Superset UI.
- **Lock editing with permissions.** `is_managed_externally: true` marks the dataset as
  Git-owned, but Superset does not block edits through it. Give business users roles
  without write access to datasets; anything edited anyway is reset on the next sync.

---

## Approach 2: External semantic layer (Cube)

[Cube Core](https://cube.dev) is a separate service that owns the business logic.
It reads its YAML model from `cube/model/`, generates SQL for Trino, and serves
the results to any client. Superset is one of those clients: it connects to
Cube's **SQL API**, which speaks the Postgres protocol, so to Superset Cube looks
like a Postgres database whose tables are the Cube views.

This approach is deliberately **separate from `semantic/`**: `sync.py` never touches Cube.

### Flow

```
  cube/model/cubes/*.yml          1. Define cubes (tables), joins and measures as YAML
  cube/model/views/*.yml             and the views clients may query
            │  re-read on the next query (dev mode)
            ▼
  Cube                            2. The semantic layer lives here
            ▲                        Turns "MEASURE(net_amount) by region" into Trino SQL,
            │                        adding the joins and the measure formula
            │  Postgres protocol :15432 ("Cube" connection, registered by bootstrap.sh)
            │
  Superset                        3. Asks Cube for measures by name; holds no formulas
            ▲                        SELECT region, MEASURE(net_amount)
            │                        FROM bank_transactions GROUP BY region
  Business user (chart, SQL Lab)

  Cube ──► Trino ──► Warehouse (mart.*)   4. Cube sends the generated SQL to Trino
```

Superset never sees the formula or the joins; it only asks Cube for a measure
by name. Any other client (another BI tool, a notebook, an application) asking
for `net_amount` gets the same SQL and the same number. Model changes are live
(no restart in dev mode); there is no import step.

### The model

| File | Contents |
|---|---|
| `cubes/transactions.yml` | Fact cube on `warehouse.mart.fact_transaction`: measures (`net_amount`, `transaction_count`, `net_fees`, `avg_txn_amount`, `reversal_rate`, `digital_share`, `active_customers`) and N:1 joins to the dimensions |
| `cubes/dates.yml`, `customers.yml`, `branches.yml`, `products.yml` | Dimension cubes, one per `dim_*` table |
| `views/bank_transactions.yml` | The view Superset uses: transaction measures + date, customer, branch and product dimensions in one flat table |

- **Joins are declared once** in the cube (`relationship: many_to_one`). Cube writes the
  `JOIN`s itself, following each view's `join_path`.
- **Measures can build on measures:** `avg_txn_amount` is `{net_amount} / NULLIF({non_reversed_count}, 0)`.
  Helper measures such as `non_reversed_count` are `public: false`.
- **Cubes are `public: false`**: clients should only use views. (In dev mode Cube still lists
  them; see production notes.)

### Connection from Superset

`superset/bootstrap.sh` registers a database connection named **Cube** on every
Superset start (creates it, or updates its URI). The URI comes from `CUBE_URI`
in the `superset` service in `docker-compose.yml`:

```
postgresql://cube:<CUBE_SQL_PASSWORD>@cube:15432/cube
```

| Part | Value |
|---|---|
| Driver | `postgresql://`: Cube's SQL API speaks the Postgres protocol |
| User | `cube` (`CUBEJS_SQL_USER` in the `cube` service) |
| Password | `CUBE_SQL_PASSWORD` from `.env` |
| Host | `cube` inside Docker; `localhost` from your machine (DBeaver, psql, a local Superset) |
| Port | `15432` (`CUBEJS_PG_SQL_PORT`) |
| Database | `cube` (any name works) |

To connect another Superset by hand: **Settings → Database Connections → + Database
→ PostgreSQL**, and paste the URI into **SQLAlchemy URI**.

### Use it in Superset

**SQL Lab:** choose database **Cube**, schema **public**. Measures are queried with
`MEASURE()`; dimensions are plain columns:

```sql
SELECT region, MEASURE(net_amount) AS net_amount, MEASURE(digital_share) AS digital_share
FROM bank_transactions
GROUP BY region
ORDER BY 2 DESC
```

**Charts:** **Datasets → + Dataset → Cube → public → bank_transactions**. In a chart,
add metrics as **Custom SQL** with `MEASURE(<measure name>)`, e.g. `MEASURE(net_amount)`.
Dimensions, filters and time grains (`full_date` by month, quarter, ...) work as usual;
Cube translates Superset's `DATE_TRUNC`, `WHERE` and `GROUP BY`.

**New views:** add a file to `cube/model/views/` and the view is listed under
**+ Dataset → Cube → public** right away (no restart, no sync).

**Saved metrics:** a dataset created on the Cube connection gets one saved metric per
Cube measure of its view, e.g. `net_amount` = `MEASURE(net_amount)`, with the title and
description from the Cube model (`superset/cube_connection.py`). For a dataset created
before, or after adding measures to the view, click **Sync columns from source**.

### Change the model

1. Edit or add files in `cube/model/cubes/` or `cube/model/views/`.
2. Check the change in the Playground (http://localhost:4000), then refresh Superset.
   In dev mode (`CUBEJS_DEV_MODE=true`) Cube re-reads the model on the next query, so
   no restart and no import step. With dev mode off (production), restart Cube.

To expose a new measure or dimension to Superset, add it to the cube **and** to the
view's `includes` list.

---

## Superset 7 semantic layers (semantic views)

Superset 7.0 adds semantic layers as a datasource type, next to datasets
(feature flag `SEMANTIC_LAYERS`, set in `superset/superset_config.py`). A semantic
layer exposes **semantic views**: fixed metrics and dimensions that charts pick from,
no custom SQL.

**Put a YAML file in `semantic_views/` and it appears in Superset as a semantic view.**
That is the whole flow:

```
semantic_views/*.yaml ──sync.py─────────► PUT  /api/v1/semantic_layer/<Trino>   (YAML stored in Superset)
                                            POST /api/v1/semantic_view/            (one view per file)
```

The `sync` service runs `sync/sync.py`. Every 5 seconds,
when a file changed, it:

1. Stores all the YAML in the semantic layer **Trino**.
2. Creates a semantic view for each new file.
3. Deletes the semantic view of each removed file.

Editing a file changes the view in place (same id), so existing charts keep working.
The views appear in **Datasets** with **Trino** as their connection.

Superset ships no semantic layer type, so `superset/semantic_layer.py` adds one,
`native`: for each chart it turns the picked metrics, dimensions and filters into one
`SELECT` and runs it on the Superset connection named in the file (`database:`,
default `Trino`). `superset_config.py` loads it at startup (`FLASK_APP_MUTATOR`).
Without this file Superset still starts, but every semantic view fails to load.

### Add a view

Copy `semantic_views/branch_performance.yaml` (table + joins) or
`semantic_views/customer_segments.yaml` (SQL source), change `name` and the fields,
and save. Check the log:

```bash
docker compose logs -f sync
```

```
created semantic view(s): my_new_view
synced 4 semantic view(s): branch_performance, customer_segments, reversal_risk, my_new_view
```

Dimension `type` is one of `string`, `number`, `integer`, `boolean`, `date`, `time`;
`date` / `time` dimensions get Day / Week / Month / Quarter / Year grains. Metric `type`
is `number` (default) or `integer`. Use `1.0E0`, not `1.0`, in ratios: Trino treats
`1.0` as a decimal with one digit, so `AVG(... 1.0 ...)` rounds 1.95% to 0.0.

---

## Pros and cons

### Approach 1: Native semantic layer

**Pros**
- **Fewer moving parts.** Superset and Trino only; nothing extra to run, secure or monitor.
- **Full Superset feature set.** Any Trino SQL in metrics and virtual datasets (window
  functions, CTEs, `approx_percentile`, ...), SQL Lab, drill-down, cross-filters.
- **Metrics are first-class in Superset.** Business users pick `net_amount` from a list
  with its label, description and number format; no SQL needed in charts.
- **Easy to adopt.** A dataset can be built in the UI, exported and committed.

**Cons**
- **Superset only.** The definitions cannot be reused by Power BI, Excel, Python
  notebooks, applications or AI agents; each would redefine the same numbers.
- **No join graph.** Joins are hand-written in each virtual dataset's SQL, and the
  author must avoid fan-out (double counting) every time.
- **Repetition across datasets.** The same rule (e.g. "exclude reversed transactions")
  is copied into every dataset that needs it (`transactions`, `customers`,
  `branch_monthly`, ...). Changing it means editing every copy.
- **Metrics cannot reference other metrics**; each is a standalone SQL expression.
- **No acceleration layer.** Only Superset's result cache; heavy queries always hit Trino.
- **No deletes.** Superset's import never deletes, so a removed file leaves its dataset in Superset.

### Approach 2: External semantic layer (Cube)

**Pros**
- **Define once, use everywhere.** The same measures are served over SQL (Postgres
  protocol), REST and GraphQL to Superset, other BI tools, notebooks and applications.
- **Real data model.** Relationships are declared once; Cube generates the joins for
  each query, and views compose cubes without hand-written SQL.
- **Composable measures.** Ratios and averages are built from other measures
  (`avg_txn_amount = net_amount / non_reversed_count`), so a rule lives in one place.
- **Changes are live.** Edit the model and every client sees the new
  definition; no import into Superset.
- **Performance and security features** available when needed: pre-aggregations
  (stored in Cube Store) and row-level access rules in the model that apply to every
  client, not just Superset. (Not configured in this POC.)

**Cons**
- **Another service to run.** Production needs dev mode off, Cube Store, real
  authentication, monitoring and high availability. It also adds a hop between
  Superset and Trino.
- **Shallower Superset integration.** Superset sees Cube views as plain tables: measure
  titles, descriptions and formats from Cube do not appear in Superset, and chart
  authors write `MEASURE(...)` as Custom SQL (or someone maintains Superset datasets on
  top of the views).
- **Restricted SQL.** Only queries Cube can map to its model are accepted. Free-form SQL
  on Cube (e.g. window functions or Superset virtual datasets over the views) may be
  rejected; such logic belongs in the Cube model.
- **Datasets built on Cube views in the Superset UI are not in Git.**
- **New skill set.** The team has to learn Cube's modeling language and debug
  through the SQL Cube generates (visible in the Playground).

### When to choose which

- **Native** fits when Superset is the only consumer and the team wants the
  smallest setup.
- **Cube** fits when several tools or applications must show the same numbers, when
  the model has many joined tables, or when pre-aggregation or central row-level
  security is needed, and the team can operate one more service.

---

## Production notes

**Both approaches**
- Pin `SUPERSET_VERSION` / `TRINO_VERSION` (and `CUBE_VERSION`, default `v1.8.6`) to
  what the bank runs.

**Native**
- The sync scripts log in with a Superset database (AUTH_DB) user; use a dedicated
  service account. OAuth-only logins can't be used by the scripts.

**Cube**
- **Turn off dev mode** (`CUBEJS_DEV_MODE=false`). Dev mode disables authentication,
  enables the Playground, and lists `public: false` cubes. With it off, only views are
  exposed through the SQL API.
- **Run Cube Store** (`cubejs/cubestore`) and set `CUBEJS_CUBESTORE_HOST` /
  `CUBEJS_CUBESTORE_PORT`. Without dev mode, queries fail if no Cube Store is configured.
- Use a strong `CUBE_API_SECRET` and `CUBE_SQL_PASSWORD`, and give Cube a dedicated
  Trino user (`CUBEJS_DB_USER`) with read-only access.
