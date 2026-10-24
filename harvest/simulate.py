"""The replanning loop: step through the season hour by hour.

Every `sensor_every_hours` a new grain moisture reading comes in. The value function is worked
out again from that reading and the planner makes a new plan. Machines follow the latest plan.
This file (not the planner) handles driving time and what actually gets harvested, using one
forecast member as the "true" weather.
"""

import numpy as np

from harvest.planner import WAIT, plan
from harvest.value import field_values, predict_moisture, start_moisture


def run_season(weather, params, planner=plan):
    """Simulate the season.

    weather: {name: [member, field, hour]}  from forecast.load_forecast
    params:  settings from params.yaml
    planner: function(value, state, params) -> schedule [machine, hour]
    returns: {
        "total_gbp":    float            money earned
        "earned_gbp":   [hour]           money earned in each hour
        "harvesting":   [machine, hour]  field each machine harvested, WAIT (-1) if none
        "remaining_ha": [field]          area left standing at the end
        "plans":        one per replan: {"hour", "value" [field, hour], "schedule" [machine, hour]}
    }
    """
    fields, machines = params["fields"], params["machines"]  # list of dicts: [field], [machine]
    names = [field["name"] for field in fields]  # [field] str
    n_hours = params["season_hours"]  # int

    # one forecast member plays the weather that really happens; the planner sees the others
    member = params["truth_member"]  # int
    truth = {name: values[[member]] for name, values in weather.items()}  # {name: [1, field, hour]}
    # {name: [member - 1, field, hour]}
    forecast = {name: np.delete(values, member, axis=0) for name, values in weather.items()}

    first_moisture = start_moisture(truth, params)  # [field] %
    true_moisture = predict_moisture(first_moisture, truth, params)[0]  # [field, hour]
    true_value = field_values(truth, first_moisture, params)  # [field, hour]
    travel = np.ceil(np.array(params["travel_hours"])).astype(int)  # [field+1, field+1] int hours

    remaining = np.array([field["area_ha"] for field in fields], dtype=float)  # [field] ha
    machine_at = np.array(  # [machine] int field index, len(fields) = depot
        [len(fields) if m["start"] == "depot" else names.index(m["start"]) for m in machines]
    )
    arrives_at = np.zeros(len(machines), dtype=int)  # [machine] hour a driving machine gets there
    earned = np.zeros(n_hours)  # [hour] £
    harvesting = np.full((len(machines), n_hours), WAIT)  # [machine, hour] field index or WAIT
    plans = []  # list of dicts, one per replan

    for hour in range(n_hours):
        if hour % params["sensor_every_hours"] == 0:
            # new sensor reading -> new field values -> new plan
            reading = true_moisture[:, hour]  # [field] %
            end = hour + params["plan_hours"]  # int
            # {name: [member - 1, field, plan_hour]}
            upcoming = {name: values[:, :, hour:end] for name, values in forecast.items()}
            # [field, plan_hour] £/ha
            value = field_values(upcoming, reading, params, first_hour=hour)
            state = {"remaining_ha": remaining.copy(), "machine_at": machine_at.copy()}
            schedule = planner(value, state, params)  # [machine, plan_hour] field index or WAIT
            plans.append({"hour": hour, "value": value, "schedule": schedule})
            plan_start = hour  # int, season hour of schedule column 0

        for m, machine in enumerate(machines):  # int, dict
            target = schedule[m, hour - plan_start]  # int field index or WAIT
            if hour >= arrives_at[m] and target != WAIT and target != machine_at[m]:
                arrives_at[m] = hour + travel[machine_at[m], target]  # start driving
                machine_at[m] = target
            arrived = hour >= arrives_at[m] and target == machine_at[m]  # bool
            if arrived and remaining[target] > 0 and true_value[target, hour] > 0:
                ha = min(remaining[target], machine["ha_per_hour"])  # float
                remaining[target] -= ha
                earned[hour] += ha * true_value[target, hour]
                harvesting[m, hour] = target

    return {
        "total_gbp": earned.sum(),
        "earned_gbp": earned,
        "harvesting": harvesting,
        "remaining_ha": remaining,
        "plans": plans,
    }
