"""The planner: which field should each machine work on in each hour?

The planner only says where machines should be. simulate.py handles driving and harvesting.
"""

import numpy as np

WAIT = -1


def plan_vgreedy(value, state, params):
    """greedy by assigning free machine immediately to the field with highest current expected
    value. no future planning nor wait etc

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


def plan_urgencygreedy(value, state, params):
    """
    greedy by immediately assigning machines to most urgently needing harvesting by value
    look-ahead.

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
    schedule = np.full((len(machines), n_hours), WAIT)  # wait by default

    for hour in range(n_hours):
        for m, machine in enumerate(machines):
            if (
                target[m] == WAIT or target[m] == n_fields or remaining[target[m]] <= 0
            ):  # i.e. waiting, depot or finished: can choose next action
                free = [f for f in range(n_fields) if remaining[f] > 0 and f not in target]
                if not free:
                    target[m] = WAIT
                else:
                    best_later = value[free, hour + 1 :].max(
                        axis=1, initial=0
                    )  # max value from now to horizon
                    urgency = value[free, hour] - best_later
                    if urgency.max() > 0:
                        # 1. some field is at its peak: cut the one that loses the most by waiting
                        target[m] = free[np.argmax(urgency)]
                    else:
                        # not sure what to do here
                        target[m] = WAIT
                        # every field gets better later: plain greedy on today's value
                        # target[m] = free[np.argmax(value[free, hour])]

            if target[m] != WAIT:
                schedule[m, hour] = target[m]
                if value[target[m], hour] > 0:
                    remaining[target[m]] -= machine["ha_per_hour"]

    return schedule


