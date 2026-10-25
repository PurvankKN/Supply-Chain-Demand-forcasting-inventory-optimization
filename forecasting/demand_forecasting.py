"""
demand_forecasting.py
----------------------
Forecasts monthly demand for each product-plant combination, 6 months ahead.

Two models are compared per series and the better one (by back-tested MAPE)
is used for the final forecast:

  1. Seasonal-naive baseline  (last year's same month, trend-adjusted)
  2. Gradient Boosting Regressor on lag + calendar features

Note on tooling: this environment has no internet access, so this script
uses scikit-learn's GradientBoostingRegressor as the ML forecaster instead
of XGBoost/Prophet. The feature engineering (lags, rolling stats, calendar
features) is the same approach you'd use with either library -- see
requirements.txt for how to swap in xgboost/prophet on your own machine.
"""

import sqlite3
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

DB_PATH = "database/scm_warehouse.db"
FORECAST_HORIZON = 6  # months
BACKTEST_HOLDOUT = 6  # months held out to score models


def load_demand():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM fact_demand_history", conn, parse_dates=["date"])
    conn.close()
    return df


def make_features(series: pd.Series) -> pd.DataFrame:
    """Build lag/rolling/calendar features for a single product-plant time series."""
    df = pd.DataFrame({"y": series})
    df["month"] = df.index.month
    for lag in [1, 2, 3, 6, 12]:
        df[f"lag_{lag}"] = df["y"].shift(lag)
    df["roll_mean_3"] = df["y"].shift(1).rolling(3).mean()
    df["roll_std_3"] = df["y"].shift(1).rolling(3).std()
    return df


def seasonal_naive_forecast(y: pd.Series, horizon: int) -> np.ndarray:
    """Last year's value for the same month, adjusted by recent trend ratio."""
    if len(y) < 13:
        return np.repeat(y.iloc[-1], horizon)
    recent_avg = y.iloc[-3:].mean()
    year_ago_avg = y.iloc[-15:-12].mean() if len(y) >= 15 else y.iloc[:3].mean()
    trend_ratio = recent_avg / year_ago_avg if year_ago_avg > 0 else 1.0
    forecasts = []
    for h in range(1, horizon + 1):
        idx = len(y) - 12 + h - 1
        base = y.iloc[idx] if 0 <= idx < len(y) else y.iloc[-1]
        forecasts.append(base * trend_ratio)
    return np.array(forecasts)


def mape(y_true, y_pred):
    y_true, y_pred = np.array(y_true), np.array(y_pred)
    mask = y_true != 0
    return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100


def gbr_backtest_and_forecast(y: pd.Series, horizon: int, holdout: int):
    feat = make_features(y).dropna()
    if len(feat) < holdout + 12:
        return None, None  # not enough history for a fair backtest

    train = feat.iloc[:-holdout]
    test = feat.iloc[-holdout:]

    X_cols = [c for c in feat.columns if c != "y"]
    model = GradientBoostingRegressor(n_estimators=150, max_depth=3, learning_rate=0.08, random_state=42)
    model.fit(train[X_cols], train["y"])
    backtest_pred = model.predict(test[X_cols])
    backtest_mape = mape(test["y"], backtest_pred)

    # Refit on full history, then forecast forward recursively
    model_full = GradientBoostingRegressor(n_estimators=150, max_depth=3, learning_rate=0.08, random_state=42)
    model_full.fit(feat[X_cols], feat["y"])

    history = y.copy()
    forecasts = []
    for h in range(horizon):
        next_date = history.index[-1] + pd.DateOffset(months=1)
        row = {"month": next_date.month}
        for lag in [1, 2, 3, 6, 12]:
            row[f"lag_{lag}"] = history.iloc[-lag] if len(history) >= lag else history.iloc[0]
        row["roll_mean_3"] = history.iloc[-3:].mean()
        row["roll_std_3"] = history.iloc[-3:].std()
        X_next = pd.DataFrame([row])[X_cols]
        pred = max(0, model_full.predict(X_next)[0])
        forecasts.append(pred)
        history.loc[next_date] = pred

    return backtest_mape, np.array(forecasts)


def run_forecasting():
    df = load_demand()
    products = df["product_id"].unique()
    plants = df["plant_id"].unique()

    future_months = pd.date_range(
        start=df["date"].max() + pd.DateOffset(months=1), periods=FORECAST_HORIZON, freq="MS"
    )

    results = []
    for pid in products:
        for plid in plants:
            sub = df[(df.product_id == pid) & (df.plant_id == plid)].sort_values("date")
            y = sub.set_index("date")["demand_units"].asfreq("MS")

            naive_fc = seasonal_naive_forecast(y, FORECAST_HORIZON)
            naive_backtest = seasonal_naive_forecast(y.iloc[:-BACKTEST_HOLDOUT], BACKTEST_HOLDOUT)
            naive_mape = mape(y.iloc[-BACKTEST_HOLDOUT:], naive_backtest)

            gbr_mape, gbr_fc = gbr_backtest_and_forecast(y, FORECAST_HORIZON, BACKTEST_HOLDOUT)

            if gbr_mape is not None and gbr_mape < naive_mape:
                chosen_model, chosen_mape, forecast_vals = "GradientBoosting", gbr_mape, gbr_fc
            else:
                chosen_model, chosen_mape, forecast_vals = "SeasonalNaive", naive_mape, naive_fc

            for i, month in enumerate(future_months):
                results.append({
                    "product_id": pid,
                    "plant_id": plid,
                    "forecast_month": month.strftime("%Y-%m-%d"),
                    "forecast_demand": round(float(forecast_vals[i]), 1),
                    "model_used": chosen_model,
                    "backtest_mape_pct": round(float(chosen_mape), 2),
                    "historical_std": round(float(y.std()), 1),
                })

    result_df = pd.DataFrame(results)
    result_df.to_csv("outputs/demand_forecast.csv", index=False)
    print(result_df.groupby(["product_id", "model_used"]).size())
    print(f"\nAvg backtest MAPE: {result_df['backtest_mape_pct'].mean():.1f}%")
    print("Forecast written to outputs/demand_forecast.csv")
    return result_df


if __name__ == "__main__":
    run_forecasting()
