# Alteryx v1 (archived)

The first iteration of the data preparation was built visually in Alteryx Designer (SparkED learner licence, ended 24 Oct 2026):

- `alteryx/00_profiling.yxmd` — profiling and the value-alias table
- `alteryx/01_ingest_crm_extracts.yxmd` + `macros/mc_ingest_crm_extract.yxmc` — batch macro ingesting 24 files across two schemas
- `alteryx/02_build_pipeline_mart.yxmd` — cleaning, owner matching, account linking, stage stints (Phases 1–5 of the original plan)
- `alteryx/backup/` — workflow snapshots; `images/screenshots/` — evidence

The project was then rebuilt on a licence-free, version-controlled stack (dbt + DuckDB + Python + Power BI) at the repository root.
The Alteryx numbers (4,800 deals, 212 rejected rows, 720 master accounts, 12,017 stints, 2,109 first-pass owner matches) are reproduced
exactly by the dbt models and enforced by `dq_reconciliation`. The Alteryx work stopped after Phase 5; business rules, the model,
reconciliation and outputs exist only in the dbt version.
