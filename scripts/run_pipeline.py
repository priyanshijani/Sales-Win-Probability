"""Run the whole pipeline end to end: seeds -> models -> tests -> ML -> exports.

    python scripts/run_pipeline.py            # uses the committed raw data
    python scripts/run_pipeline.py --regen    # regenerate the synthetic raw data first (seeded, identical result)
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
(ROOT / "warehouse").mkdir(exist_ok=True)      # DuckDB file lives here; the folder is not guaranteed on a fresh clone


def run(*cmd):
    print(f"\n>>> {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True)


if "--regen" in sys.argv:
    run(sys.executable, "scripts/generate_raw_data.py")
run("dbt", "build", "--profiles-dir", ".")          # fails if any test or reconciliation check fails
run(sys.executable, "ml/win_probability.py")
run(sys.executable, "scripts/export_outputs.py")
run("dbt", "docs", "generate", "--profiles-dir", ".")
