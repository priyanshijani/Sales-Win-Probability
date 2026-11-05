# Model Card — Win Probability `wp-v1-2026-09-15`

> Status: **Advisory** (not the forecast of record) · Owner: Sales Operations · Built in: Python / scikit-learn, `ml/win_probability.py` (reads the dbt marts, writes the `ml` schema)

## 1. Purpose
Estimate the probability that an open opportunity will be **Closed Won**, so the CRO can see which deals are
stronger or weaker than their stage suggests. Used for review and prioritisation, **not** for the official forecast
until it has been validated for two consecutive quarters.

## 2. Data
- Source: the dbt marts `pipeline_deals` and `pipeline_stage_stints` (reconciled to the CRM control totals before the model runs).
- Training unit: a "photo" of a closed deal on day 0/14/30/45/60/90/120 of each open stage it passed through. Stage, stuck threshold and regressions come from the **stint** (what was true then), never from the deal's final state.
- Label: `Won` / `Lost` (final outcome).
- Excluded rows: deals with no amount or an amount outlier (> €5M); test records (removed upstream); deals still open (outcome unknown).

## 3. Features
| Used (known while the deal is open) | Why it's allowed |
|---|---|
| `stage` (of the photographed stint) | The deal's position at the time of the photo |
| `service_line`, `department`*, `sales_manager`, `sales_region`, `industry`, `company_size_band`, `lead_source` | Fixed attributes known at creation |
| `deal_type` | Based on wins that happened **before** the deal was created |
| `log_amount` | Deal size is known while open |
| `days_in_stage_so_far` (capped at 120), `deal_age_days`, `regressions_so_far`, `over_stuck_threshold` | Computed as of the photo date |

\* `department` is used by the forest only: service line and manager already imply it, and repeating information makes logistic-regression coefficients unstable.

| Excluded | Why (how it would leak) |
|---|---|
| `rep_probability` | 0 or 100 on closed deals, so it reveals the answer |
| rep `forecast_category` | Set by the rep from the outcome as it nears |
| `loss_reason`, `lost_at_stage`, `max_stage_reached`, `actual_close_date`, `sales_cycle_days` | Only exist once the deal has closed |
| `last_activity_date` / `days_since_activity` / `is_stale` | Equal the close date on closed deals |
| `expected_close_date` / `is_past_due` | Only today's value is stored, not the value at photo time |
| `account_status` | Uses wins that happened after the photo was taken |

## 4. Validation design
- Time-based backtest: trained on deals closed before **1 Mar 2026**, tested on the pipeline as it stood on 1 Mar 2026 (stints running that day, features computed as of that day).
- All photos of a deal stay on one side of the split.
- Final model retrained on all deals closed before 15 Sep 2026 and applied to the open pipeline.
- Training set: 20,574 photos from 2,927 deals (43.0% won per photo; higher than the per-deal rate because deals reaching later stages produce more photos). Test set: 550 deals open on 1 Mar 2026 and decided by 15 Sep 2026 (42.2% won).

## 5. Results (backtest, 550 deals)
| Metric | Governed stage probability | Logistic regression | Random forest |
|---|---|---|---|
| Brier score (lower is better) | 0.264 | **0.208** | 0.210 |
| AUC (higher is better) | 0.665 | **0.725** | 0.717 |
| Forecast won € (actual: €51.3M) | €78.9M (+53.8%) | **€55.6M (+8.4%)** | €58.8M (+14.6%) |

Chosen model: **Logistic regression**, because it has the lowest Brier score, it is simpler than the forest and its coefficients are explainable.
Top drivers (share of total coefficient magnitude): 1. service line (30%) 2. stage (22%) 3. sales manager (15%), then industry (14%) and sales region (10%).
Do these make business sense? Stage and service line are plausible drivers (different service lines have different buying cycles). Sales manager as a top-3 driver is a finding to *discuss*, not to act on automatically: it may reflect real differences in qualification discipline, or territory mix the model cannot separate.

**Business finding:** the governed stage probabilities in `stage_rules.csv` are too optimistic. In the backtest they overstate the won € by 54%, versus 8% for the model, and every governed bucket above 25% sits well above the observed win rate (e.g. Proposal: 80% governed vs 49% observed). Sales Ops should recalibrate `stage_rules.csv`; the model stays advisory until it has proven itself over two quarters.

**Today's pipeline (15 Sep 2026):** 692 of 724 open deals are scored (32 have no amount and are marked `NOT_SCORED_NO_AMOUNT`). Model-weighted pipeline is €73.8M against €104.0M governed. 212 deals are flagged `Review` because model and governed probability differ by 25 points or more.

## 6. Explaining a single deal
Every scored deal has reason codes (`ml.model_explanations`, one row per deal and feature; summarised in `ml.model_scores.model_reasoning`).
- The logistic regression's log-odds for a deal are the intercept plus one contribution per feature (coefficient x value, summed over a feature's one-hot columns).
- A feature's **impact (pts)** is the change in win probability, in percentage points, compared with a neutral value of that feature (its average contribution across today's open pipeline). The "average open deal" probability (42%) is the model's output when every feature is neutral.
- Impacts are computed one feature at a time, so they are close to, but not exactly, additive. Drivers under 2 points are left out of the one-line text.
- Each driver also gets a one-line plain-words `insight` (e.g. "Retail & Consumer Goods clients convert below average"). The wording follows the model's own sign, so it never contradicts the impact printed beside it.
- Shown on Power BI page 6 ("Why this deal?"): click a deal and see its probability, the CRM stage default, the average open deal and the drivers.
- Only the logistic regression is explained this way. If a future retrain picks the forest, `ml/win_probability.py` skips the explanations and prints a note.

**Reading caveats**
- A driver such as *sales manager* or *client industry* describes how similar deals have behaved, not why. Use it to start a conversation about qualification or territory, not to judge a person.
- *Days in current stage* has a small effect (about -1 to +2 points) and is entangled with *deal age*: raw win rates are flat across days-in-stage buckets (41-47%), while older deals clearly win less. Do not read a positive days-in-stage impact as "stuck deals win more".

## 7. Limitations
- Synthetic data with designed patterns; real CRM data will be noisier and the lift will be smaller.
- Only 550 deals in the test set, one backtest date, no confidence intervals: treat the Brier/AUC gaps as indicative.
- Deals still open at 15 Sep 2026 have no outcome yet, so the backtest only covers deals decided within about six months.
- The model learns historical team and region effects. It shows where results have come from, not why.
- Photos over-represent deals that lived longer.
- Calibration is good in the middle of the range but the extreme bins are thin (18 deals below 10%, 7 above 90%).

## 8. Governance
- Review quarterly; retrain when new outcomes arrive (`python ml/win_probability.py`).
- Promote from *Advisory* to *Forecast of record* only after two quarters of better accuracy than governed probabilities, with CRO sign-off.
- Any change is logged in `docs/business_definitions.md` → change log.
- Reproducible: seeded (`random_state=42`), inputs are reconciled dbt marts, outputs land in `ml.*` tables and `data/output/powerbi/model_*.csv`.
