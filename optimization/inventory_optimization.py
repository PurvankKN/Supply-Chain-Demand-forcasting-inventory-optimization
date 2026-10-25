"""
inventory_optimization.py
--------------------------
Turns the demand forecast into actionable inventory policy per
product-plant combination:

  - Safety stock (service-level driven, using lead-time demand variability)
  - Reorder point (ROP)
  - Economic order quantity (EOQ)
  - Days/weeks of cover from current on-hand inventory
  - A simple two-echelon flag: which plants for a product could be served
    from a shared regional buffer instead of holding full local safety stock
    (relevant for global manufacturers whose plant footprint spans APAC / NA / EMEA
    manufacturing + distribution nodes)

Service level assumption: 95% (z = 1.645). This is documented, not hardcoded
silently -- see ASSUMPTIONS in the README.
"""

import sqlite3
import numpy as np
import pandas as pd

DB_PATH = "database/scm_warehouse.db"
SERVICE_LEVEL_Z = 1.645  # 95% service level
ORDERING_COST_PER_ORDER = 250.0  # placeholder assumption, documented in README


def load_reference_data():
    conn = sqlite3.connect(DB_PATH)
    products = pd.read_sql("SELECT * FROM dim_product", conn)
    plants = pd.read_sql("SELECT * FROM dim_plant", conn)
    inventory = pd.read_sql("SELECT * FROM fact_inventory", conn)
    demand_hist = pd.read_sql("SELECT * FROM fact_demand_history", conn, parse_dates=["date"])
    suppliers = pd.read_sql("SELECT * FROM dim_supplier", conn)
    bridge = pd.read_sql("SELECT * FROM bridge_product_supplier", conn)
    conn.close()
    return products, plants, inventory, demand_hist, suppliers, bridge


def avg_lead_time_for_product(product_id, bridge, suppliers):
    sup_ids = bridge[bridge.product_id == product_id]["supplier_id"]
    lts = suppliers[suppliers.supplier_id.isin(sup_ids)]["lead_time_days"]
    return lts.mean() if len(lts) else 21.0  # default 21 days if unmapped


def run_optimization():
    products, plants, inventory, demand_hist, suppliers, bridge = load_reference_data()
    forecast = pd.read_csv("outputs/demand_forecast.csv")

    # Average forecast demand per month (next 6 months) per product-plant, plus recent std dev
    fc_summary = forecast.groupby(["product_id", "plant_id"]).agg(
        avg_monthly_forecast=("forecast_demand", "mean")
    ).reset_index()

    hist_std = demand_hist.groupby(["product_id", "plant_id"])["demand_units"].std().reset_index()
    hist_std.columns = ["product_id", "plant_id", "monthly_std"]

    plan = fc_summary.merge(hist_std, on=["product_id", "plant_id"])
    plan = plan.merge(inventory, on=["product_id", "plant_id"])
    plan = plan.merge(products[["product_id", "product_name", "unit_cost"]], on="product_id")
    plan = plan.merge(plants[["plant_id", "plant_name", "region"]], on="plant_id")

    rows = []
    for _, r in plan.iterrows():
        lead_time_days = avg_lead_time_for_product(r.product_id, bridge, suppliers)
        lead_time_months = lead_time_days / 30.0

        daily_demand = r.avg_monthly_forecast / 30.0
        daily_std = r.monthly_std / np.sqrt(30)  # approximate daily std from monthly std

        # Safety stock = z * sigma_LT ; sigma over the lead time = daily_std * sqrt(lead_time_days)
        safety_stock = SERVICE_LEVEL_Z * daily_std * np.sqrt(lead_time_days)
        reorder_point = daily_demand * lead_time_days + safety_stock

        annual_demand = r.avg_monthly_forecast * 12
        eoq = np.sqrt((2 * annual_demand * ORDERING_COST_PER_ORDER) / max(r.unit_holding_cost_annual, 1e-6))

        days_of_cover = r.on_hand_units / daily_demand if daily_demand > 0 else np.nan
        reorder_flag = "REORDER NOW" if r.on_hand_units <= reorder_point else "OK"

        rows.append({
            "product_id": r.product_id,
            "product_name": r.product_name,
            "plant_id": r.plant_id,
            "plant_name": r.plant_name,
            "region": r.region,
            "avg_monthly_forecast_demand": round(r.avg_monthly_forecast, 1),
            "lead_time_days": round(lead_time_days, 1),
            "safety_stock_units": round(safety_stock, 0),
            "reorder_point_units": round(reorder_point, 0),
            "eoq_units": round(eoq, 0),
            "current_on_hand_units": r.on_hand_units,
            "days_of_cover": round(days_of_cover, 1) if not np.isnan(days_of_cover) else None,
            "status": reorder_flag,
        })

    inv_plan = pd.DataFrame(rows)

    # --- Two-echelon consolidation flag ---
    # For each product, compare sum of independent safety stocks (current, per-plant)
    # vs. a pooled regional safety stock (sqrt(n) risk-pooling effect).
    pooling_rows = []
    for pid, grp in inv_plan.groupby("product_id"):
        n_plants = len(grp)
        independent_ss = grp["safety_stock_units"].sum()
        pooled_ss = independent_ss / np.sqrt(n_plants) if n_plants > 1 else independent_ss
        savings_units = independent_ss - pooled_ss
        pooling_rows.append({
            "product_id": pid,
            "num_plants": n_plants,
            "sum_independent_safety_stock": round(independent_ss, 0),
            "pooled_regional_safety_stock_estimate": round(pooled_ss, 0),
            "potential_unit_savings": round(savings_units, 0),
            "recommendation": "Consider regional buffer pooling" if savings_units > 0.15 * independent_ss else "Keep decentralized",
        })
    pooling_df = pd.DataFrame(pooling_rows)

    inv_plan.to_csv("outputs/inventory_plan.csv", index=False)
    pooling_df.to_csv("outputs/multi_echelon_pooling.csv", index=False)

    print(inv_plan[["product_name", "plant_name", "status"]].to_string(index=False))
    print(f"\n{(inv_plan.status == 'REORDER NOW').sum()} of {len(inv_plan)} product-plant combos need reordering now.")
    print("\nMulti-echelon pooling analysis:")
    print(pooling_df.to_string(index=False))
    print("\nWritten to outputs/inventory_plan.csv and outputs/multi_echelon_pooling.csv")
    return inv_plan, pooling_df


if __name__ == "__main__":
    run_optimization()
