# Build Checklist — dbt + DuckDB + Python ML + Power BI

Status as of 22 Oct 2026. `[x]` = done and verified by `dbt build` (65/65 nodes pass) · `[ ]` = open.
Original Alteryx v1 steps (Phases 0–5) are in `archive/alteryx_v1/`; this stack reproduces their numbers.

## Phase 0 — Setup
- [x] Repo on GitHub, `.gitignore`, folder structure
- [x] Seeded synthetic data generator (`scripts/generate_raw_data.py`) and raw data committed
- [x] dbt Core + DuckDB project (`dbt_project.yml`, `profiles.yml`, `requirements.txt`)
- [x] Plan, business definitions, model card template

## Phase 1 — Profile the data
- [x] Profiling findings (`docs/profiling_notes.md`): 29 stage spellings, 59 country spellings, 3 date formats, 5 amount formats, ...
- [x] Governed alias table `data/reference/value_aliases.csv` (210 rows) loaded as a dbt seed
- [x] Custom test: every (domain, spelling) maps to exactly one standard value

## Phase 2 — Ingest 24 files with schema drift
- [x] `stg_crm__opportunities`: `read_csv(opps_*.csv, union_by_name)` → 5,012 rows from 24 files
- [x] `standardise_opportunity_columns` macro driven by `crm_field_mapping_v1_v2` (replaces the Alteryx batch macro)
- [x] Parsers for dates (3 formats), amounts (5 formats), probabilities, currencies hidden in amount text

## Phase 3 — Sales team and accounts
- [x] `stg_crm__sales_roster` / `int_sales_team` (29 AEs, 8 managers, 2 leavers)
- [x] `stg_crm__accounts`: Excel with header on row 4, footer dropped, swapped coordinates fixed
- [x] `int_accounts_master`: 765 records → 720 masters; missing coordinates filled from city average

## Phase 4 — Clean the opportunities
- [x] `int_opportunity_versions`: latest version per deal, test records flagged
- [x] `rejected_records`: 206 older versions + 6 test records = 212, each with a reason
- [x] Owner matching: v2 email, v1 exact name (1,991), "Last, First" (118), initial + surname (63), alias (5)
- [x] Currency fill (138 from account country), 10 deals with deleted accounts kept and flagged

## Phase 5 — Stage history → stints
- [x] `int_stage_events`: duplicates removed after parsing (minute vs second precision)
- [x] `int_stage_stints`: 12,017 stints via `lead()`; exit type Advanced / Regressed / Won / Lost / Open; 724 current

## Phase 6 — Business rules (`pipeline_deals`)
- [x] Governed probability, forecast category, stuck threshold from `stage_rules`
- [x] FX at close month (closed) / snapshot month (open); `amount_eur`, outlier > €5M (3), negative (4), missing (44)
- [x] Weighted amount, days in stage, stuck / stale / past-due / orphaned / at-risk, `risk_reasons`
- [x] Deal type (Expansion vs New Logo), account status, deal size band, quarters, sales cycle, `dq_flags`
- [x] `dept_quarter_summary`, `sales_team` (prorated quota), `dim_accounts`

## Phase 6b — Win probability model
- [x] Leakage rules documented (`docs/model_card.md`)
- [x] Photos at day 0/14/30/45/60/90/120 per stint (20,574 photos from 2,927 deals before 1 Mar 2026)
- [x] Time-based backtest on 550 deals; logistic regression vs forest vs governed (Brier 0.208 / 0.210 / 0.264)
- [x] Retrain on all history, score 692 of 724 open deals, review flag at ≥ 25 pts
- [x] Guardrails (probabilities in [0,1], scored + not scored = 724), `ml.*` tables
- [x] Model card filled in
- [ ] Calibration plot image for the README (`ml/outputs/`) — optional, Power BI page 5 covers it

## Phase 7 — Reconciliation and tests
- [x] `dq_reconciliation`: 27 checks (control totals, row bridges, integrity) — all PASS
- [x] 40 dbt tests incl. `assert_reconciliation_passes` (fails the build)
- [x] `dbt docs generate` (lineage graph)
- [ ] Screenshot of the dbt lineage graph (`dbt docs serve`) → `images/screenshots/`

## Phase 8 — Outputs
- [x] `python scripts/run_pipeline.py` runs seeds → models → tests → ML → exports → docs
- [x] CSV exports in `data/output/powerbi/`, `quality/`, `ai/`
- [x] GitHub Actions workflow (`.github/workflows/ci.yml`)
- [ ] Confirm the first CI run is green on GitHub

## Phase 9 — Power BI dashboards
- [x] Measures (`powerbi/measures.dax`), theme, relationships and page specs (`powerbi/README.md`)
- [x] Semantic model + relationships generated (`scripts/build_pbip.py` → `powerbi/PowerBI_Workbook.pbip`)
- [x] Open the .pbip in Desktop, refresh, fix load errors (headline measures verified against the pipeline via pbi-cli)
- [~] Page 1 Pipeline Health & Forecast (first draft generated; review layout and write the "So what" line)
- [~] Page 2 Deal Velocity & Stuck Deals (first draft generated; review layout and write the "So what" line)
- [~] Page 3 Manager & Department Performance (first draft generated; review layout and write the "So what" line)
- [~] Page 4 Europe Market Opportunity (first draft generated; review layout and write the "So what" line)
- [~] Page 5 Win Probability (ML) (first draft generated; review layout and write the "So what" line)
- [~] Page 6 Why this deal? (per-deal model explanation)
- [~] Page 7 Data Trust (first draft generated; review layout and write the "So what" line)
- [ ] Check headline numbers against `powerbi/README.md` section 5
- [ ] Export a PDF + page screenshots

## Phase 10 — AI experiment
- [x] Inputs generated (`data/output/ai/raw_union_uncleaned.csv`, `pipeline_deals_for_ai.csv`)
- [ ] Round A (ungrounded), Round B (grounded), Round C (narrative + verification)
- [ ] Fill the results table in `ai_experiment/README.md` and the README table

## Phase 11 — Screenshots and README
- [ ] Replace the 7 placeholder screenshots in `images/dashboard/` with real Power BI screenshots (same file names)
- [ ] Fill the "About" section; add the live/PDF link
- [ ] Re-read the README: every claim must be backed by something in the repo

## Phase 12 — Publish
- [ ] `git push`, confirm CI is green, set repo description and topics (dbt, duckdb, power-bi, sales-analytics, scikit-learn)
- [ ] Pin the repo on the GitHub profile
- [ ] LinkedIn post (business problem → reconciliation → model finding → AI grounding)
