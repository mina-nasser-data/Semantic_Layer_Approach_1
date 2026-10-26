# Semantic Layer POC — Verified Findings

Review date: 25 October 2026. Scope: the `Semantic_Layer_POC` repository (working tree on branch `superset-7-upgrade`, tag `pre-superset-7`, and the `.restore/pre-superset-7/` restore point). Reference IDs (R#) are listed in `Semantic_Layer_References.md`.

Status labels: **Verified** (seen in code plus runtime evidence), **Reproduced** (independently re-computed in this review), **Code review** (read from source, not run), **Documented** (official docs or source only), **Not demonstrated**, **Requires validation**.

---

## 1. Repository map

| Path | Role | Version |
|---|---|---|
| `docker-compose.yml` | One stack: Trino, sample warehouse (Postgres 16), Superset + metadata DB, Cube, `semantic-sync`, `semantic-views-sync` | Trino 476, Cube `v1.8.6`, Superset `7.0.0rc2` (was `6.0.0`) |
| `semantic/` + `sync/sync.py` + `.gitlab-ci.yml` | Approach 1a: datasets and metrics as YAML, imported through the dataset import API | Superset 6.0.0 (still runs on 7.0.0rc2) |
| `semantic_views/` + `sync/semantic_views.py` + `superset/extensions/` | Approach 1b: Superset 7 semantic layers with two custom providers | Superset 7.0.0rc2 |
| `cube/model/` | Approach 2: Cube Core model (5 cubes, 2 views) | Cube Core v1.8.6 |
| `warehouse/init/01_star_schema.sql` | Synthetic banking star schema, fixed seed (20,000 transactions, 200 customers, 8 branches, 8 products, transactions 2025-01-01 → 2026-09-30) | Postgres 16 |
| `.restore/pre-superset-7/` | Restore point before the 6 → 7 upgrade: `RESTORE.md`, `.env` (secrets, not opened), `superset-metadata.dump` | Created 18 Oct 2026 |
| `presentation/` | Screenshots and an edited demo video with QA report | — |

Git history: 7 commits (16–17 Oct 2026) on `main` up to `46b8297` (= tag `pre-superset-7`). All Superset 7 work is **uncommitted** in the working tree (modified: `.env.example`, `README.md`, `docker-compose.yml`, `superset/Dockerfile`, `superset/superset_config.py`, `sync/Dockerfile`; untracked: `semantic_views/`, `superset/extensions/`, `sync/semantic_views.py`, `sync/list_semantic.py`, `test_new_api.py`, `cube/model/views/branch_activity.yml`, `presentation/`).

Note on "Version A in `.restore`": `.restore/` holds the **restore point** (metadata backup + env + instructions), not source code. The v6 code is the git tag `pre-superset-7`. Its sync code (`sync/sync.py`) is unchanged in the current tree.

---

## 2. Superset v6 — dataset import approach

| Finding | Status | Evidence |
|---|---|---|
| Endpoint is `POST /api/v1/dataset/import/` (singular `dataset`), multipart `formData` ZIP with `overwrite=true`; databases imported first through `POST /api/v1/database/import/` | Verified | `sync/sync.py` `import_bundle()`; [R1] |
| 4 Git-managed datasets (`fact_transaction` physical; `transactions`, `customers`, `branch_monthly` virtual) and 22 metrics were stored in Superset 6.0.0 | Verified | metadata dump: `tables.is_managed_externally = t`, `sql_metrics` |
| One extra UI-built dataset `bank_transactions` on the Cube connection (not Git-managed) with an auto `count` metric | Verified | metadata dump |
| No saved charts or dashboards existed at backup time | Verified | metadata dump: `slices` and `dashboards` empty |
| Only one user, in the Admin role | Verified | metadata dump: `ab_user_role` |
| Add / delete a YAML file → dataset appears / disappears within seconds | Verified | demo video, `EDITING_TIMELINE.md` segments 10–11 |
| Validation (snake_case, descriptions, unique uuids) and smoke test (every metric run through `/api/v1/chart/data`) | Code review | `sync/sync.py` |
| CI: validate on MR → deploy to staging (MR) → prod (merge), `semantic/` only | Code review (pipeline runs not evidenced) | `.gitlab-ci.yml` |
| Rule duplication: "exclude reversed transactions" is written separately in `transactions`, `customers` and `branch_monthly` | Verified | `semantic/datasets/Trino/*.yaml` |
| Superset 6.0.0 UI disables **Save** for `is_managed_externally` datasets ("This dataset is managed externally, and can't be edited in Superset") | Documented (source) | [R2] |
| Superset 6.0.0 API does **not** refuse edits to externally managed datasets. The server-side 403 was added in 7.0 | Documented (source) | [R5] "Updates of externally managed entities are refused server-side" |
| Chart authors can still create ad-hoc Simple / Custom SQL metrics unless the dataset's `extra.disallow_adhoc_metrics` is set. It is not set in the POC YAML | Code review | `semantic/datasets/Trino/*.yaml`; Superset frontend `AdhocMetricEditPopover` |
| README says "Superset does not block edits"; that understates the UI behaviour (Save disabled) but is right for the API on 6.0 | Clarification | [R2][R5] |

## 3. Superset v7.0.0rc2 — semantic views

| Finding | Status | Evidence |
|---|---|---|
| Feature flags `SEMANTIC_LAYERS` and `ENABLE_EXTENSIONS` enabled; both default `False` and are marked `@lifecycle: development` upstream | Verified (config) / Documented | `superset/superset_config.py`; [R4][R9] |
| 7.0.0 exists only as `7.0.0rc1` / `7.0.0rc2` tags; latest final release is 6.1.0. ASF policy: release candidates are for testing, not general use | Documented | [R8][R10] |
| Superset 7.0.0rc2 ships **no** semantic-layer provider (only docstring examples). The POC wrote two: `native-semantic-layer` and `cube-semantic-layer` (~14 KB Python each) | Verified (source) | `superset/extensions/`; superset-core `decorators.py` |
| API used: `GET /api/v1/semantic_layer/types`, `POST /api/v1/semantic_layer/`, `PUT /api/v1/semantic_layer/<uuid>` (upload YAML definitions as `configuration.views`), `POST /api/v1/semantic_layer/<uuid>/views`, `POST /api/v1/semantic_view/` (bulk create), `PUT`/`DELETE /api/v1/semantic_view/<id>`, `GET /api/v1/datasource/` | Verified (code) / Documented | `sync/semantic_views.py`; [R3] |
| 4 semantic views registered: `branch_performance`, `customer_segments` (Trino native), `branch_activity`, `bank_transactions` (Cube) | Verified | `presentation/2.png` |
| Edit dialog: "Structure is managed by the upstream semantic layer and is read-only." | Verified | `presentation/3.1.png`, `3.2.png`, `11.png`; [R7] |
| Explore: "Custom SQL ad-hoc metrics are not enabled for this dataset"; only saved metrics selectable | Verified | `presentation/4.png`, `12.png` |
| Query result: Net Fees on `branch_performance` = 97,755.00 (0.17 s, queried 10/18/2026 12:18 PM) | Verified + Reproduced | `presentation/5.png`; seed re-computation |
| `PUT /api/v1/semantic_view/<pk>` accepts only `description` and `cache_timeout`: the structure cannot be changed through that endpoint | Documented (source) | [R6] |
| Semantic layer create/edit/delete is admin-only by default; semantic-view writes are Alpha-tier | Documented | [R5] |
| Users with access to the Trino database connection can still query raw tables in SQL Lab; governance remains role-dependent | Code / config review | — |
| Non-admin roles were not tested | Not demonstrated | metadata dump (only Admin) |
| Native provider emits **every** declared join on every query (no join pruning, no fan-out guard); no metric-on-metric composition; series limits, custom SQL filters and custom SQL in ORDER BY are not supported | Code review | `native_semantic_layer/__init__.py` (`_from`, `_select`, `_predicate`) |
| Query through the **Cube** semantic layer (REST `/load`) returning data in a chart | Not demonstrated | views listed only; sync smoke test runs native views only |
| `fee_revenue` and `customer_value` native views appear in `presentation/11.png` but their YAML is not in the repository | Not in repo | `presentation/11.png`, `13.png` |

## 4. Cube Core

| Finding | Status | Evidence |
|---|---|---|
| Cube Core v1.8.6 connects to Trino (`CUBEJS_DB_TYPE=trino`, catalog `warehouse`) | Verified | `docker-compose.yml`; demo video |
| Model: 5 cubes (`transactions` fact + 4 dimensions, all `public: false`), 2 views (`bank_transactions`, `branch_activity`); 4 many_to_one joins; composable measures (`avg_txn_amount = net_amount / non_reversed_count`) | Code review | `cube/model/` |
| Superset connection "Cube" registered via `superset set-database-uri` on every start (`postgresql://cube:<redacted>@cube:15432/cube`) | Verified | `superset/bootstrap.sh`; metadata dump `dbs` |
| Superset and Power BI Desktop both queried the Cube view over the SQL API; Ismailia Main SUM(amount) = 43,153,022.01 in both | Verified + Reproduced | demo still, `QUALITY_REPORT.md`; seed re-computation |
| Both tools used a raw **SUM(amount)**, not the governed `net_amount` measure (42,507,457.41 for Ismailia Main) | Verified (limitation) | `QUALITY_REPORT.md` "Known limitations" |
| With Cube Core, Power BI can only use the SQL API ("much more limited functionality" than the Cube Cloud DAX API) | Documented | [R17] |
| Dev mode ON (authentication bypass per Cube docs); no Cube Store, no pre-aggregations, no row-level security; Cube model not in CI | Verified (config) | `docker-compose.yml`, README; [R14] |
| Cube's generated SQL text was not captured | Not demonstrated | — |

## 5. Approaches not implemented

| Topic | Finding | Status |
|---|---|---|
| Apache Ossie | Accepted into the Apache Incubator, June 2026 (formerly OSI). Core spec `0.2.0.dev0`, marked draft. Specification + schema + validation + converters (dbt, GoodData, Polaris, Salesforce). No execution engine: query language and reference engine are listed under Future Efforts | Documented [R22–R25][R27] |
| Ossie in Superset | GitHub discussion #42823 (closed, no implementation); Preset proposes a provider extension | Proposed only [R26][R11] |
| Snowflake / others with Ossie | No exact integration confirmed | Not verified |
| MetricFlow | Apache 2.0. Defines metrics and compiles SQL; CLI; reads Ossie documents from dbt v1.12. APIs (JDBC/ADBC/GraphQL), service layer and integrations are proprietary dbt platform features (Starter, Enterprise, Enterprise+) | Documented [R28][R29][R34] |
| MetricFlow on Trino | Trino renderer exists in source; dbt docs list only Snowflake, BigQuery, Databricks, Postgres (v1), Redshift | Requires validation [R28][R33] |
| dbt prerequisite | No dbt project exists in this repository | Verified |

## 6. Independent re-computation (performed in this review)

`warehouse/init/01_star_schema.sql` was loaded into a local PostgreSQL 16 instance (same major version as the POC warehouse, fixed seed `setseed(0.42)`). SQL was run directly on Postgres, not through Superset, Trino or Cube.

| Quantity | Result | Matches |
|---|---|---|
| SUM(amount) for Ismailia Main | 43,153,022.01 | Power BI + Superset on Cube (demo) |
| net_amount for Ismailia Main | 42,507,457.41 | (governed measure; not shown in demo) |
| net_fees, all data | 97,755.00 | Superset 7 semantic view (`5.png`) |
| net_fees by region | Canal 37,205.00 · Greater Cairo 36,100.00 · Delta 12,715.00 · Alexandria 11,735.00 | sums to 97,755.00 |
| SUM(amount) / net_amount, all data | 323,757,585.92 / 317,418,359.40 | — |
| Reversed transactions | 390 of 20,000 (1.95 %) | — |

## 7. Security and hygiene observations

- `test_new_api.py` contains a hard-coded Superset admin password (value not reproduced here). Remove it, or read it from the environment, before the repository is shared.
- `.env` and `.restore/pre-superset-7/.env` hold secrets; both are kept out of Git (`.gitignore` covers `.env`; `.restore/` is excluded via `.git/info/exclude`). Their contents were not opened in this review.
- The metadata dump contains the Cube connection URI and an encrypted password field; treat the dump as sensitive.
- Cube runs in dev mode (authentication bypass); acceptable locally only.
- Demo video: `QUALITY_REPORT.md` notes that folder names and a Git author name are visible in the recording.

## 8. What was not tested (gaps)

Concurrency and load; latency at scale; failover and HA; non-admin roles and permissions; row-level security; real bank data volumes and types; Power BI with a governed Cube measure (`MEASURE(net_amount)`); queries through the v7 Cube provider; Cube pre-aggregations / Cube Store; Ossie and MetricFlow in practice.

## 9. Unresolved questions

1. Must Power BI (or Excel, apps, AI agents) show the same governed KPIs within 12–36 months?
2. What availability target and concurrency must the semantic layer support?
3. When will Superset 7.0 reach a final release, and will the semantic-layer API or extension interface change before then?
4. Who would own and support the two custom Superset providers?
5. Can a managed service (dbt platform, Cube Cloud) be used under the bank's data-residency rules?
6. Is MetricFlow officially supported on Trino (vendor confirmation)?
7. Does Cube Store's object-storage requirement (S3 / GCS / Azure Blob) fit the bank's infrastructure, for example an S3-compatible on-prem store? (Requires validation.)

## 10. Questions management may ask (with short answers)

| Question | Short answer |
|---|---|
| "Did both approaches really work?" | Yes, on synthetic data: native on Superset 6 and 7 (rc), Cube with Superset and Power BI. Headline numbers were re-computed independently. |
| "Which one is better?" | It depends on one requirement: whether tools other than Superset must use governed KPIs. The evidence does not justify a winner without that answer. |
| "Is Superset 7 production-ready?" | Not yet: 7.0.0 is a release candidate, and the semantic-layer flags are marked "development". |
| "Is open source free?" | The licence is. Infrastructure, operations and engineering are not. See the TCO model. |
| "Why not just use Ossie?" | It is a draft format with no engine and no Superset support yet. Watch it; don't build on it. |
| "Why not dbt?" | Possible if the bank adopts dbt. Today there is no dbt project, Trino support is unconfirmed, and serving APIs require a paid plan. |
| "How many Cube servers do we need?" | Unknown until a load test. No sizing claim is made. |
| "Can users still change KPI definitions?" | On v6: through the API and via ad-hoc chart metrics, yes. On v7 semantic views: structure is read-only in the UI; layer config is admin-only. Non-admin roles still need testing. |
| "Did Power BI use the governed definition?" | No. The demo matched on SUM(amount). Testing `MEASURE(net_amount)` in Power BI is a validation step. |
| "What if we choose wrong?" | Keeping definitions in Git YAML limits the switching cost to a conversion. `RESTORE.md` documents how to roll the stack back to Superset 6. |

## 11. Integrity of this review

- No project file was modified. `.restore/` was inspected read-only. SHA-256 before and after: `.env` `16e904c1…d41217`, `RESTORE.md` `afa30155…9df`, `superset-metadata.dump` `eabc059b…cf5cf`.
- The only new files are in `deliverables/semantic_layer_executive_presentation/`.
