"""Where each combine is on the map, worked out from the simulated season.

The model only knows which field a combine is in. On the map, a combine cuts a field in passes up
and down, parallel to the field's longest side, and how far along those passes it has got is the
share of the field cut so far. So the map always agrees with the % cut on the panel.

Positions are in metres east and north of the yard; to_lonlat turns them into map coordinates.
"""

import numpy as np

METRES_PER_DEGREE = 111_320  # one degree of latitude; longitude degrees shrink by cos(latitude)


def to_metres(lonlat, origin):
    """[point, 2] lon/lat degrees -> [point, 2] metres east and north of origin (lon, lat)."""
    lonlat = np.asarray(lonlat, dtype=float)
    east = (lonlat[:, 0] - origin[0]) * METRES_PER_DEGREE * np.cos(np.radians(origin[1]))
    north = (lonlat[:, 1] - origin[1]) * METRES_PER_DEGREE
    return np.column_stack([east, north])


def to_lonlat(xy, origin):
    """[..., 2] metres east and north of origin -> [..., 2] lon/lat. Undoes to_metres."""
    xy = np.asarray(xy, dtype=float)
    lon = origin[0] + xy[..., 0] / (METRES_PER_DEGREE * np.cos(np.radians(origin[1])))
    lat = origin[1] + xy[..., 1] / METRES_PER_DEGREE
    return np.stack([lon, lat], axis=-1)


def rotation(angle):
    """2x2 matrix turning points anticlockwise by angle (radians): points @ rotation(a).T."""
    return np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])


def passes(outline, width_m):
    """The path a combine drives to cut a field: passes up and down, parallel to its longest side.

    outline: [corner, 2] metres, the field boundary (first corner not repeated)
    width_m: distance between neighbouring passes
    returns: [point, 2] metres, in the order they are driven
    """
    sides = np.roll(outline, -1, axis=0) - outline  # [corner, 2]
    longest = sides[np.argmax(np.hypot(sides[:, 0], sides[:, 1]))]
    angle = np.arctan2(longest[1], longest[0])
    flat = outline @ rotation(-angle).T  # the longest side now runs along the x axis

    points = []
    for i, y in enumerate(np.arange(flat[:, 1].min() + width_m / 2, flat[:, 1].max(), width_m)):
        xs = crossings(flat, y)
        if len(xs) < 2:
            continue
        one_pass = [(min(xs), y), (max(xs), y)]  # outermost crossings, so odd shapes stay simple
        points += one_pass if i % 2 == 0 else one_pass[::-1]  # every other pass drives back
    return np.array(points) @ rotation(angle).T


def crossings(outline, y):
    """x where the horizontal line at y crosses the outline's sides. outline: [corner, 2]."""
    xs = []
    for (x1, y1), (x2, y2) in zip(outline, np.roll(outline, -1, axis=0)):
        if (y1 <= y < y2) or (y2 <= y < y1):
            xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    return xs


def distance_along(path):
    """[point] metres driven from the start of the path to each point."""
    steps = np.hypot(*np.diff(path, axis=0).T)
    return np.concatenate([[0.0], np.cumsum(steps)])


def point_along(path, distance, metres):
    """The point `metres` along the path (clipped to its ends). distance: from distance_along."""
    metres = np.clip(metres, 0, distance[-1])
    i = min(np.searchsorted(distance, metres, side="right") - 1, len(path) - 2)
    step = distance[i + 1] - distance[i]
    share = 0 if step == 0 else (metres - distance[i]) / step
    return path[i] + share * (path[i + 1] - path[i])


def combine_positions(
    place, driving, start_place, cut_share, paths, yard, steps, gap_m, yard_gap_m
):
    """Where each combine is, `steps` times an hour.

    place:       [machine, hour] field index it is in or driving to; n_fields = the yard
    driving:     [machine, hour] bool, on the road
    start_place: [machine] where each machine starts: field index or n_fields = the yard
    cut_share:   [field, hour + 1] share of each field cut (0-1) at the start of each hour
    paths:       list per field of [point, 2] metres, from passes
    yard:        [2] metres
    steps:       positions per hour
    gap_m:       how far behind the first combine a second one in the same field is drawn
    yard_gap_m:  how far apart combines park at the yard
    returns:     [machine, hour * steps + 1, 2] metres
    """
    n_machines, n_hours = place.shape
    n_fields = len(paths)
    distances = [distance_along(path) for path in paths]

    def cut_edge(field, time, rank):
        """Where the cutting has got to in a field at a time (hours), minus rank combine gaps."""
        hour = min(int(time), n_hours - 1)
        share = np.interp(time, [hour, hour + 1], cut_share[field, hour : hour + 2])
        metres = share * distances[field][-1] - rank * gap_m
        return point_along(paths[field], distances[field], metres)

    def spot(where, time, rank=0):
        if where == n_fields:
            return yard + [(rank + 1) * yard_gap_m, -yard_gap_m]  # in a row, clear of the label
        return cut_edge(where, time, rank)

    positions = np.zeros((n_machines, n_hours * steps + 1, 2))
    for m in range(n_machines):
        here = spot(start_place[m], 0)
        hour = 0
        while hour < n_hours:
            where = place[m, hour]
            if driving[m, hour]:
                # one trip lasts while it keeps driving to the same place
                arrive = hour
                while arrive < n_hours and driving[m, arrive] and place[m, arrive] == where:
                    arrive += 1
                goal = spot(where, arrive)
                n_steps = (arrive - hour) * steps
                for k in range(n_steps):
                    positions[m, hour * steps + k] = here + (goal - here) * k / n_steps
                here, hour = goal, arrive
                continue
            # in a field or at the yard: other combines in the same field are drawn behind
            sharing = [
                k for k in range(n_machines) if place[k, hour] == where and not driving[k, hour]
            ]
            rank = sharing.index(m)
            for k in range(steps):
                positions[m, hour * steps + k] = spot(where, hour + k / steps, rank)
            here = spot(where, hour + 1, rank)
            hour += 1
        positions[m, -1] = here
    return positions
