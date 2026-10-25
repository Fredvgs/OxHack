"""The only file in webapp/ that talks to the model in harvest/.

It runs the season the way run.py does (one forecast member plays the weather that really
happens; the planner only sees the others) and collects what the control panel shows on top of
the result: the forecast as the planner saw it at each replan, and what really happened.
If harvest/ changes its inputs or outputs, this is the file to fix.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from harvest import planners
from harvest.forecast import load_forecast
from harvest.simulate import activities, run_season
from harvest.value import predict_moisture, start_moisture

ROOT = Path(__file__).parent.parent
WEBAPP = Path(__file__).parent
FORECAST_CSV = ROOT / "data" / "forecast.csv"
MOISTURE_CSV = ROOT / "outputs" / "moisture_forecast.csv"  # from scripts/moisture_forecast.py
WAIT = (
    planners.WAIT
)  # in a schedule: stay where you are (passed on so explain.py needn't import harvest)


def load_settings():
    """params.yaml (the model's numbers) and webapp/demo.yaml (the web app's own)."""
    params = yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))
    demo = yaml.safe_load((WEBAPP / "demo.yaml").read_text(encoding="utf-8"))
    return params, demo


def run_demo(params, demo):
    """Run the season on data/forecast.csv and collect everything the panel needs.

    returns: {
        "result":            run_season's result (see harvest/README.md)
        "plans":             one per replan: run_season's {"hour", "value", "schedule"} plus
                             "moisture_pct" [band, field, hour]: demo band_percentiles over members
                             "rain_chance" [field, hour]: share of members raining > rain_limit_mm
                             "humidity_pct" [band, field, hour]: band_percentiles over members
                             "cut_chance" [field, hour]: share of members in which it can be cut
        "true_moisture_pct": [field, hour]  grain moisture that really happened (start of hour)
        "true_rain_mm":      [field, hour]  rain that really fell
        "true_humidity_pct": [field, hour]  air humidity that really happened
        "standing_ha":       [field, hour + 1]  area still standing at the start of each hour
        "doing":             {"cutting", "driving", "waiting", "depot"}: [machine, hour] bool
        "times":             [hour + 1] Timestamps in demo time_zone, start of each hour
        "n_members":         int, forecast members the planner sees
    }
    """
    weather = load_forecast(FORECAST_CSV, params, MOISTURE_CSV)
    chosen = getattr(planners, demo["planner"])
    cut_chances = []  # one [field, hour] per replan, in the order run_season replans

    def planner(value, state, params):
        """The chosen planner, unchanged; on the way we note what the ensemble says."""
        # value_by_member is £/ha in each forecast member, 0 where that member can't cut
        cut_chances.append((state["value_by_member"] > 0).mean(axis=0))
        return chosen(value, state, params)

    result = run_season(weather, params, planner)

    # the same split as run_season: one member is the real weather, the others are the forecast
    member, n_hours = params["truth_member"], params["season_hours"]
    truth = {name: values[[member], :, :n_hours] for name, values in weather.items()}
    forecast = {name: np.delete(values, member, axis=0) for name, values in weather.items()}
    true_moisture = predict_moisture(start_moisture(truth, params), truth, params)[0]

    plans = [
        {**outlook(plan, forecast, true_moisture, params, demo), "cut_chance": cut_chance}
        for plan, cut_chance in zip(result["plans"], cut_chances)
    ]
    start = pd.Timestamp(params["forecast_start"], tz="UTC")
    times = pd.date_range(start, periods=n_hours + 1, freq="h").tz_convert(demo["time_zone"])
    n_fields = len(params["fields"])
    return {
        "result": result,
        "plans": plans,
        "true_moisture_pct": true_moisture,
        "true_rain_mm": truth["rain_mm"][0],
        "true_humidity_pct": truth["humidity_pct"][0],
        "standing_ha": standing_ha(result, params),
        "doing": activities(result["cut_ha"], result["driving"], result["place"], n_fields),
        "times": times,
        "n_members": forecast["rain_mm"].shape[0],
    }


def outlook(plan, forecast, true_moisture, params, demo):
    """Add to one plan the forecast its planner saw: moisture and humidity spread, chance of rain.

    plan:          {"hour", "value" [field, hour], "schedule" [machine, hour]} from run_season
    forecast:      {name: [member, field, hour]} the members the planner sees, from season hour 0
    true_moisture: [field, hour] the moisture the sensor reads
    returns: plan plus "moisture_pct" and "humidity_pct" [band, field, hour], "rain_chance"
             [field, hour]
    """
    hour = plan["hour"]
    n_plan = plan["value"].shape[1]  # shorter than plan_hours near the end of the forecast
    # the plan starts from the latest reading, as in simulate.py
    reading = true_moisture[:, hour - hour % params["sensor_every_hours"]]  # [field] %
    upcoming = {name: values[:, :, hour : hour + n_plan] for name, values in forecast.items()}
    moisture = predict_moisture(reading, upcoming, params)  # [member, field, hour] %
    rain_chance = (upcoming["rain_mm"] > params["rain_limit_mm"]).mean(axis=0)  # [field, hour]
    return {
        **plan,
        "moisture_pct": np.percentile(moisture, demo["band_percentiles"], axis=0),
        "rain_chance": rain_chance,
        "humidity_pct": np.percentile(upcoming["humidity_pct"], demo["band_percentiles"], axis=0),
    }


def standing_ha(result, params):
    """Area still standing in each field at the start of each hour, and at the end.

    returns: [field, hour + 1] ha
    """
    area = np.array([field["area_ha"] for field in params["fields"]], dtype=float)  # [field]
    n_machines, n_hours = result["cut_ha"].shape
    cut = np.zeros((len(area), n_hours))  # [field, hour] ha cut by all machines
    for m in range(n_machines):
        hours = np.flatnonzero(result["cut_ha"][m] > 0)
        cut[result["harvesting"][m, hours], hours] += result["cut_ha"][m, hours]
    cut_so_far = np.concatenate([np.zeros((len(area), 1)), np.cumsum(cut, axis=1)], axis=1)
    return area[:, None] - cut_so_far
