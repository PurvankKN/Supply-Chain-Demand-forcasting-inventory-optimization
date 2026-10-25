"""
generate_data.py
-----------------
Generates realistic synthetic supply-chain data modeled on a global power-management manufacturer's
Electrical segment (circuit breakers, switchgear, UPS units, power distribution
units, busway systems) — the segment driving current data-center /
electrification growth.

Since real company transactional data isn't public, this script builds a
plausible multi-plant, multi-product, multi-supplier dataset with realistic
seasonality (data-center capex cycles), trend (AI infrastructure demand boom),
and noise, so the rest of the pipeline (warehousing -> forecasting ->
inventory optimization -> dashboard) can run end-to-end on something that
behaves like real demand data.

Output: CSV files in data/raw/
"""

import numpy as np
import pandas as pd
from datetime import datetime

np.random.seed(42)

# ---------------------------------------------------------------------------
# 1. Dimension: Products (Electrical-segment SKUs)
# ---------------------------------------------------------------------------
products = pd.DataFrame([
    {"product_id": "P01", "product_name": "Low-Voltage Circuit Breaker",  "category": "Circuit Protection",  "segment": "Electrical", "unit_cost": 145.0},
    {"product_id": "P02", "product_name": "Medium-Voltage Switchgear",    "category": "Power Distribution",  "segment": "Electrical", "unit_cost": 8200.0},
    {"product_id": "P03", "product_name": "Uninterruptible Power Supply (UPS)", "category": "Power Quality", "segment": "Electrical", "unit_cost": 3400.0},
    {"product_id": "P04", "product_name": "Power Distribution Unit (PDU)","category": "Data Center",         "segment": "Electrical", "unit_cost": 620.0},
    {"product_id": "P05", "product_name": "Busway System (per section)", "category": "Power Distribution",  "segment": "Electrical", "unit_cost": 980.0},
    {"product_id": "P06", "product_name": "Wiring Device / Connector Kit","category": "Industrial Components","segment": "Electrical","unit_cost": 38.0},
])

# ---------------------------------------------------------------------------
# 2. Dimension: Plants / Distribution Centers (modeled on a real multinational manufacturer's footprint)
# ---------------------------------------------------------------------------
plants = pd.DataFrame([
    {"plant_id": "PL01", "plant_name": "Pondicherry Plant",       "region": "APAC",          "country": "India",  "role": "Manufacturing", "monthly_capacity_units": 42000},
    {"plant_id": "PL02", "plant_name": "Ohio Electrical Plant",   "region": "North America", "country": "USA",    "role": "Manufacturing", "monthly_capacity_units": 51000},
    {"plant_id": "PL03", "plant_name": "Cork Distribution Center","region": "EMEA",          "country": "Ireland","role": "Distribution",  "monthly_capacity_units": 36000},
    {"plant_id": "PL04", "plant_name": "Monterrey Plant",         "region": "North America", "country": "Mexico", "role": "Manufacturing", "monthly_capacity_units": 39000},
])

# ---------------------------------------------------------------------------
# 3. Dimension: Suppliers (tier-1, feeding raw materials into plants)
# ---------------------------------------------------------------------------
suppliers = pd.DataFrame([
    {"supplier_id": "S01", "supplier_name": "Copper & Conductor Metals Ltd",  "material": "Copper / Conductors", "lead_time_days": 28, "risk_score": 0.35, "country": "Chile"},
    {"supplier_id": "S02", "supplier_name": "Global Steel Components Inc",    "material": "Steel Enclosures",     "lead_time_days": 21, "risk_score": 0.22, "country": "USA"},
    {"supplier_id": "S03", "supplier_name": "Semicon Power Electronics",      "material": "Semiconductors / IGBTs","lead_time_days": 45, "risk_score": 0.61, "country": "Taiwan"},
    {"supplier_id": "S04", "supplier_name": "Precision Molding Solutions",    "material": "Plastic / Polymer Parts","lead_time_days": 18, "risk_score": 0.18, "country": "Mexico"},
    {"supplier_id": "S05", "supplier_name": "Battery Cell Systems Pvt Ltd",   "material": "Battery Cells (UPS)",  "lead_time_days": 35, "risk_score": 0.48, "country": "India"},
])

