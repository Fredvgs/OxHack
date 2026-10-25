"""How much does the forecast grain moisture depend on the rain settings?

Runs every crop on data/forecast.csv at several rain thresholds, and oilseed rape at several
rain_rise_scale values, each with a modified copy of the moisture constants (params.yaml is not
changed). Reports the moisture at the last forecast hour, over every member and field.

Run:  uv run python scripts/rain_sensitivity.py
      (values tried: "rain_sensitivity" in params.yaml)
"""

import copy
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))  # so "harvest" imports when run from scripts/

from harvest.moisture import CONSTANTS, WEATHER_COLUMNS, simulate  # noqa: E402


def load_weather(path):
    """temp_c, RH (decimal) and rain_mm as [member x field, hour] arrays, from the forecast CSV."""
    table = pd.read_csv(path, usecols=["hour", "member", "field", *WEATHER_COLUMNS])
    table = table.sort_values(["member", "field", "hour"], ignore_index=True)
    n_hours = table["hour"].nunique()
    T_c = table["temp_c"].to_numpy(dtype=float).reshape(-1, n_hours)
    RH = table["humidity_pct"].to_numpy(dtype=float).reshape(-1, n_hours) / 100
    rain_mm = table["rain_mm"].to_numpy(dtype=float).reshape(-1, n_hours)
    return T_c, RH, rain_mm


def end_moisture(crop, constants, weather):
    """Moisture (% wet basis) at the last hour, one value per (member, field)."""
    start = constants["crops"][crop]["start_moisture_pct"]
    return simulate(crop, start, *weather, constants=constants)[:, -1]


def main():
    settings = yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))
    tries = settings["rain_sensitivity"]
    weather = load_weather(ROOT / "data" / "forecast.csv")
    rain_mm = weather[2]

    print("Share of forecast hours with rain:")
    print(f"  > 0 mm: {(rain_mm > 0).mean():6.1%}")
    for threshold in tries["thresholds_mm"]:
        if threshold > 0:
            print(f"  >= {threshold} mm: {(rain_mm >= threshold).mean():6.1%}")

    runs = []  # (crop, setting, constants)
    for threshold in tries["thresholds_mm"]:
        constants = copy.deepcopy(CONSTANTS)
        constants["rain_threshold_mm"] = threshold
        runs += [(crop, f"threshold {threshold} mm", constants) for crop in constants["crops"]]
    for scale in tries["osr_rain_rise_scales"]:
        constants = copy.deepcopy(CONSTANTS)
        constants["crops"]["osr"]["rain_rise_scale"] = scale
        runs.append(("osr", f"rain_rise_scale {scale}", constants))

    print("\nMoisture at the last forecast hour, % wet basis, over every member and field")
    print(
        f"(current settings: threshold {CONSTANTS['rain_threshold_mm']} mm, osr rain_rise_scale "
        f"{CONSTANTS['crops']['osr']['rain_rise_scale']})"
    )
    print(f"{'crop':<8} {'setting':<24} {'mean':>6} {'min':>6} {'max':>6}")
    for crop, setting, constants in sorted(runs, key=lambda run: run[0]):
        end = end_moisture(crop, constants, weather)
        print(f"{crop:<8} {setting:<24} {end.mean():6.2f} {end.min():6.2f} {end.max():6.2f}")


if __name__ == "__main__":
    main()
