# Multi-Region Demand Forecasting & Inventory Optimization System

An end-to-end supply chain analytics pipeline that forecasts demand and
optimizes inventory policy for a multinational electrical-components
manufacturer's **Electrical products segment** (circuit breakers,
switchgear, UPS units, power distribution units, busway systems, wiring
devices) — a segment currently seeing strong demand growth on the back of
AI data-center infrastructure buildout.

Built as a supply chain / SCM analytics portfolio project.

## Why this project

Global power-management manufacturers ship electrical, hydraulic, and other
industrial products across multi-tier, multi-plant supply chains spanning
100+ countries. Segments tied to data-center and utility infrastructure are
currently benefiting from an AI-driven demand surge — which makes **demand
forecasting accuracy and inventory positioning** a live, high-stakes
problem: understock and you delay data-center/utility customers; overstock
and working capital gets tied up in commodity-exposed components (copper,
semiconductors, battery cells).

This project simulates that problem end-to-end: from raw transactional data
through a data warehouse, into a forecasting layer, into an inventory
optimization layer, into a decision-ready dashboard.

## Architecture

```
data/generate_data.py          → synthetic transactional data (CSV)
        │
        ▼
database/build_database.py     → SQLite star-schema warehouse (scm_warehouse.db)
        │
        ▼
forecasting/demand_forecasting.py   → 6-month demand forecast per product × plant
        │
        ▼
optimization/inventory_optimization.py → safety stock, ROP, EOQ, multi-echelon pooling
        │
        ▼
dashboard/build_dashboard.py    → outputs/SCM_Dashboard.xlsx
```

Run everything with:
```bash
pip install -r requirements.txt
python main.py
```

## Data model

**Dimensions:** `dim_product` (6 Electrical-segment SKUs), `dim_plant` (4
plants/DCs modeled on a real multinational manufacturer's global
footprint — one each in APAC, North America x2, and EMEA), `dim_supplier`
(5 tier-1 suppliers with lead times and a risk score), `bridge_product_supplier`.

**Facts:** `fact_demand_history` (36 months × 6 products × 4 plants = 864
rows, with trend + seasonality + noise reflecting real capex/budget cycles),
`fact_inventory` (current on-hand snapshot + holding cost).

> Note: real company transactional data isn't public, so this uses a
> synthetic dataset engineered to have realistic structure (trend, seasonality,
> noise, product-specific growth rates) rather than actual company figures.
> The pipeline is written generically — point `build_database.py` at any
> CSVs with the same schema and it runs on real data unchanged.

## Forecasting methodology

For each of the 24 product × plant series, two models are backtested on the
last 6 months and the better one (by MAPE) is used for the final forecast:

1. **Seasonal-naive baseline** — last year's same month, trend-adjusted.
2. **Gradient Boosting Regressor** (scikit-learn) on lag features
   (1/2/3/6/12-month lags), rolling mean/std, and calendar month.

Average backtest MAPE across all series: **~7%**.

> This environment has no internet access, so scikit-learn's
> `GradientBoostingRegressor` stands in for XGBoost, and the seasonal-naive
> baseline stands in for Prophet. The feature engineering (lags, rolling
> windows, calendar features) is the same approach either library would use.
> See "Extending this project" below to swap in Prophet/XGBoost.

## Inventory optimization methodology

For each product × plant:
- **Safety stock** = z(95% service level = 1.645) × σ over lead time
- **Reorder point (ROP)** = lead-time demand + safety stock
- **EOQ** = √(2 × annual demand × ordering cost ÷ annual holding cost)
- **Days of cover** from current on-hand inventory
- Flags combinations currently below ROP as `REORDER NOW`

**Multi-echelon pooling analysis:** for each product, compares the sum of
independent per-plant safety stocks against a pooled regional buffer
(√n risk-pooling approximation), flagging SKUs where consolidating safety
stock into a shared regional buffer could meaningfully cut inventory —
directly relevant to manufacturers running a multi-region plant network
(APAC/NA/EMEA).

**Assumptions (documented, adjustable in `optimization/inventory_optimization.py`):**
- Service level: 95%
- Ordering cost: $250/order (placeholder — replace with a company-specific figure if known)
- Holding cost: 22% of unit cost annually (industry-typical range)

## Results (this run)

- 24 of 24 product-plant combinations forecasted, ~7% avg backtest MAPE
- 11 of 24 combinations currently flagged `REORDER NOW` — concentrated in
  UPS units, PDUs, and busway systems, the SKUs most exposed to data-center
  demand growth
- All 6 SKUs show a >15% inventory reduction opportunity from regional
  safety-stock pooling across the 4-plant network

See `outputs/demand_forecast.csv`, `outputs/inventory_plan.csv`,
`outputs/multi_echelon_pooling.csv`, and `outputs/SCM_Dashboard.xlsx`
(Overview / Demand Forecast / Inventory Plan / Multi-Echelon Pooling tabs,
with charts and conditional formatting on reorder status).

## Extending this project

- Swap `GradientBoostingRegressor` for `xgboost.XGBRegressor` (same feature
  matrix) or add Facebook Prophet for the seasonal-naive baseline's role.
- Replace synthetic data with a real point-of-sale/ERP extract by matching
  the CSV schemas in `data/raw/`.
- Extend with a MILP network model to jointly optimize *where* each plant's
  output should route, on top of *how much* to hold at each node.
- Add a supplier-risk-weighted safety stock adjustment using the
  `risk_score` field already in `dim_supplier` (higher-risk suppliers →
  higher safety stock multiplier).

## Tech stack

Python · pandas · scikit-learn · SQLite · openpyxl · (optional: XGBoost, Prophet)

## Author

Anshikha Chaurasiya — B.Tech, Production & Industrial Engineering, NIT Jamshedpur
[LinkedIn](https://linkedin.com/in/anshikha-chaurasiya-24681328a)