product_supplier = pd.DataFrame([
    {"product_id": "P01", "supplier_id": "S02"},
    {"product_id": "P01", "supplier_id": "S04"},
    {"product_id": "P02", "supplier_id": "S01"},
    {"product_id": "P02", "supplier_id": "S02"},
    {"product_id": "P03", "supplier_id": "S03"},
    {"product_id": "P03", "supplier_id": "S05"},
    {"product_id": "P04", "supplier_id": "S03"},
    {"product_id": "P05", "supplier_id": "S01"},
    {"product_id": "P06", "supplier_id": "S04"},
])

# ---------------------------------------------------------------------------
# 4. Fact: 36 months of monthly demand history per product-plant combination
# ---------------------------------------------------------------------------
months = pd.date_range(end=datetime(2026, 6, 1), periods=36, freq="MS")

base_demand = {
    "P01": 9000, "P02": 420, "P03": 1100, "P04": 3200, "P05": 2600, "P06": 24000,
}
# Data-center / electrification boom -> stronger upward trend for DC-relevant SKUs
trend_per_month = {
    "P01": 25, "P02": 6, "P03": 22, "P04": 55, "P05": 30, "P06": 60,
}
plant_share = {
    "PL01": 0.30, "PL02": 0.34, "PL03": 0.18, "PL04": 0.18,
}

rows = []
for _, prod in products.iterrows():
    pid = prod["product_id"]
    for _, plant in plants.iterrows():
        plid = plant["plant_id"]
        share = plant_share[plid]
        for i, m in enumerate(months):
            seasonal = 1 + 0.12 * np.sin(2 * np.pi * (m.month / 12) + 0.5)  # capex/budget cycle seasonality
            trend = base_demand[pid] * share + trend_per_month[pid] * share * i
            noise = np.random.normal(0, 0.06 * trend)
            demand = max(0, trend * seasonal + noise)
            rows.append({
                "date": m.strftime("%Y-%m-%d"),
                "product_id": pid,
                "plant_id": plid,
                "demand_units": int(round(demand)),
            })

demand_history = pd.DataFrame(rows)

# ---------------------------------------------------------------------------
# 5. Fact: Current inventory snapshot
# ---------------------------------------------------------------------------
inv_rows = []
for _, prod in products.iterrows():
    for _, plant in plants.iterrows():
        avg_recent_demand = demand_history[
            (demand_history.product_id == prod.product_id) & (demand_history.plant_id == plant.plant_id)
        ].tail(3)["demand_units"].mean()
        on_hand = int(avg_recent_demand * np.random.uniform(0.8, 1.6))
        inv_rows.append({
            "product_id": prod.product_id,
            "plant_id": plant.plant_id,
            "on_hand_units": on_hand,
            "unit_holding_cost_annual": round(prod.unit_cost * 0.22, 2),  # ~22% carrying cost assumption
        })
inventory = pd.DataFrame(inv_rows)

# ---------------------------------------------------------------------------
# Write CSVs
# ---------------------------------------------------------------------------
products.to_csv("data/raw/dim_product.csv", index=False)
plants.to_csv("data/raw/dim_plant.csv", index=False)
suppliers.to_csv("data/raw/dim_supplier.csv", index=False)
product_supplier.to_csv("data/raw/bridge_product_supplier.csv", index=False)
demand_history.to_csv("data/raw/fact_demand_history.csv", index=False)
inventory.to_csv("data/raw/fact_inventory.csv", index=False)

print(f"Generated {len(demand_history)} demand records across "
      f"{products.shape[0]} products x {plants.shape[0]} plants x 36 months.")
print("Files written to data/raw/")
