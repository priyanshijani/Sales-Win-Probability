# Business Definitions — Nexora Consulting Sales Pipeline
*The single source of truth for every number on the dashboards and every answer an AI gives about the pipeline.*

> **Version** 1.0 · **As-of date** 15 Sep 2026 (`SnapshotDate`) · **Owner** Sales Operations (you) · **Status** Draft for CRO sign-off
> Each rule states **what**, **how it's calculated**, **why we chose it**, and **where it's implemented**.
> "dbt" = calculated at row level in the transformation layer (`models/marts/pipeline_deals.sql`). "Power BI" = aggregation in a DAX measure (`powerbi/measures.dax`).

---

## 1. Pipeline stages

| Order | Stage | Confidence band | Governed probability | Forecast category | Stuck after |
|---|---|---|---|---|---|
| 1 | Discovery | 0–50% | 25% | Pipeline | 40 days |
| 2 | Solution Design | 50–75% | 60% | Pipeline | 45 days |
| 3 | Proposal | 75–90% | 80% | Best Case | 50 days |
| 4 | Negotiation | 90–100% | 95% | Commit | 30 days |
| 5 | Closed Won | 100% | 100% | Closed Won | — |
| 0 | Closed Lost | 0% | 0% | Closed Lost | — |

- **Stored in** `data/reference/stage_rules.csv` so Sales Ops can change a threshold without editing any SQL.
- **Why governed probabilities?** Reps type their own probability, and some teams are consistently optimistic. A forecast must not depend on who typed it. We keep the rep's number as `rep_probability` to *measure* forecast honesty, but we never forecast with it.
- **Why these stuck thresholds?** Roughly 1.5× the typical (median) time deals spend in each stage over the last 24 months. Beyond that, the chance of winning drops sharply.
- **Forecast category** is derived from the stage, not taken from the rep-entered `Forecast_Category` field (which disagrees with the stage in ~15% of v2 records).

## 2. Deal-level definitions (dbt)

| Term | Definition | Why |
|---|---|---|
| **Opportunity** | One unique `opportunity_id` (format `OPP-000000`), latest version by `last_modified`. Test records (name contains "TEST", owner "CRM Admin", account `ACC-00000`) are excluded. | The CRM re-exports some deals and keeps test data; counting rows would inflate the pipeline. |
| **Open deal** | Stage is Discovery, Solution Design, Proposal or Negotiation. | — |
| **Amount (EUR)** | Parsed amount × FX rate (EUR per 1 unit). **Closed deals:** rate of the close month. **Open deals:** rate of the snapshot month (2026-09). | Finance values bookings at the rate when they were won, and open pipeline at today's rate. |
| **Currency (missing)** | If blank, use the currency of the account's country. | The CRM defaults to the local currency; blanks are almost always local. |
| **Negative amount** | Use the absolute value; flag `AMOUNT_NEGATIVE`. | A contract cannot be worth less than zero; this is a sign-entry error. |
| **Outlier amount** | Any single deal above €5,000,000 is flagged `AMOUNT_OUTLIER` and **excluded from € metrics** until Sales Ops confirms it. | Our largest genuine deals are ~€4M. A typo of ×100 would distort every total. |
| **Missing amount** | Kept in deal counts, excluded from € metrics, flagged `AMOUNT_MISSING`. | Early-stage deals often have no estimate yet; deleting them would understate activity. |
| **Weighted amount** | `amount_eur × governed_probability` (open deals only). | Standard expected-value forecast. |
| **Close date (missing for won deals)** | Use the timestamp of the move to Closed Won in the stage history. | The audit log is system-generated and more reliable than a manually typed date. |
| **Days in current stage** | Snapshot date − date the deal entered its current stage (from stage history). | The deal record only shows the current stage, not when it got there. |
| **Stuck deal** | Open and `days_in_current_stage` > stage's `stuck_after_days`. | See section 1. |
| **Stale deal** | Open and no logged activity for more than 30 days. | A deal nobody is working on is not really pipeline. |
| **Past-due deal** | Open and `expected_close_date` is before the snapshot date. | The rep hasn't updated the expected close date; the forecast is out of date. |
| **Orphaned deal** | Open deal owned by someone who has left (`OWNER_LEFT`). | Nobody is accountable for it. |
| **At-risk deal** | Open and (stuck OR stale OR past-due OR orphaned). `risk_reasons` lists which. | One simple list for the Monday pipeline review. |
| **Regression** | A move from a later open stage back to an earlier open stage (e.g. Proposal → Solution Design). | Signals re-scoping or weak qualification. |
| **Max stage reached** | Highest open-stage order a deal ever reached (Closed Won = 5). | Needed for honest stage conversion rates, since lost deals no longer show where they got to. |
| **Lost at stage** | The stage a deal was in immediately before Closed Lost. | Shows *where* we lose, not only *why*. |
| **Sales cycle (days)** | `actual_close_date − created_date`, closed deals only. | — |
| **Deal size band** | < €50k · €50–150k · €150–500k · €500k–1M · > €1M. | Matches how the CRO talks about deals. |
| **Deal type** | **Expansion** if the account had a Closed Won deal *before* this deal was created; otherwise **New Logo**. | Rep-entered "Lead Source = Upsell" is unreliable; the account's history is not. |

