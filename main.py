"""
main.py
--------
Runs the full pipeline end-to-end:
  1. Generate synthetic data (skip if data/raw already populated and you want to keep it fixed)
  2. Build the SQLite data warehouse
  3. Forecast demand (6 months ahead) per product-plant
  4. Compute inventory policy (safety stock, ROP, EOQ) + multi-echelon pooling analysis
  5. Build the Excel dashboard

Usage:
    python main.py
"""

import subprocess
import sys


STEPS = [
    ("Generating synthetic demand/supply data", ["python3", "data/generate_data.py"]),
    ("Building SQLite data warehouse", ["python3", "database/build_database.py"]),
    ("Forecasting demand", ["python3", "forecasting/demand_forecasting.py"]),
    ("Optimizing inventory policy", ["python3", "optimization/inventory_optimization.py"]),
    ("Building Excel dashboard", ["python3", "dashboard/build_dashboard.py"]),
]


def main():
    for label, cmd in STEPS:
        print(f"\n{'='*70}\n{label}\n{'='*70}")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"\nStep failed: {label}")
            sys.exit(1)
    print("\nPipeline complete. See outputs/ for results and outputs/SCM_Dashboard.xlsx for the dashboard.")


if __name__ == "__main__":
    main()
