# Semantic Layer POC — References & Evidence

Research date: **25 October 2026**. Every reference ID (R#) matches the footnotes in `Semantic_Layer_Executive_Presentation.pptx`.

## How the URLs were checked

- **GitHub links** point to the exact tag inspected (Superset `6.0.0` and `7.0.0rc2`, Cube `v1.8.6`) or to `main`. The files were read from shallow, tag-pinned clones of each repository during this review, and the links resolved (HTTP 200) when checked from the project machine.
- **Documentation, pricing and blog links** were opened and read with a web-fetch tool during this review. Pricing pages change often, so re-check them before using any figure in a budget.
- **Repository evidence** is cited by file path relative to the repository root (see the second table).

## External references

| ID | Claim / topic | Source | Version / date | URL | What the source supports |
|---|---|---|---|---|---|
| R1 | Superset 6.0.0 dataset import endpoint (POST /api/v1/dataset/import/, multipart formData, overwrite, passwords) | apache/superset @ tag 6.0.0 — superset/datasets/api.py (import_) | 6.0.0 | <https://github.com/apache/superset/blob/6.0.0/superset/datasets/api.py> | Exact endpoint path and request fields used by sync.py |
| R2 | Externally managed datasets: Save disabled in the dataset editor (frontend) | apache/superset @ 6.0.0 — DatasourceModal.tsx | 6.0.0 | <https://github.com/apache/superset/blob/6.0.0/superset-frontend/src/components/Datasource/DatasourceModal.tsx> | UI disables Save with tooltip "This dataset is managed externally, and can't be edited in Superset" |
| R3 | Superset 7 semantic layer / semantic view REST API | apache/superset @ 7.0.0rc2 — superset/semantic_layers/api.py | 7.0.0rc2 (tag commit 16 Oct 2026) | <https://github.com/apache/superset/blob/7.0.0rc2/superset/semantic_layers/api.py> | resource names semantic_layer / semantic_view; POST /, PUT /<uuid>, POST /<uuid>/views, GET /types |
| R4 | SEMANTIC_LAYERS and ENABLE_EXTENSIONS flags default False, lifecycle 'development' | apache/superset @ 7.0.0rc2 — superset/config.py | 7.0.0rc2 | <https://github.com/apache/superset/blob/7.0.0rc2/superset/config.py> | Feature maturity of semantic layers and extensions |
| R5 | Semantic layer permissions; server-side refusal of edits to externally managed entities | apache/superset @ 7.0.0rc2 — UPDATING.md | 7.0.0rc2 | <https://github.com/apache/superset/blob/7.0.0rc2/UPDATING.md> | SemanticLayer create/edit admin-only, SemanticView writes Alpha-tier; PUT on is_managed_externally entities returns 403 (new in 7.0) |
| R6 | Semantic view PUT schema (description, cache_timeout only) | apache/superset @ 7.0.0rc2 — superset/semantic_layers/schemas.py | 7.0.0rc2 | <https://github.com/apache/superset/blob/7.0.0rc2/superset/semantic_layers/schemas.py> | Semantic view structure cannot be edited through PUT /api/v1/semantic_view/<pk> |
| R7 | Read-only structure message for semantic views | apache/superset @ 7.0.0rc2 — SemanticViewEditModal.tsx | 7.0.0rc2 | <https://github.com/apache/superset/blob/7.0.0rc2/superset-frontend/src/features/semanticViews/SemanticViewEditModal.tsx> | "Structure is managed by the upstream semantic layer and is read-only." |
| R8 | Superset release tags (no 7.0.0 final tag; 6.1.0 latest final) | apache/superset — tags | checked 25 Oct 2026 | <https://github.com/apache/superset/tags> | 7.0.0 exists only as rc1/rc2 at research date |
| R9 | Feature-flag lifecycle definitions (Development = experimental, may be incomplete or unstable) | Apache Superset docs — Feature Flags | 'Next' docs, accessed 25 Oct 2026 | <https://superset.apache.org/admin-docs/configuration/feature-flags> | SEMANTIC_LAYERS and ENABLE_EXTENSIONS listed under Development |
| R10 | ASF policy on release candidates | ASF Release Policy (apache/www-site source) | accessed 25 Oct 2026 | <https://apache.googlesource.com/www-site/+show/HEAD/content/legal/release-policy.md> | Release candidates are for developers/testers; users should wait for a formally approved release |
| R11 | Superset semantic layers (SIP-182), extensions, providers, Ossie direction | Preset blog — Semantic Layers in Apache Superset: SIP-182 and Apache Ossie | 6 Aug 2026 | <https://preset.io/blog/semantic-layers-in-superset/> | Targeted at 7.0; providers are extensions; 'design is still moving'; Ossie provider proposed, not shipped |
| R12 | Superset CLI import/export of datasources | Apache Superset docs 6.0.0 — Importing and Exporting Datasources | 6.0.0 | <https://superset.apache.org/user-docs/6.0.0/configuration/importing-exporting-datasources> | YAML/ZIP datasource bundles with metrics nested under tables |
| R13 | Cube Core architecture (API instances, Refresh Worker, Cube Store; caches) | Cube docs — Cube Core architecture | accessed 25 Oct 2026 | <https://docs.cube.dev/cube-core/architecture> | Component model; in-memory cache lazy; pre-aggregations in Cube Store |
| R14 | Cube Core production requirements | Cube docs — Running in production | accessed 25 Oct 2026 | <https://docs.cube.dev/cube-core/running-in-production> | Dev mode is an auth bypass; Cube Store cluster; >=4 CPU / up to 8 GB per node; no OSS replication; HA = independent clusters; /readyz |
| R15 | Cube SQL API (Postgres protocol), CUBEJS_PG_SQL_PORT, limitations | Cube docs — SQL API | accessed 25 Oct 2026 | <https://docs.cube.dev/reference/core-data-apis/sql-api> | Postgres-compatible clients; disabled by default in Core; regular/post-processing/pushdown support levels |
| R16 | MEASURE() and query types in the SQL API | Cube docs — SQL API query format | accessed 25 Oct 2026 | <https://docs.cube.dev/reference/core-data-apis/sql-api/query-format> | MEASURE works with measures of any type; aggregation rules |
| R17 | Power BI with Cube (DAX API vs SQL API) | Cube docs — Power BI | accessed 25 Oct 2026 | <https://docs.cube.dev/docs/integrations/power-bi> | DAX API is Cube Cloud; SQL API is 'the only option when using Cube Core' with 'much more limited functionality' |
| R18 | Superset with Cube | Cube docs — Superset | accessed 25 Oct 2026 | <https://docs.cube.dev/admin/connect-to-data/visualization-tools/superset> | Superset connects to Cube as a Postgres database via the SQL API |
| R19 | Cube Cloud scaling guidance (reference only) | Cube docs — Scalability | accessed 25 Oct 2026 | <https://docs.cube.dev/admin/deployment/scalability> | Rough estimate: 1 API instance per 5–10 requests/second (Cube Cloud) |
| R20 | Cube Cloud pricing (reference for the managed alternative) | Cube — Pricing | accessed 25 Oct 2026 | <https://cube.dev/pricing> | Starter $40/developer/month; Premium $80/developer/month; Enterprise custom; dedicated compute billed hourly |
| R21 | Cube Core licence | cube-js/cube — LICENSE | v1.8.6 tree | <https://github.com/cube-js/cube/blob/v1.8.6/LICENSE> | Apache License 2.0 by default; some packages MIT |
| R22 | Apache Ossie: what it is, repository contents, converters | apache/ossie — README | main, 25 Oct 2026 | <https://github.com/apache/ossie> | Specification + schema + validation; converters (dbt, GoodData, Polaris, Salesforce) in ossie-converters |
| R23 | Ossie spec version and draft status | apache/ossie — core-spec/spec.md | 0.2.0.dev0 (DRAFT) | <https://github.com/apache/ossie/blob/main/core-spec/spec.md> | Schema may change before 0.2.0 |
| R24 | Ossie roadmap: query language and reference engine are future efforts | apache/ossie — ROADMAP.md | main, 25 Oct 2026 | <https://github.com/apache/ossie/blob/main/ROADMAP.md> | No execution engine today |
| R25 | Ossie incubation status | apache/ossie — DISCLAIMER | main | <https://github.com/apache/ossie/blob/main/DISCLAIMER> | Undergoing incubation; not yet fully endorsed by the ASF |
| R26 | Ossie support in Superset — community question | apache/superset Discussion #42823 'Apache Ossie Support' | opened 6 Aug 2026, closed | <https://github.com/apache/superset/discussions/42823> | A request/discussion only — no implementation |
| R27 | Ossie accepted into Apache Incubator (June 2026); formerly OSI | Dremio blog — Apache Ossie joins the Apache Incubator | 2026 (secondary source) | <https://www.dremio.com/blog/apache-ossie-the-open-semantic-interchange-joins-the-apache-incubator> | History, spec + tooling, 'not a product you install' |
| R28 | MetricFlow concepts, metric types, supported platforms, Ossie input | dbt docs — About MetricFlow | dbt v1.12+ syntax, accessed 25 Oct 2026 | <https://docs.getdbt.com/docs/build/about-metricflow> | Semantic graph; Apache 2.0; listed platforms: Snowflake, BigQuery, Databricks, Postgres (v1), Redshift |
| R29 | dbt Semantic Layer architecture: open vs proprietary components | dbt docs — Semantic Layer architecture | accessed 25 Oct 2026 | <https://docs.getdbt.com/docs/use-dbt-semantic-layer/sl-architecture> | MetricFlow Apache 2.0; service layer and GraphQL/JDBC APIs proprietary (Starter, Enterprise, Enterprise+) |
| R30 | dbt Semantic Layer integrations | dbt docs — Available integrations | accessed 25 Oct 2026 | <https://docs.getdbt.com/docs/platform-integrations/avail-sl-integrations> | 12 integrations incl. Power BI, Tableau, Excel; Superset/Preset not listed |
| R31 | dbt platform pricing | dbt Labs — Pricing | accessed 25 Oct 2026 | <https://www.getdbt.com/pricing> | Starter $100/user/month, 5 developer seats, 5,000 queried metrics/month; Enterprise custom, 20,000 queried metrics/month |
| R32 | How queried metrics are counted | dbt docs — How pricing works | last updated 8 Oct 2026 | <https://docs.getdbt.com/docs/platform/billing/how-pricing-works> | Each metric in a successful request counts; failed and metadata requests do not |
| R33 | MetricFlow licence and source | dbt-labs/metricflow — repository | main, 13 Oct 2026 | <https://github.com/dbt-labs/metricflow> | Apache 2.0; SqlEngine enum includes Trino; Trino SQL renderer present in source |
| R34 | MetricFlow relicensed to Apache 2.0 (Coalesce 2025) | dbt Labs blog — Open source MetricFlow | Coalesce 2025; page edited 18 Dec 2025 | <https://www.getdbt.com/blog/open-source-metricflow-governed-metrics> | Open source includes metric definition and multi-dialect SQL calculation |
| R35 | Apache Superset licence | apache/superset — LICENSE.txt | 7.0.0rc2 | <https://github.com/apache/superset/blob/7.0.0rc2/LICENSE.txt> | Apache License 2.0 |

## Repository evidence

| Evidence | Path | What it shows |
|---|---|---|
| v6 dataset-import sync | `sync/sync.py` | Render → validate → `POST /api/v1/database/import/` then `POST /api/v1/dataset/import/` (overwrite=true) → prune → smoke test via `/api/v1/chart/data` |
| v6 definitions | `semantic/metadata.yaml`, `semantic/databases/Trino.yaml`, `semantic/datasets/Trino/*.yaml` | 4 datasets, 22 metrics, `is_managed_externally: true` |
| v6 restore point | `.restore/pre-superset-7/RESTORE.md`, `superset-metadata.dump` | Superset 6.0.0 metadata from 18 Oct 2026: 5 datasets (4 Git-managed + 1 UI-built on Cube), 23 metric rows (22 from YAML + 1 auto `count`), 0 charts, 0 dashboards, 1 user (Admin role) |
| v6 code baseline | git tag `pre-superset-7` (commit `46b8297`) | `SUPERSET_VERSION` default `6.0.0`; no `superset/extensions`, no `semantic_views/` |
| v7 semantic-view sync | `sync/semantic_views.py` | `GET /api/v1/semantic_layer/types`, `POST /api/v1/semantic_layer/`, `PUT /api/v1/semantic_layer/<uuid>`, `POST /api/v1/semantic_layer/<uuid>/views`, `POST/PUT/DELETE /api/v1/semantic_view/`, `GET /api/v1/datasource/` |
| v7 definitions | `semantic_views/branch_performance.yaml`, `semantic_views/customer_segments.yaml` | Native provider YAML schema (source table/sql + joins, dimensions, metrics) |
| v7 config | `superset/superset_config.py`, `superset/Dockerfile` | `FEATURE_FLAGS = {SEMANTIC_LAYERS: True, ENABLE_EXTENSIONS: True}`, `LOCAL_EXTENSIONS`, base image `apache/superset:7.0.0rc2` |
| Custom providers | `superset/extensions/native-semantic-layer/…/__init__.py`, `superset/extensions/cube-semantic-layer/…/__init__.py` | Bank-written Superset 7 semantic-layer providers (~14 KB each) |
| Cube model | `cube/model/cubes/*.yml`, `cube/model/views/*.yml` | 5 cubes, 2 views, many_to_one joins, composable measures |
| Stack | `docker-compose.yml` | Trino 476, Postgres 16 warehouse, Superset, Cube `v1.8.6` (dev mode on, SQL API :15432), sync services |
| Warehouse | `warehouse/init/01_star_schema.sql`, `trino/catalog/warehouse.properties` | Synthetic star schema, fixed seed, 20,000 transactions |
| CI | `.gitlab-ci.yml` | validate → staging (MR) → prod (merge) for `semantic/` only |
| v7 UI evidence | `presentation/2.png`, `3.1.png`, `3.2.png`, `4.png`, `5.png`, `11.png`, `12.png`, `13.png` | Semantic views listed; read-only structure; saved metrics only; custom SQL metrics disabled; Net Fees = 97,755.00 at 10/18/2026 12:18 PM |
| Cube cross-tool evidence | `presentation/output/professional_demo/diagrams/comparison_powerbi_superset.png`, `QUALITY_REPORT.md`, `EDITING_TIMELINE.md` | Power BI and Superset both show 43,153,022.01 (Ismailia Main, SUM(amount)) on the Cube view |
| Independent re-computation | (this review) | Seed SQL loaded into PostgreSQL 16: Ismailia Main SUM(amount) = 43,153,022.01; net_fees = 97,755.00; net_amount = 317,418,359.40; SUM(amount) = 323,757,585.92; 390 reversed transactions |

## Claims the evidence does not support

- Snowflake or any other platform's exact Ossie integration: not verified for this deck.
- Ossie support in Apache Superset: not implemented (discussion #42823 and Preset's proposal only).
- MetricFlow on Trino: renderer exists in source, but dbt docs do not list Trino. Requires validation.
- Any self-hosted infrastructure cost in currency: no measurement exists; see `Semantic_Layer_TCO_Model.md`.
