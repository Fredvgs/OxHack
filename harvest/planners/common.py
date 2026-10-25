"""Shared by every planner."""

import numpy as np

WAIT = -1  # schedule entry: stay where you are this hour


def follow_plan(schedule, value, state, params):
    """Play a schedule forward with the rules of simulate.py, on the expected values.

    Driving takes travel_hours (rounded up to whole hours), a machine already driving finishes the
    trip before it follows a new entry, WAIT means stay put without cutting, and a machine cuts
    only where there's grain left and the value is above 0.

    schedule: [machine, hour]  field index, number of fields for the depot, or WAIT
    value:    [field, hour]    expected £/ha
    state:    {"remaining_ha": [field], "machine_at": [machine]}
    returns:  {"place":   [machine, hour] int   where it is or is driving to
               "driving": [machine, hour] bool  on the road
               "cutting": [machine, hour] bool  cutting grain}
    """
    n_fields, n_hours = value.shape
    travel = np.ceil(np.array(params["travel_hours"])).astype(int)  # whole hours, as simulate.py
    remaining = np.array(state["remaining_ha"], dtype=float)  # area we expect is still standing
    at = list(state["machine_at"])  # place each machine is at or driving to
    arrives = [0] * len(at)  # hour each machine gets there
    place = np.zeros(schedule.shape, dtype=int)
    driving = np.zeros(schedule.shape, dtype=bool)
    cutting = np.zeros(schedule.shape, dtype=bool)

    for hour in range(n_hours):
        for m, machine in enumerate(params["machines"]):
            target = schedule[m, hour]
            if hour >= arrives[m] and target != WAIT and target != at[m]:  # set off
                arrives[m] = hour + travel[at[m], target]
                at[m] = target
            place[m, hour] = at[m]
            driving[m, hour] = hour < arrives[m]
            field = at[m]
            # in a field, arrived, and not told to WAIT (WAIT means don't cut, as in simulate.py)
            ready_to_cut = field < n_fields and not driving[m, hour] and target == field
            if ready_to_cut and remaining[field] > 0 and value[field, hour] > 0:
                remaining[field] -= min(remaining[field], machine["ha_per_hour"])
                cutting[m, hour] = True
    return {"place": place, "driving": driving, "cutting": cutting}


def idle_stretches(cutting):
    """Every run of hours with no cutting, as (first hour, hour after the last).

    cutting: [hour] bool
    returns: list of (start, end): no cutting in hours start to end - 1
    """
    stretches = []
    start = None
    for hour, cut in enumerate(cutting):
        if not cut and start is None:
            start = hour  # a stretch begins
        if cut and start is not None:
            stretches.append((start, hour))  # cutting again: the stretch ends
            start = None
    if start is not None:
        stretches.append((start, len(cutting)))  # still not cutting when the plan ends
    return stretches


def send_idle_to_depot(schedule, value, state, params):
    """Wait at the depot instead of in a field, when that's cheaper. Run last by every planner
    except plan_mpc, which already weighs the same costs in its own model.

    For each stretch of hours in which a combine doesn't cut (waiting, driving, or in a field too
    wet to cut), compare:
    - as planned: idle_in_field_gbp_per_hour for each hour stood in a field, and
      drive_gbp_per_hour for each hour on the road;
    - via the depot: drive there, wait for free, and drive to the field it cuts next, getting there
      by the hour the plan starts cutting it.
    The stretch is rewritten only if the depot saves more than depot_margin_gbp, there's time for
    both drives, and no other combine holds that field on the way back. Every other entry is left
    as it was, so the hours each combine cuts don't change.

    value is the average over forecast members, so it's 0 only when every member says the field
    can't be cut: combines go home only for gaps the forecast is sure about. Being away when the
    field turns out dry costs far more than an idle hour.

    schedule: [machine, hour]  field index, number of fields for the depot, or WAIT
    value:    [field, hour]    expected £/ha (from value.field_values)
    state:    {"remaining_ha": [field], "machine_at": [machine]}
    params:   settings from params.yaml
    returns:  [machine, hour]  the same schedule, with depot visits added
    """
    if not params["depot_when_idle"]:
        return schedule
    n_fields, n_hours = value.shape
    depot = n_fields
    travel = np.ceil(np.array(params["travel_hours"])).astype(int)  # whole hours, as simulate.py
    idle_gbp = params["idle_in_field_gbp_per_hour"]
    drive_gbp = params["drive_gbp_per_hour"]
    plan = follow_plan(schedule, value, state, params)
    new_schedule = schedule.copy()

    for m in range(len(schedule)):
        others = np.delete(plan["place"], m, axis=0)  # [other machine, hour]
        for start, end in idle_stretches(plan["cutting"][m]):
            # where it is when the stretch starts (it was cutting there the hour before), and the
            # field it cuts next, or None if it doesn't cut again in this plan
            here = state["machine_at"][m] if start == 0 else plan["place"][m, start - 1]
            next_field = plan["place"][m, end] if end < n_hours else None

            # 1. what the stretch costs as planned
            driving = plan["driving"][m, start:end]
            in_field = plan["place"][m, start:end] < depot
            planned_gbp = idle_gbp * (in_field & ~driving).sum() + drive_gbp * driving.sum()

            # 2. what it costs via the depot, leaving there in time to be cutting at `end`
            out_hours = travel[here, depot]
            back_hours = 0 if next_field is None else travel[depot, next_field]
            depot_gbp = drive_gbp * (out_hours + back_hours)
            leave = end - back_hours

            # 3. rewrite the stretch only if it's clearly cheaper and it all fits
            cheaper = depot_gbp + params["depot_margin_gbp"] < planned_gbp
            fits = start + out_hours <= leave
            field_free = next_field is None or not (others[:, leave:end] == next_field).any()
            if cheaper and fits and field_free:
                new_schedule[m, start:leave] = depot
                if next_field is not None:
                    new_schedule[m, leave:end] = next_field
    return new_schedule
