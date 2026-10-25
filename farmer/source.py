"""What the farmer site shows, in farmer terms, from the simulated season.

The only file in farmer/ that imports the rest of the repo: it reads the season the control panel
in webapp/ already works out (webapp.demo_state, read-only) and turns the model's numbers into
what a farmer needs: each field Ready / Soon / Wait / Done, its best time, its grain moisture,
and what each combine is doing and does next. The algorithm itself stays out of sight.
"""

from functools import cache
from pathlib import Path

import numpy as np
import yaml

from webapp import demo_state

FARMER = Path(__file__).parent


@cache
def settings():
    """farmer/site.yaml"""
    return yaml.safe_load((FARMER / "site.yaml").read_text(encoding="utf-8"))


@cache
def farm():
    """The farm: what doesn't change through the season."""
    base = demo_state.farm()
    plan = demo_state.plan()
    params, _, _ = demo_state.season()
    site = settings()
    corners = np.concatenate([np.array(field["outline"]) for field in base["fields"]])  # [lat, lng]
    return {
        "name": site["farm_name"],
        "place": site["place"],
        "fields": base["fields"],
        "yard": base["yard"],
        "machines": base["machines"],
        "centre": corners.mean(axis=0).round(5).tolist(),  # [lat, lng]
        "map": base["map"],
        "season_start_utc": params["forecast_start"] + "Z",  # params.yaml times are UTC
        "hours": plan["hours"],
        "steps_per_hour": plan["steps_per_hour"],
        "site": {key: value for key, value in site.items() if key != "farm_name"},
    }


@cache
def season():
    """Everything that changes hour by hour, worked out once.

    returns: {
        "labels":       [hour + 1] "Sun 25 Oct 14:00"
        "status":       [field][hour] "ready" | "soon" | "wait" | "done"
        "moisture_pct": [field][hour] grain moisture the plan expects (middle of the forecasts)
        "best":         [field][hour] best hour still to come, "now", or None if none
        "cut_pct":      [field][hour + 1] share of the field cut, %
        "doing":        [hour][machine] "Cutting Long Ground" ...
        "next":         [hour][machine] "Brook Furlong, Sun 09:00" ...
        "activity", "place": [machine][hour], "tracks": [machine][frame][lat, lng]
        "harvested_ha": [hour + 1], "earned_gbp": [hour + 1] totals so far
    }
    """
    plan = demo_state.plan()
    farm_ = farm()
    site = settings()
    n_hours, n_fields = plan["hours"], len(farm_["fields"])
    area = np.array([field["area_ha"] for field in farm_["fields"]], dtype=float)
    standing = np.array(plan["standing_ha"])  # [field, hour + 1] ha

    status = np.full((n_fields, n_hours), "wait", dtype=object)
    moisture = np.zeros((n_fields, n_hours))
    best = np.full((n_fields, n_hours), None, dtype=object)
    for hour in range(n_hours):
        p = [p for p in plan["plans"] if p["hour"] <= hour][-1]  # the plan in force
        column = hour - p["hour"]
        value = np.array(p["value_gbp_per_ha"])[:, column:]  # [field, hour from now] £/ha
        cuttable = (value > 0) & (np.array(p["cut_chance"])[:, column:] >= site["ready_chance"])
        moisture[:, hour] = np.array(p["moisture_pct"][1])[:, column]
        for f in range(n_fields):
            status[f, hour] = field_status(standing[f, hour], cuttable[f], site["soon_hours"])
            if standing[f, hour] > 0 and value[f].max() > 0:
                j = int(np.argmax(value[f]))
                best[f, hour] = "now" if j == 0 else short_label(plan["labels"][hour + j])

    return {
        "labels": plan["labels"],
        "status": status.tolist(),
        "moisture_pct": np.round(moisture, 1).tolist(),
        "best": best.tolist(),
        "cut_pct": np.round(100 * (1 - standing / area[:, None])).tolist(),
        "doing": [[card["headline"] for card in cards] for cards in plan["cards"]],
        "next": [[card["next"] for card in cards] for cards in plan["cards"]],
        "activity": plan["activity"],
        "place": plan["place"],
        "tracks": plan["tracks"],
        "harvested_ha": np.round(area.sum() - standing.sum(axis=0), 1).tolist(),
        "earned_gbp": np.concatenate([[0], np.cumsum(plan["earned_gbp"])]).round().tolist(),
        "limits": plan["limits"],
    }


def field_status(standing_ha, cuttable, soon_hours):
    """ "done", "ready" (cuttable now), "soon" (cuttable within soon_hours) or "wait".

    cuttable: [hour from now] bool, worth cutting in enough forecasts
    """
    if standing_ha <= 0:
        return "done"
    if cuttable[0]:
        return "ready"
    if cuttable[:soon_hours].any():
        return "soon"
    return "wait"


def short_label(label):
    """ "Sun 25 Oct 14:00" -> "Sun 14:00"."""
    return f"{label[:3]} {label[-5:]}"