## 3. Account definitions (dbt)

| Term | Definition | Why |
|---|---|---|
| **Master account** | Account records whose names match after upper-casing, trimming, collapsing spaces, removing a trailing "." and removing the legal suffix (GmbH, AG, Ltd, S.A., B.V., …) are one company. The lowest `account_id` becomes `master_account_id`. | 45 companies exist twice in the CRM. Without this, the map and "top accounts" double-count them. |
| **Active Customer** | Master account with at least one Closed Won deal in the last 12 months. | "Customer" means someone currently buying, not someone who bought once in 2024. |
| **Lapsed Customer** | Has a Closed Won deal, but none in the last 12 months. | A re-activation target. |
| **Prospect** | Never won a deal. | — |
| **Sales region** | From the account's country via `country_region_mapping.csv` (e.g. Ireland → UK & Ireland), *not* from the rep's territory. | Market analysis is about where the client is. |
| **Coordinates** | If latitude/longitude are missing, use the average of other accounts in the same city. If they look swapped (latitude outside 34–72 and longitude inside it), swap them back. | Keeps every account on the map without inventing locations. |
| **Unknown account** | Deals pointing to an account deleted in the CRM keep their value in totals with account "Unknown (deleted in CRM)" and are flagged `ACCOUNT_MISSING`. | Removing them would make totals disagree with the CRM. |

## 4. People definitions (dbt)

| Term | Definition |
|---|---|
| **Deal owner** | Resolved to one email: v2 records use `Owner_Email` (lower-cased). v1 records match the owner name to the roster (case-insensitive; "Last, First" reordered; initials + surname; remaining spellings via `value_aliases.csv`). |
| **Active rep** | No leave date, or leave date after the snapshot date. |
| **Department** | From the deal record, standardised via `value_aliases.csv` (v2 codes like `DATA_AI` → Data & AI). |
| **Prorated quota (YTD)** | Annual quota × (days elapsed in 2026 ÷ 365). Leavers and joiners are prorated to their active days. |

## 5. Dashboard metrics (Power BI)

| Metric | Formula | Notes |
|---|---|---|
| **Open Pipeline €** | `SUM(amount_eur)` where `is_open` | Excludes outliers and missing amounts |
| **Weighted Pipeline €** | `SUM(weighted_amount_eur)` | |
| **Bookings €** | `SUM(amount_eur)` where `is_won`, by `actual_close_date` | |
| **Target Attainment %** | Bookings ÷ Target for the same department and quarter | From `dept_quarter_summary` |
| **Pipeline Coverage ×** | Open pipeline € expected to close in the quarter ÷ that quarter's target | Healthy ≥ 3× for our cycle length |
| **Win Rate (count)** | Won deals ÷ (Won + Lost deals), by close date in the period | Open deals excluded — they haven't been decided |
| **Win Rate (value)** | Won € ÷ (Won € + Lost €) | Shown in tooltips |
| **Stage conversion %** | Deals with `max_stage_reached ≥ N+1` ÷ deals with `max_stage_reached ≥ N`, for deals created in the period | |
| **€ At Risk** | `SUM(amount_eur)` where `is_at_risk` | |
| **Forecast honesty gap (pts)** | `AVG(rep_probability − governed_probability × 100)` on open deals | Positive = optimistic |
| **Quota attainment YTD %** | FY2026 bookings ÷ prorated quota | |

## 5b. Predictive win probability (advisory)

| Term | Definition | Why |
|---|---|---|
| **Model win probability** | Probability (0–1) that an open deal ends Closed Won, from model `wp-v1-2026-09-15` (see `docs/model_card.md`). Uses only information known while the deal is open. | Stage alone treats all Proposal deals the same; history shows size, industry, region, team and time-in-stage matter. |
| **Model-weighted pipeline €** | `SUM(amount_eur × model_win_probability)` for scored open deals. | Compared with the governed weighted pipeline to test the forecast. |
| **Model review flag** | "Review" when model and governed probability differ by 25 points or more. | Points the Monday review at the deals where "the rule" and "the data" disagree most. |
| **Driver impact (pts)** | How many percentage points one fact about an open deal (e.g. its industry or stage) adds to or removes from the model's win probability, compared with a neutral value of that fact (the average across the open pipeline). Computed one fact at a time, so close to but not exactly additive. | Lets a manager see *why* the model rates a deal as it does, and challenge it. Drivers describe past patterns, not causes. |
| **Status** | *Advisory*: shown next to, never instead of, the governed forecast until it beats it for two consecutive quarters with CRO sign-off. | A model must earn trust before it drives commitments. |

## 6. Known limitations
- Data is synthetic. Patterns were designed for learning, not taken from a real company.
- FX rates are monthly averages; finance may use daily rates.
- Activity dates come from the CRM and miss offline contact (calls from mobile phones, events).
- Stuck thresholds should be reviewed each quarter as the business mix changes.

## 7. Change log
| Date | Change | Approved by |
|---|---|---|
| 2026-09-24 | v1.0 drafted | — |
| 2026-09-24 | v1.1 added predictive win probability (advisory) | — |
