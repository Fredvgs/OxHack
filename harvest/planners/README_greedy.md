# Greedy dispatch rules

`greedy.py` contains three myopic dispatch rules. The plan is built in a single forward pass over
the horizon. A combine is reassigned only when idle (unassigned, at the depot, or on a field whose
expected standing area has reached zero). It is then given the unoccupied field with the highest
priority index and stays there until that field is cleared, depleting area at its own rate in every
hour of positive value. Travel time is not represented in the plan; the simulator applies it.

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

## Reference

Panwalkar, S.S. and Iskander, W. (1977). A survey of scheduling rules. *Operations Research*
25(1): 45-62.
