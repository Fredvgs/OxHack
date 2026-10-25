"""Words for the pages: the combine cards, and what changed at each replan.

Every sentence is built from numbers the model worked out (see bridge.run_demo), so nothing on
the pages is made up. Moisture and rain come from the forecast the plan in force was made with.
"""

import numpy as np

from webapp.bridge import WAIT


def all_cards(season, params, demo, labels):
    """Cards for the whole season. labels: [field] names the farmer sees.

    returns: [hour][machine] card dicts (see card)
    """
    n_machines, n_hours = season["result"]["place"].shape
    return [
        [card(hour, m, season, params, demo, labels) for m in range(n_machines)]
        for hour in range(n_hours)
    ]


def plan_changes(season, params, demo, labels, machine_labels):
    """What each replan learned and what it changed, a few short sentences per plan.

    labels: [field] and machine_labels: [machine] names the farmer sees
    returns: [plan] list of sentences
    """
    plans, times = season["plans"], season["times"]
    stories = [[f"First plan, from the meter readings at {short(times[plans[0]['hour']])}."]]
    for before, now in zip(plans, plans[1:]):
        standing = np.flatnonzero(season["standing_ha"][:, now["hour"]] > 0)  # fields not finished
        if len(standing) == 0:
            stories.append(["Every field is cut."])
            continue
        lines = [reading_surprise(before, now, standing, season, params, labels)]
        lines.append(biggest_value_change(before, now, standing, demo, labels))
        moves = route_changes(before, now, labels, machine_labels)
        lines += moves or ["Routes unchanged."]
        stories.append([line for line in lines if line])
    return stories


def reading_surprise(before, now, standing, season, params, labels):
    """The meter reading furthest from what the last plan expected, e.g. "Meter in ... 19.5%"."""
    hour = now["hour"] - now["hour"] % params["sensor_every_hours"]  # the latest reading
    column = hour - before["hour"]  # the last plan's column for that hour
    if column < 0:
        return ""  # no new reading since the last plan
    reading = season["true_moisture_pct"][standing, hour]  # [standing field] %
    expected = before["moisture_pct"][1][standing, column]  # middle of the last plan's band
    i = np.argmax(np.abs(reading - expected))
    if abs(reading[i] - expected[i]) < 0.1:
        return "Meter readings matched the forecast."
    return (
        f"Meter in {labels[standing[i]]}: {reading[i]:.1f}%, "
        f"the last plan expected {expected[i]:.1f}%."
    )


def biggest_value_change(before, now, standing, demo, labels):
    """The field whose expected £/ha over the next compare_hours moved most since the last plan."""
    offset = now["hour"] - before["hour"]  # the last plan's column for now
    n = min(before["value"].shape[1] - offset, now["value"].shape[1], demo["compare_hours"])
    if n <= 0:
        return ""
    old = before["value"][standing, offset : offset + n].mean(axis=1)  # [standing field] £/ha
    new = now["value"][standing, :n].mean(axis=1)
    i = np.argmax(np.abs(new - old))
    change = new[i] - old[i]
    if abs(change) < 1:
        return f"Values over the next {n} h hardly moved."
    direction = "higher" if change > 0 else "lower"
    return f"{labels[standing[i]]}, next {n} h: £{abs(change):,.0f}/ha {direction} on average."


def route_changes(before, now, labels, machine_labels):
    """Combines whose next field is different in the new plan, as sentences."""
    offset = now["hour"] - before["hour"]
    lines = []
    for m, name in enumerate(machine_labels):
        old = next_field(before["schedule"][m, offset:], len(labels))
        new = next_field(now["schedule"][m], len(labels))
        if new is not None and new != old:
            instead = f", not {labels[old]}" if old is not None else ""
            lines.append(f"{name} now heads for {labels[new]}{instead}.")
    return lines


def next_field(row, n_fields):
    """The first field (not the yard, not wait) a schedule row sends the combine to, or None."""
    fields = [int(target) for target in row if 0 <= target < n_fields]
    return fields[0] if fields else None


def plan_in_force(plans, hour):
    """The latest plan made at or before this hour."""
    return [plan for plan in plans if plan["hour"] <= hour][-1]


def short(time):
    """Timestamp -> "Mon 14:00"."""
    return f"{time:%a %H:%M}"


def card(hour, m, season, params, demo, labels):
    """What combine m is doing in this hour and why.

    returns: {"status": "cutting" | "driving" | "waiting" | "yard", "headline": "Cutting Long
              Ground", "field": field index or None, "detail": "wheat · 40 ha · 62% cut",
              "why": [sentence], "next": sentence}
    """
    n_fields = len(params["fields"])
    where = int(season["result"]["place"][m, hour])  # field index, n_fields = the yard
    plan = plan_in_force(season["plans"], hour)
    column = hour - plan["hour"]  # the plan's column for this hour
    upcoming = next_move(plan["schedule"][m], column, where, plan["hour"], season, labels)
    driving = bool(season["doing"]["driving"][m, hour])

    if where == n_fields:
        if driving:
            return yard_card("driving", "Driving to the yard", [], upcoming)
        why = yard_reasons(plan["schedule"][m], hour, plan, season, labels)
        return yard_card("yard", "At the yard", why, upcoming)

    status = next(
        name for name in ("cutting", "driving", "waiting") if season["doing"][name][m, hour]
    )
    verb = {"cutting": "Cutting", "driving": "Driving to", "waiting": "Waiting in"}[status]
    return {
        "status": status,
        "headline": f"{verb} {labels[where]}",
        "field": where,
        "detail": field_detail(where, hour, season, params),
        "why": reasons(where, hour, status, plan, season, params, demo),
        "next": upcoming,
    }


