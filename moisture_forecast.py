"""Grain moisture for every crop, at every hour, member and field of data/forecast.csv.

Run:  uv run python moisture_forecast.py
Writes outputs/moisture_forecast.csv: the forecast columns plus wheat_moisture_pct,
barley_moisture_pct and osr_moisture_pct (% wet basis at the end of each hour, including the
rain rule for wheat and barley).
Starting moistures and model constants: "moisture_model" in params.yaml.
"""

from pathlib import Path

from harvest.moisture import CONSTANTS, forecast_moisture

ROOT = Path(__file__).parent
OUTPUT = ROOT / "outputs" / "moisture_forecast.csv"


def main():
    table = forecast_moisture(ROOT / "data" / "forecast.csv")
    OUTPUT.parent.mkdir(exist_ok=True)
    table.to_csv(OUTPUT, index=False, float_format="%.3f")

    # summary: the last hour, averaged over forecast members
    crops = list(CONSTANTS["crops"])
    columns = [f"{crop}_moisture_pct" for crop in crops]
    last = table[table["hour"] == table["hour"].max()]
    summary = last.groupby("field")[columns].mean()
    print(f"Moisture (% wet basis) at hour {last['hour'].iloc[0]}, average over members")
    print(
        "start: "
        + ", ".join(f"{crop} {CONSTANTS['crops'][crop]['start_moisture_pct']}%" for crop in crops)
    )
    print(summary.rename(columns=dict(zip(columns, crops))).round(2).to_string())
    print(f"\nSaved {len(table):,} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
