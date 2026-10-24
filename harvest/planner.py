"""The planner: which field should each machine work on in each hour?

The planner only says where machines should be. simulate.py handles driving and harvesting.
"""

import numpy as np

WAIT = -1


def plan(value, state, params):
    """Greedy plan: each machine finishes its field, then moves to the free field worth the most.

    value:   [field, hour]    expected £/ha (from value.field_values)
    state:   {"remaining_ha": [field], "machine_at": [machine]}
             machine_at is a field index, or the number of fields for the depot
    params:  settings from params.yaml
    returns: [machine, hour]  field index each machine should work on, or WAIT (-1)
    """
    n_fields, n_hours = value.shape
    machines = params["machines"]
    remaining = state["remaining_ha"].copy()  # area we expect is still standing
    target = list(state["machine_at"])
    schedule = np.full((len(machines), n_hours), WAIT)

    for hour in range(n_hours):
        for m, machine in enumerate(machines):
            if target[m] == WAIT or target[m] == n_fields or remaining[target[m]] <= 0:
                free = [f for f in range(n_fields) if remaining[f] > 0 and f not in target]
                target[m] = free[np.argmax(value[free, hour])] if free else WAIT
            if target[m] != WAIT:
                schedule[m, hour] = target[m]
                if value[target[m], hour] > 0:
                    remaining[target[m]] -= machine["ha_per_hour"]
    return schedule
