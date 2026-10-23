"""Export the dbt marts and ML outputs from DuckDB to CSV for Power BI, the data-quality evidence and the AI experiment.

Run after `dbt build` and `python ml/win_probability.py`:  python scripts/export_outputs.py
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
con = duckdb.connect(str(ROOT / "warehouse" / "nexora.duckdb"), read_only=True)

EXPORTS = {
    "data/output/powerbi": [
        "pipeline_deals", "pipeline_stage_stints", "sales_team", "dim_accounts", "dept_quarter_summary",
        "dq_reconciliation", "rejected_records", "ml.model_scores", "ml.model_calibration", "ml.model_backtest",
        "ml.model_feature_importance", "ml.model_explanations",
    ],
    "data/output/quality": ["rejected_records", "dq_reconciliation"],
}

for folder, tables in EXPORTS.items():
    out = ROOT / folder
    out.mkdir(parents=True, exist_ok=True)
    for t in tables:
        name = t.split(".")[-1]
        con.execute(f"copy (select * from {t}) to '{(out / (name + '.csv')).as_posix()}' (header, delimiter ',')")
        n = con.sql(f"select count(*) from {t}").fetchone()[0]
        print(f"{folder}/{name}.csv  {n:>6,} rows")

# --- AI experiment inputs -------------------------------------------------------------------------------------------
ai = ROOT / "data/output/ai"
ai.mkdir(parents=True, exist_ok=True)
con.execute(f"""copy (select * from read_csv('{(ROOT / "data/raw/crm_exports/opportunities").as_posix()}/opps_*.csv',
                union_by_name = true, all_varchar = true, filename = true))
                to '{(ai / "raw_union_uncleaned.csv").as_posix()}' (header, delimiter ',')""")
con.execute(f"""copy (select opportunity_id, opportunity_name, account_name, country_name, sales_region, industry,
                owner_name, sales_manager, department, service_line, deal_type, stage, forecast_category, is_open,
                is_won, is_lost, currency, amount_local, amount_eur, governed_probability, weighted_amount_eur,
                created_date, expected_close_date, actual_close_date, days_in_current_stage, stuck_after_days, is_stuck,
                is_at_risk, risk_reasons, dq_flags from pipeline_deals)
                to '{(ai / "pipeline_deals_for_ai.csv").as_posix()}' (header, delimiter ',')""")
print("data/output/ai/raw_union_uncleaned.csv + pipeline_deals_for_ai.csv")