def plan_urgencygreedy_withlookahead(value, state, params):
    """
    greedy by immediately assigning machines to most urgently needing harvesting by value
    look-ahead. takes value now as average of value now and value at how long it would take to
    harvest that field in the future

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
    schedule = np.full((len(machines), n_hours), WAIT)  # wait by default

    for hour in range(n_hours):
        for m, machine in enumerate(machines):
            if (
                target[m] == WAIT or target[m] == n_fields or remaining[target[m]] <= 0
            ):  # i.e. waiting, depot or finished: can choose next action
                free = [f for f in range(n_fields) if remaining[f] > 0 and f not in target]
                if not free:
                    target[m] = WAIT
                else:
                    # hours THIS machine needs to cut what's left of each free field (always >= 1)
                    hours_to_finish = np.ceil(remaining[free] / machine["ha_per_hour"]).astype(int)
                    # last hour it would be cutting, clipped to the plan horizon
                    finish_hour = np.minimum(hour + hours_to_finish - 1, n_hours - 1)
                    # a field is cut over several hours, so score it by the average of its
                    # value at the start and at the end of the job, not just the first hour
                    value_now = (value[free, hour] + value[free, finish_hour]) / 2
                    best_later = value[free, hour + 1 :].max(
                        axis=1, initial=0
                    )  # max value from now to horizon
                    urgency = value_now - best_later
                    if urgency.max() > 0:
                        # 1. some field is at its peak: cut the one that loses the most by waiting
                        target[m] = free[np.argmax(urgency)]
                    else:
                        # not sure what to do here
                        target[m] = WAIT
                        # every field gets better later: plain greedy on today's value
                        # target[m] = free[np.argmax(value[free, hour])]

            if target[m] != WAIT:
                schedule[m, hour] = target[m]
                if value[target[m], hour] > 0:
                    remaining[target[m]] -= machine["ha_per_hour"]

    return schedule


# Lagrangian relaxation, from Adelman & Mersereau (2008), "Relaxations of Weakly Coupled Stochastic
# Dynamic Programs", Operations Research 56(3): 712-727. Pages below are the journal's page numbers.
#
# The paper's problem (§2.1, p. 714): several subproblems that would be independent if it weren't
# for constraints linking their actions, sum_i D_i(s_i, a_i) <= b. Ours:
#   subproblem i      a field
#   state s_i         hectares still standing, and the hour
#   action a_i        hectares cut this hour
#   linking b         all fields together can't cut more per hour than the combines' total ha/hour
# The paper writes it for an infinite horizon with discounting (beta < 1) but says the method works
# in other settings too (§2.1, p. 714). Ours is the planning horizon with no discounting (beta = 1).
#
# Two simplifications, both because of what the planner is given:
# - No randomness. The planner only gets the value averaged over forecast members, so each field's
#   subproblem is deterministic. Uncertainty is handled by replanning when a new reading comes in.
# - One price per hour. The paper's lambda is the same in every state (§2.5, p. 717), because a
#   price that depends on the state stops the problem splitting by field (§4.3.2, p. 721). The hour
#   is the one part of the state that every field shares and knows, so a price per hour still
#   splits it, and is the natural finite-horizon version: one linking constraint per hour.
#
# Driving time isn't in the relaxation: it depends on where a combine is, not on a field, so it
# doesn't split by field. plan_lagrangian adds it back when it builds the schedule.


def field_alone(net_gbp_per_ha, remaining_ha, max_ha_per_hour):
    """Best plan for one field on its own, paying a price for every hectare of combine time it uses.

    This is the paper's subproblem, eq. (7) in Proposition 1 (p. 715): once the linking constraint
    has a price, each field solves its own dynamic program. Here the only state is the area left
    and nothing is random, so that program is just "cut in the hours with the best net value, at
    most one combine's worth per hour". Hectares may split across hours, so this is the LP
    relaxation of the subproblem and our bound matches the LP bound (Geoffrion's
    z_IP <= z_LD <= z_LP, eq. (1), p. 712).

    net_gbp_per_ha:  [hour]  value minus price, £/ha
    remaining_ha:    float   area still standing
    max_ha_per_hour: float   most this field can be cut in an hour (one combine per field)
    returns:         ([hour] ha cut, float £ earned net of the prices)
    """
    order = np.argsort(-net_gbp_per_ha, kind="stable")  # best hour first
    cut_ha = np.zeros(len(net_gbp_per_ha))
    # fill the best hours first, a combine's worth each, until the field is empty
    hours_before = np.arange(len(order))
    cut_ha[order] = np.clip(remaining_ha - max_ha_per_hour * hours_before, 0, max_ha_per_hour)
    cut_ha[net_gbp_per_ha <= 0] = 0  # never pay more for combine time than the grain is worth
    return cut_ha, float(cut_ha @ net_gbp_per_ha)


def machine_prices(value, remaining_ha, params):
    """What a hectare of combine time is worth in each hour, by Lagrangian relaxation (§2.3).

    Put a price on combine time, let every field plan alone at that price (field_alone), then move
    the prices until the fields' plans fit what the combines can cut.

    value:        [field, hour]  expected £/ha (from value.field_values)
    remaining_ha: [field]        area still standing
    params:       settings from params.yaml
    returns:      ([hour] price £/ha, float bound £)
                  No schedule can earn more than the bound from this value matrix, whatever the
                  prices (Proposition 2, p. 715). The lowest one found is returned.
    """
    n_fields, n_hours = value.shape
    rates = [machine["ha_per_hour"] for machine in params["machines"]]
    capacity_ha = sum(rates)  # b: the most all combines together can cut in one hour
    # one combine per field. Writing the constraint as tightly as possible matters: a loose version
    # of the same constraint can give a much worse bound and policy (§3.3 and §4.1, pp. 718-720)
    max_cut_ha = max(rates)

    price = np.zeros(n_hours)
    best_price, best_bound = price, np.inf
    for k in range(params["lagrangian_iterations"]):
        plans = [
            field_alone(value[f] - price, remaining_ha[f], max_cut_ha) for f in range(n_fields)
        ]
        demand_ha = sum(cut for cut, _ in plans)  # [hour] what the fields want cut
        # eq. (6) and (8), p. 715, with beta = 1: what the combines' time is worth at these
        # prices, plus what each field makes when it has to pay them
        bound = capacity_ha * price.sum() + sum(gbp for _, gbp in plans)
        if bound < best_bound:
            best_price, best_bound = price, bound

        excess_ha = demand_ha - capacity_ha  # [hour] asked for beyond what the combines can cut
        if (excess_ha <= 0).all() and np.allclose(price * excess_ha, 0):
            # the plans fit and spare hours cost nothing, so no price change can lower the bound
            # (Theorem 2 (ii), p. 719, applied to this relaxed problem)
            break
        # the bound (8) is convex and piecewise linear in the prices (p. 716), so take a
        # subgradient step: raise the price where too much is asked for, lower it (never below 0)
        # where combines are spare. Shrinking steps settle on the lowest bound.
        step = params["lagrangian_first_step_gbp_per_ha"] / (k + 1)
        price = np.maximum(0, price + step * excess_ha / np.linalg.norm(excess_ha))
    return best_price, best_bound


def plan_lagrangian(value, state, params):
    """Price combine time hour by hour, then send each combine where cutting now beats waiting.

    1. machine_prices: one price per hour for combine time, so that at those prices the fields'
       own plans fit what the combines can cut. Hours everyone wants (just before rain, or the
       driest hour) get expensive.
    2. Step through the hours like the other planners. A free combine goes to the field that gains
       the most from being cut now rather than at its own best later hours at those prices. That's
       the paper's one-step greedy policy (§3.2, p. 718). Waiting for a better hour now costs
       something if combines will be busy then, which the urgency planners can't see.

    value:   [field, hour]    expected £/ha (from value.field_values)
    state:   {"remaining_ha": [field], "machine_at": [machine]}
             machine_at is a field index, or the number of fields for the depot
    params:  settings from params.yaml
    returns: [machine, hour]  field index each machine should work on, or WAIT (-1)
    """
    n_fields, n_hours = value.shape
    machines = params["machines"]
    price, _ = machine_prices(value, state["remaining_ha"], params)
    max_cut_ha = max(machine["ha_per_hour"] for machine in machines)
    travel = np.ceil(np.array(params["travel_hours"])).astype(int)  # whole hours, as simulate.py
    margin = params["lagrangian_wait_margin_gbp_per_ha"]

    remaining = state["remaining_ha"].copy()  # area we expect is still standing
    at = list(state["machine_at"])  # field each machine is at or driving to, n_fields = depot
    ready = [0] * len(machines)  # plan hour each machine finishes driving
    schedule = np.full((len(machines), n_hours), WAIT)

    def later_gbp(field, hour, ha):
        """V_i(s_i), eq. (7): most `field` makes from `hour` on with `ha` left, at the prices."""
        return field_alone(value[field, hour:] - price[hour:], ha, max_cut_ha)[1]

    def gain_gbp_per_ha(m, field, hour):
        """How much better, per ha, to cut `field` as soon as machine m gets there than to leave it.

        The right-hand side of Bellman's equation with V_i plugged in (§3.2, p. 718): the cut now
        plus what the field makes later, minus what it makes later if left alone. The hour being
        planned isn't priced: there the real constraint holds, one combine per field. Driving
        time is charged at the prices, since the combine could have been cutting.
        """
        rate = machines[m]["ha_per_hour"]
        arrive = hour + travel[at[m], field]
        if arrive >= n_hours or value[field, arrive] <= 0:
            return -np.inf
        ha = min(rate, remaining[field])
        cut_now = ha * value[field, arrive] + later_gbp(field, arrive + 1, remaining[field] - ha)
        leave = later_gbp(field, arrive + 1, remaining[field])
        driving = rate * price[hour:arrive].sum()
        return (cut_now - leave - driving) / ha

    for hour in range(n_hours):
        for m, machine in enumerate(machines):
            if hour >= ready[m]:  # not driving, so free to choose
                taken = {at[o] for o in range(len(machines)) if o != m}  # one combine per field
                options = [f for f in range(n_fields) if remaining[f] > 0 and f not in taken]
                gains = {f: gain_gbp_per_ha(m, f, hour) for f in options}
                # at the best prices a field is often only just indifferent between now and later,
                # so cut now unless waiting is clearly better: later is less certain than now
                worth_it = {f: gain for f, gain in gains.items() if gain > -margin}
                if at[m] in worth_it:
                    choice = at[m]  # carry on here rather than pay to drive somewhere else
                else:
                    choice = max(worth_it, key=worth_it.get, default=WAIT)
                if choice == WAIT:
                    continue
                if choice != at[m]:
                    ready[m] = hour + travel[at[m], choice]
                    at[m] = choice

            schedule[m, hour] = at[m]
            if hour >= ready[m] and value[at[m], hour] > 0:
                remaining[at[m]] = max(0, remaining[at[m]] - machine["ha_per_hour"])

    return schedule
