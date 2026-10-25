# Greedy dispatch rules

`greedy.py` contains three myopic dispatch rules. The plan is built in a single forward pass over
the horizon. A combine is reassigned only when idle (unassigned, at the depot, or on a field whose
expected standing area has reached zero). It is then given the unoccupied field with the highest
priority index and stays there until that field is cleared, depleting area at its own rate in every
hour of positive value. Travel time is not represented in the plan; the simulator applies it. As a last step every rule passes its
plan through `send_idle_to_depot` (below).

With $V_{ft}$ the expected value (£/ha) of field $f$ in hour $t$ and $H$ the horizon, the rules
differ only in the index:

| Planner | Index for free field $f$ at hour $t$ | Assign when |
|---|---|---|
| `plan_vgreedy` | $V_{ft}$ | always |
| `plan_urgencygreedy` | $V_{ft} - \max_{t<s<H} V_{fs}$ | index $> 0$ |
| `plan_urgencygreedy_withlookahead` | $\tfrac12 (V_{ft} + V_{f,t+\tau_f-1}) - \max_{t<s<H} V_{fs}$ | index $> 0$ |

where $\tau_f$ is the number of hours the combine needs to clear field $f$ (the end hour truncated
at $H-1$). The urgency index is the loss from deferring a field past the current hour, in the
manner of slack-based priority rules. The look-ahead variant replaces the instantaneous value with
the mean of the values at the start and end of the job, since a field is cut over several hours.

None of the rules models contention between combines. Under the urgency rules a combine waits
whenever every free field is expected to improve later in the horizon, whether or not any combine
will be free at that time. With a receding horizon the expected peak can keep moving ahead, so
harvest may be postponed repeatedly. `plan_lagrangian` addresses this by pricing future combine
time.

## Waiting at the depot (`common.py`, shared with `plan_lagrangian`)

`send_idle_to_depot` replays the finished plan with travel times on the expected values
(`follow_plan`) and splits each combine's hours into cutting and not cutting. For each maximal
stretch without cutting it compares the running cost as planned, `idle_in_field_gbp_per_hour` per
hour standing in a field plus `drive_gbp_per_hour` per hour travelling, with the cost of driving to
the depot and back just in time for the next cutting hour. The stretch is rewritten if the saving
exceeds `depot_margin_gbp`, both drives fit, and no other combine holds the next field on the way
back. The cutting hours stay the same by construction, so in the model the pass only lowers running
cost. These are the costs `plan_mpc` optimises in its route DP. The expected value is zero only
when every forecast member rules out cutting, so the pass acts only on gaps the ensemble agrees on.
`depot_when_idle: false` turns it off.

## Reference

Panwalkar, S.S. and Iskander, W. (1977). A survey of scheduling rules. *Operations Research*
25(1): 45-62.
