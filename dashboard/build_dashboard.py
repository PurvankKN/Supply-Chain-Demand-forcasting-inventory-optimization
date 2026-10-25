"""
build_dashboard.py
--------------------
Assembles a formatted Excel dashboard (outputs/SCM_Dashboard.xlsx)
from the pipeline's CSV outputs: an overview sheet, demand forecast sheet
with a chart, inventory plan sheet with conditional formatting + reorder
formulas, and a multi-echelon pooling sheet.
"""

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.chart import LineChart, BarChart, Reference
from openpyxl.formatting.rule import CellIsRule

FONT_NAME = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(name=FONT_NAME, bold=True, color="FFFFFF", size=11)
BODY_FONT = Font(name=FONT_NAME, size=10)
TITLE_FONT = Font(name=FONT_NAME, bold=True, size=14, color="1F3864")
THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def style_header(ws, row, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER


def write_df(ws, df, start_row=1, start_col=1):
    for j, col in enumerate(df.columns):
        ws.cell(row=start_row, column=start_col + j, value=col)
    for i, (_, row) in enumerate(df.iterrows()):
        for j, val in enumerate(row):
            cell = ws.cell(row=start_row + 1 + i, column=start_col + j, value=val)
            cell.font = BODY_FONT
            cell.border = BORDER
    style_header(ws, start_row, len(df.columns))
    for j, col in enumerate(df.columns):
        col_letter = get_column_letter(start_col + j)
        max_len = max([len(str(col))] + [len(str(v)) for v in df[col].astype(str)])
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 40)
    return start_row + 1 + len(df)


def build():
    forecast = pd.read_csv("outputs/demand_forecast.csv")
    inv_plan = pd.read_csv("outputs/inventory_plan.csv")
    pooling = pd.read_csv("outputs/multi_echelon_pooling.csv")

    wb = Workbook()

    # ---------------- Overview sheet ----------------
    ws0 = wb.active
    ws0.title = "Overview"
    ws0["B2"] = "Multi-Region Electrical Components — Demand Forecasting & Inventory Optimization"
    ws0["B2"].font = TITLE_FONT
    ws0["B4"] = "Scope: 6 Electrical-segment SKUs (circuit breakers, switchgear, UPS, PDUs, busway, wiring devices)"
    ws0["B5"] = "across 4 plants/DCs (Pondicherry, Ohio, Cork, Monterrey), 36 months of demand history, 6-month forecast."
    ws0["B4"].font = BODY_FONT
    ws0["B5"].font = BODY_FONT

    reorder_count = int((inv_plan.status == "REORDER NOW").sum())
    total_combos = len(inv_plan)
    avg_mape = forecast["backtest_mape_pct"].mean()

    kpis = [
        ("Product–Plant combinations tracked", total_combos),
        ("Combinations flagged REORDER NOW", reorder_count),
        ("Avg. forecast backtest MAPE (%)", round(avg_mape, 1)),
        ("SKUs recommended for regional safety-stock pooling",
         int((pooling.recommendation == "Consider regional buffer pooling").sum())),
    ]
    r = 7
    ws0.cell(row=r, column=2, value="Key Metrics").font = Font(name=FONT_NAME, bold=True, size=12)
    r += 1
    for label, value in kpis:
        ws0.cell(row=r, column=2, value=label).font = BODY_FONT
        ws0.cell(row=r, column=4, value=value).font = Font(name=FONT_NAME, bold=True, size=11, color="C00000")
        r += 1
    ws0.column_dimensions["B"].width = 45
    ws0.column_dimensions["D"].width = 14

    # ---------------- Demand Forecast sheet ----------------
    ws1 = wb.create_sheet("Demand Forecast")
    last_row = write_df(ws1, forecast)

    # Chart: total forecast demand by month, summed across plants, per product
    pivot = forecast.pivot_table(index="forecast_month", columns="product_id",
                                  values="forecast_demand", aggfunc="sum").reset_index()
    chart_start_row = last_row + 3
    write_df(ws1, pivot, start_row=chart_start_row)

    chart = LineChart()
    chart.title = "6-Month Forecast Demand by Product"
    chart.y_axis.title = "Units"
    chart.x_axis.title = "Month"
    n_cols = len(pivot.columns)
    data = Reference(ws1, min_col=2, max_col=n_cols, min_row=chart_start_row, max_row=chart_start_row + len(pivot))
    cats = Reference(ws1, min_col=1, min_row=chart_start_row + 1, max_row=chart_start_row + len(pivot))
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.width, chart.height = 22, 11
    ws1.add_chart(chart, f"A{chart_start_row + len(pivot) + 3}")

    # ---------------- Inventory Plan sheet ----------------
    ws2 = wb.create_sheet("Inventory Plan")
    write_df(ws2, inv_plan)
    status_col_letter = get_column_letter(list(inv_plan.columns).index("status") + 1)
    rng = f"{status_col_letter}2:{status_col_letter}{len(inv_plan)+1}"
    ws2.conditional_formatting.add(
        rng,
        CellIsRule(operator="equal", formula=['"REORDER NOW"'],
                   fill=PatternFill("solid", fgColor="FFC7CE"),
                   font=Font(name=FONT_NAME, color="9C0006"))
    )
    ws2.conditional_formatting.add(
        rng,
        CellIsRule(operator="equal", formula=['"OK"'],
                   fill=PatternFill("solid", fgColor="C6EFCE"),
                   font=Font(name=FONT_NAME, color="006100"))
    )

    # Bar chart: current on-hand vs reorder point, one bar group per row (top 10 by risk)
    top_risk = inv_plan.sort_values("days_of_cover").head(10).reset_index(drop=True)
    chart_row = len(inv_plan) + 4
    ws2.cell(row=chart_row, column=1, value="Top 10 Lowest Days-of-Cover (chart source)")
    write_df(ws2, top_risk[["product_name", "current_on_hand_units", "reorder_point_units"]], start_row=chart_row + 1)

    bar = BarChart()
    bar.type = "col"
    bar.title = "On-Hand vs Reorder Point — Top 10 At-Risk SKU/Plant Combos"
    bar.y_axis.title = "Units"
    data2 = Reference(ws2, min_col=2, max_col=3, min_row=chart_row + 1, max_row=chart_row + 1 + len(top_risk))
    cats2 = Reference(ws2, min_col=1, min_row=chart_row + 2, max_row=chart_row + 1 + len(top_risk))
    bar.add_data(data2, titles_from_data=True)
    bar.set_categories(cats2)
    bar.width, bar.height = 24, 11
    ws2.add_chart(bar, f"A{chart_row + len(top_risk) + 4}")

    # ---------------- Multi-Echelon Pooling sheet ----------------
    ws3 = wb.create_sheet("Multi-Echelon Pooling")
    write_df(ws3, pooling)

    wb.save("outputs/SCM_Dashboard.xlsx")
    print("Dashboard written to outputs/SCM_Dashboard.xlsx")


if __name__ == "__main__":
    build()