def yard_card(status, headline, why, upcoming):
    return {
        "status": status,
        "headline": headline,
        "field": None,
        "detail": "",
        "why": why,
        "next": upcoming,
    }


def yard_reasons(row, hour, plan, season, labels):
    """Why a combine is parked: the best field right now, and what the plan is waiting for.

    row: [hour] the combine's schedule in the plan in force
    """
    column = hour - plan["hour"]
    value = plan["value"][:, column]  # [field] £/ha this hour
    standing = np.flatnonzero(season["standing_ha"][:, hour] > 0)  # fields not finished
    if len(standing) == 0:
        return ["Every field is cut."]
    if value[standing].max() <= 0:
        return ["No field can be cut this hour: too wet or raining."]
    best = standing[np.argmax(value[standing])]
    lines = [f"Best field this hour: {labels[best]}, £{value[best]:,.0f}/ha."]
    move = first_move(row, column, len(labels))
    if move is not None and move[0] < len(labels):
        target, j = move
        when = short(season["times"][plan["hour"] + j])
        lines.append(
            f"Plan holds it for {labels[target]}: £{plan['value'][target, j]:,.0f}/ha at {when}."
        )
    return lines


def field_detail(field, hour, season, params):
    """ "wheat · 40 ha · 62% cut" at the start of this hour."""
    info = params["fields"][field]
    cut_pct = 100 * (1 - season["standing_ha"][field, hour] / info["area_ha"])
    return f"{info['crop']} · {info['area_ha']:g} ha · {cut_pct:.0f}% cut"


def reasons(field, hour, status, plan, season, params, demo):
    """Why the combine is in this field: up to four short sentences."""
    column = hour - plan["hour"]
    lines = []
    if status == "waiting":
        lines.append(waiting_reason(field, hour, season, params))

    # moisture: the middle of the forecast band, which starts from the latest meter reading
    moisture = plan["moisture_pct"][1, :, column]  # [field] %
    standing = season["standing_ha"][:, hour] > 0  # [field] bool
    driest = standing[field] and moisture[field] <= moisture[standing].min()
    lines.append(
        f"Grain about {moisture[field]:.1f}%" + (", the driest field left." if driest else ".")
    )

    lines.append(rain_outlook(field, hour, plan, season, demo))
    lines.append(value_now_and_later(field, hour, plan, season, demo))
    return lines


def waiting_reason(field, hour, season, params):
    """Why a combine in a field isn't cutting, from the weather that really happened."""
    rain_mm = season["true_rain_mm"][field, hour]
    moisture = season["true_moisture_pct"][field, hour]
    if season["standing_ha"][field, hour] <= 0:
        return "Field finished."
    if rain_mm > params["rain_limit_mm"]:
        return f"Raining: {rain_mm:.1f} mm this hour."
    if moisture > params["max_harvest_moisture_pct"]:
        return f"Too wet to cut: {moisture:.1f}%, limit {params['max_harvest_moisture_pct']}%."
    return "Waiting here for a better hour, as planned."


def rain_outlook(field, hour, plan, season, demo):
    """ "Rain likely from Mon 17:00 (64% of forecasts)." or "No rain likely before Fri 06:00.\""""
    column = hour - plan["hour"]
    chance = plan["rain_chance"][field, column:]  # [hour from now] share of members
    likely = np.flatnonzero(chance * 100 >= demo["rain_chance_pct"])
    if len(likely) == 0:
        end = season["times"][
            min(plan["hour"] + plan["rain_chance"].shape[1], len(season["times"]) - 1)
        ]
        return f"No rain likely before {short(end)}."
    first = likely[0]
    when = "now" if first == 0 else f"from {short(season['times'][hour + first])}"
    return f"Rain likely {when} ({chance[first]:.0%} of forecasts)."


def value_now_and_later(field, hour, plan, season, demo):
    """Expected £/ha cutting this hour against compare_hours later, from the plan's value."""
    column = hour - plan["hour"]
    value = plan["value"][field]  # [hour] £/ha, averaged over forecast members
    later = column + demo["compare_hours"]
    if value[column] <= 0:
        return "Not worth cutting this hour."
    if later >= len(value):
        return f"£{value[column]:,.0f}/ha if cut now."
    when = short(season["times"][plan["hour"] + later])
    return f"£{value[column]:,.0f}/ha now, £{value[later]:,.0f}/ha if left until {when}."


def first_move(row, column, where):
    """The next time the plan sends this combine somewhere else.

    row: [hour] the combine's schedule in the plan in force; where: where it is now
    returns: (target, plan column), or None if the plan keeps it where it is
    """
    for j in range(column + 1, len(row)):
        if row[j] != WAIT and row[j] != where:
            return int(row[j]), j
    return None


def next_move(row, column, where, plan_hour, season, labels):
    """The next move as a sentence, e.g. "Barn Field, Mon 15:00"."""
    move = first_move(row, column, where)
    if move is None:
        return "No change planned."
    target, j = move
    place = "Yard" if target == len(labels) else labels[target]
    return f"{place}, {short(season['times'][plan_hour + j])}"
