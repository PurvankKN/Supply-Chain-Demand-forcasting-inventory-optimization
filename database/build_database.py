"""
build_database.py
------------------
Loads the raw CSVs into a SQLite star-schema data warehouse
(scm_warehouse.db) with dimension and fact tables, plus indexes
for the query patterns the forecasting/optimization layers use.
"""

import sqlite3
import pandas as pd
import os

DB_PATH = "database/scm_warehouse.db"
RAW_DIR = "data/raw"

SCHEMA = """
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_plant;
DROP TABLE IF EXISTS dim_supplier;
DROP TABLE IF EXISTS bridge_product_supplier;
DROP TABLE IF EXISTS fact_demand_history;
DROP TABLE IF EXISTS fact_inventory;

CREATE TABLE dim_product (
    product_id   TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    category     TEXT,
    segment      TEXT,
    unit_cost    REAL
);

CREATE TABLE dim_plant (
    plant_id              TEXT PRIMARY KEY,
    plant_name            TEXT NOT NULL,
    region                TEXT,
    country               TEXT,
    role                  TEXT,
    monthly_capacity_units INTEGER
);

CREATE TABLE dim_supplier (
    supplier_id   TEXT PRIMARY KEY,
    supplier_name TEXT NOT NULL,
    material      TEXT,
    lead_time_days INTEGER,
    risk_score    REAL,
    country       TEXT
);

CREATE TABLE bridge_product_supplier (
    product_id  TEXT REFERENCES dim_product(product_id),
    supplier_id TEXT REFERENCES dim_supplier(supplier_id)
);

CREATE TABLE fact_demand_history (
    date         TEXT NOT NULL,
    product_id   TEXT REFERENCES dim_product(product_id),
    plant_id     TEXT REFERENCES dim_plant(plant_id),
    demand_units INTEGER
);

CREATE TABLE fact_inventory (
    product_id             TEXT REFERENCES dim_product(product_id),
    plant_id               TEXT REFERENCES dim_plant(plant_id),
    on_hand_units          INTEGER,
    unit_holding_cost_annual REAL
);

CREATE INDEX idx_demand_prod_plant ON fact_demand_history(product_id, plant_id);
CREATE INDEX idx_demand_date ON fact_demand_history(date);
"""

def main():
    os.makedirs("database", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    table_map = {
        "dim_product": "dim_product.csv",
        "dim_plant": "dim_plant.csv",
        "dim_supplier": "dim_supplier.csv",
        "bridge_product_supplier": "bridge_product_supplier.csv",
        "fact_demand_history": "fact_demand_history.csv",
        "fact_inventory": "fact_inventory.csv",
    }

    for table, csv_file in table_map.items():
        df = pd.read_csv(os.path.join(RAW_DIR, csv_file))
        df.to_sql(table, conn, if_exists="append", index=False)
        print(f"Loaded {len(df):>4} rows -> {table}")

    conn.commit()
    conn.close()
    print(f"\nDatabase built at {DB_PATH}")

if __name__ == "__main__":
    main()
