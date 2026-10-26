# Semantic Layer — Total Cost of Ownership Model

**Status: this is a cost model, not a measured cost.** The repository contains no workload measurements, cloud or data-centre billing, or staffing data. No currency amount below is an estimate for the bank. The only currency figures are public vendor list prices, recorded with their source and access date so readers can see what they are and are not.

Research date: 25 October 2026. Reference IDs (R#) are listed in `Semantic_Layer_References.md`.

---

## 1. Formulas

```
TCO(horizon) = Licensing + Infrastructure + Warehouse + Engineering
             + Operations + Integration + Migration          (horizon = 12 or 36 months)

Licensing       = Σ (seats × price per seat per month × months) + usage overage
Infrastructure  = Σ (monthly resource cost × months)          — per environment (dev, staging, prod, DR)
Warehouse       = Δ query CPU-hours × internal cost per CPU-hour
                + pre-aggregation / refresh CPU-hours × cost per CPU-hour
                + Δ storage GB × cost per GB-month × months
Engineering     = estimated engineering hours × fully loaded hourly cost   (implementation, one-off)
Operations      = (monitoring + on-call + upgrades + security patching hours per month) × hourly cost × months
Integration     = hours to connect each BI tool / API client × hourly cost
Migration       = (charts / dashboards to rebuild × hours each + data reconciliation hours) × hourly cost
```

*Fully loaded hourly cost* = salary + benefits + overhead, provided by Finance. Do not use a contractor or market rate unless the work will really be outsourced.

---

## 2. Cost categories by option: what to count

The letters A–F match the business cost framework (A licence, B infrastructure, C warehouse, D engineering, E operations, F lock-in / opportunity cost).

| Category | Superset native (v6 import → v7 semantic views) | Cube Core (self-hosted) | MetricFlow + dbt Semantic Layer (managed) | MetricFlow self-hosted | Ossie + engine |
|---|---|---|---|---|---|
| A · Software subscriptions | None. Superset is Apache 2.0 [R35] | None. Apache 2.0 / MIT [R21] | dbt platform seats + queried metrics [R31][R32] | None. Apache 2.0 [R33][R34] | None for the spec; engine-dependent |
| B · Infrastructure | No new service. Same Superset nodes; extension code runs inside Superset | ≥2 Cube API nodes for HA, Refresh Worker, Cube Store router + workers (≥4 CPU, up to 8 GB per node), object storage; HA via 2 independent Cube Store clusters [R14] | Vendor-hosted service; bank network / private connectivity | dbt runner + a bank-built API service with HA | Whatever engine is chosen |
| C · Warehouse compute & storage | Every chart query runs on Trino | Lower for queries served from pre-aggregations, plus refresh jobs; raw queries still hit Trino [R13] | Every metric query compiles to warehouse SQL; exports add tables | Same as managed | Engine-dependent |
| D · Engineering implementation | Low for v6 (built). v7: maintain 2 custom providers (~14 KB Python each) on a prerelease API | Medium: model already started; add Cube Store, auth, CI for `cube/model/`, prod config | High: no dbt project exists in this repository; model + semantic YAML from scratch | Highest: dbt project + serving layer | High: converters + Superset provider + engine |
| E · Operations (monitoring, on-call, upgrades) | Superset only (already operated) | New tier-1 service: monitoring, `/readyz` checks, upgrades, capacity planning | Vendor operates the service; bank manages contract, tokens, access | Bank operates everything | Engine-dependent |
| Integration development | Each non-Superset tool must re-implement every KPI | One connection per tool (SQL / REST / GraphQL); Power BI on Core uses SQL API only, "much more limited" than Cube Cloud's DAX API [R17] | Native integrations incl. Power BI, Tableau, Excel; Superset not listed [R30] | Custom per tool | Converter per tool |
| Migration | v6 → v7: rewrite YAML to provider schema; rebuild charts on semantic views | Rebuild charts on Cube views; train authors on `MEASURE()` | Re-express metrics in dbt; rebuild charts | Same | Same + converter testing |
| Testing & release management | CI exists for `semantic/`; v7 sync has `--validate-only` | No CI for Cube in repo; must be built | dbt CI | dbt CI | Spec validation tooling exists [R22] |
| F · Lock-in / exit cost | Definitions tied to Superset formats | Tied to Cube modelling language | Serving tied to dbt platform | Low | Lowest in principle |

---

## 3. Public list prices (reference only)

These are **list prices for managed products**, accessed 25 October 2026. They are **not** quotes for the bank and must not be extrapolated to an enterprise agreement.

| Product | Plan | Public price | Notes | Source |
|---|---|---|---|---|
| dbt platform | Starter | $100 per user / month | 5 developer seats; 15,000 successful models built / month; 5,000 queried metrics / month; Semantic Layer included | [R31] |
| dbt platform | Enterprise / Enterprise+ | Custom | 20,000 queried metrics / month listed; overage rate for queried metrics not published | [R31] |
| dbt platform | Developer | Free | 1 seat; Semantic Layer service and APIs not available on Developer plans | [R29][R31] |
| Cube Cloud | Starter | $40 per developer / month | Dedicated deployment $0.60 / hour | [R20] |
| Cube Cloud | Premium | $80 per developer / month | Explorer $40 / user / month, Viewer $20 / user / month; dedicated deployment $1.20 / hour | [R20] |
| Cube Cloud | Enterprise | Custom | BYOC, SSO, audit logging | [R20] |

**Queried-metric counting (dbt):** every metric in a successful request counts, and compile-only requests count too. Failed and metadata requests do not count [R32]. Example: a dashboard with 10 metric tiles, opened 200 times a day for 22 working days, could generate roughly 10 × 200 × 22 = 44,000 queried metrics a month, before caching. That is above the Enterprise allowance listed above. Measure real usage before negotiating.

`Pricing requires vendor confirmation` for any bank-wide figure.

---

## 4. Estimation method (how the bank can fill the model)

| Input | How to obtain it | Owner |
|---|---|---|
| Engineering hours | Record actual hours during the validation phase; extrapolate per remaining KPI / dataset | Data squad lead |
| Fully loaded hourly cost | Finance standard rate card | Finance |
| Infrastructure unit costs | Internal VM / Kubernetes price list (CPU, RAM, storage, load balancer) for dev, staging, prod, DR | Platform / Infra |
| Cube node count | Load test at target concurrency; Cube Cloud's rough guide of 1 API instance per 5–10 requests/second [R19] is only a starting point | Data squad + Infra |
| Warehouse CPU per option | Trino query logs during identical test workloads (`query_id`, CPU time) | Data squad |
| Availability target | Business SLA (e.g. dashboards in business hours vs 24/7) | Business owner |
| Number of BI tools / API consumers | BI strategy for the next 36 months | BI lead |
| Vendor prices | Written quotes only | Procurement |

---

## 5. Sensitivity: which variables move cost most

Qualitative judgement based on the cost drivers above, not a calculation. H = high, M = medium, L = low.

| Variable | Native | Cube Core | dbt SL (managed) | Why |
|---|---|---|---|---|
| Concurrent users / query rate | M | H | M | Cube API nodes scale with request rate; native and dbt push load to warehouse and Superset |
| Number of BI tools to serve | H | L | M | Native: each tool re-implements every KPI (tools × metrics) |
| Availability target | L | H | M | Cube HA = more API nodes + second Cube Store cluster [R14] |
| Number of metric developers | L | L | H | dbt priced per seat [R31] |
| Data volume / freshness | M | H | M | Pre-aggregation storage and refresh compute |
| Queried metrics per month | — | — | H | dbt usage metric [R32] |

---

## 6. Worksheet template (fill with measured inputs)

| Category | Native 12 m | Native 36 m | Cube 12 m | Cube 36 m | dbt SL 12 m | dbt SL 36 m | Assumptions / source |
|---|---|---|---|---|---|---|---|
| Software subscriptions | | | | | | | |
| Infrastructure | | | | | | | |
| Warehouse compute & storage | | | | | | | |
| Engineering implementation | | | | | | | |
| Ongoing maintenance | | | | | | | |
| Monitoring & reliability | | | | | | | |
| Integration development | | | | | | | |
| Migration | | | | | | | |
| Testing & release management | | | | | | | |
| **Total** | | | | | | | |

---

## 7. Assumptions and limitations

- The POC ran on a laptop-scale Docker Compose stack with 20,000 synthetic rows. Nothing about runtime, resource use or latency in it carries over to production.
- One anecdotal observation from the demo narration (Cube via Superset: first run about 4 s, cached about 1 s) is a single observation, not a benchmark.
- Open-source licensing does not mean zero TCO: categories B–E dominate for self-hosted options.
- Data-residency or regulatory constraints may rule out managed services regardless of cost. Confirm with Risk and IT Security.
