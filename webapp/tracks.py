"""Where each combine is on the map, worked out from the simulated season.

The model only knows which field a combine is in. On the map, a combine cuts a field in passes up
and down, parallel to the field's longest side, and how far along those passes it has got is the
share of the field cut so far. So the map always agrees with the % cut on the pages. Between
fields, and between the parcels of one field, it drives along the field edges (edge_network).

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
        xs = sorted(crossings(flat, y))
        # inside the field between the 1st and 2nd crossing, the 3rd and 4th...: a pass across an
        # odd-shaped field stops at its edge and picks up again on the far side of the gap
        one_pass = [(x, y) for x in xs[: len(xs) // 2 * 2]]
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


def edge_network(outlines, hop_m, off_edge_factor):
    """The field edges as the combines' roads, so they drive round fields rather than across them.

    A route walks round the edge of each parcel it passes and hops the gap to the next one where
    the two come closest. Gaps up to hop_m (lanes, hedges, tracks between neighbouring fields)
    count as their length; longer hops across country count off_edge_factor times it, so routes
    keep to field edges where they can.
    outlines: [parcel] of [corner, 2] metres, every parcel on the farm (first corner not repeated)
    returns: {"corners": [corner, 2] every parcel's corners, one parcel after another
              "first":   [parcel + 1] where each parcel's corners start in corners
              "parcel":  [corner] which parcel each corner is on
              "exit":    [parcel, parcel] the corner of the first parcel nearest the second
              "next":    [parcel, parcel] the next parcel on the way from the first to the second}
    """
    sizes = [len(outline) for outline in outlines]
    corners = np.concatenate(outlines)
    first = np.cumsum([0] + sizes)
    parcel = np.repeat(np.arange(len(outlines)), sizes)
    n = len(outlines)
    gap, exit_corner = np.zeros((n, n)), np.zeros((n, n), dtype=int)
    for i in range(n):
        own = corners[first[i] : first[i + 1]]
        apart = np.linalg.norm(own[:, None, :] - corners[None, :, :], axis=2)  # [own, all]
        nearest = apart.min(axis=0)  # [corner] how far each corner is from parcel i
        # each parcel's corner nearest parcel i: sorted by parcel, then distance, its first one
        theirs = np.lexsort((nearest, parcel))[first[:-1]]  # [parcel]
        gap[i] = nearest[theirs]
        exit_corner[:, i] = theirs
        exit_corner[i] = first[i] + apart[:, theirs].argmin(axis=0)
    centres = np.array([outline.mean(axis=0) for outline in outlines])
    cost = np.linalg.norm(centres[:, None, :] - centres[None, :, :], axis=2)
    cost = np.where(gap <= hop_m, cost, cost * off_edge_factor)
    # the cheapest way between every pair of parcels (Floyd-Warshall), remembering its first step
    step = np.tile(np.arange(n), (n, 1))
    for k in range(n):
        through = cost[:, [k]] + cost[[k], :]
        better = through < cost
        cost = np.where(better, through, cost)
        step = np.where(better, step[:, [k]], step)
    return {"corners": corners, "first": first, "parcel": parcel, "exit": exit_corner, "next": step}


def route(network, start, end):
    """The way from start to end along the field edges (edge_network).

    start, end: [2] metres, anywhere; they join the edges at the nearest corner
    returns: [point, 2] metres, from start to end
    """
    corners, parcel = network["corners"], network["parcel"]
    here = np.argmin(np.linalg.norm(corners - start, axis=1))
    goal = np.argmin(np.linalg.norm(corners - end, axis=1))
    pieces = [np.asarray(start, dtype=float)[None]]
    while parcel[here] != parcel[goal]:
        a = parcel[here]
        b = network["next"][a, parcel[goal]]
        pieces.append(edge_walk(network, here, network["exit"][a, b]))
        here = network["exit"][b, a]  # across the gap to the next parcel
    pieces += [edge_walk(network, here, goal), np.asarray(end, dtype=float)[None]]
    return np.concatenate(pieces)


def edge_walk(network, start, end):
    """Corners from one corner of a parcel to another, the shorter way round: [point, 2] metres.

    start, end: corner indices in network["corners"], on the same parcel
    """
    first, last = network["first"][network["parcel"][start] + np.array([0, 1])]
    ring = network["corners"][first:last]
    n, i, j = len(ring), start - first, end - first
    forward = ring[(i + np.arange((j - i) % n + 1)) % n]
    backward = ring[(i - np.arange((i - j) % n + 1)) % n]
    return min(forward, backward, key=lambda way: distance_along(way)[-1])


def combine_positions(
    place, driving, start_place, cut_share, paths, route, yard, steps, gap_m, yard_gap_m
):
    """Where each combine is, `steps` times an hour.

    place:       [machine, hour] field index it is in or driving to; n_fields = the yard
    driving:     [machine, hour] bool, on the road
    start_place: [machine] where each machine starts: field index or n_fields = the yard
    cut_share:   [field, hour + 1] share of each field cut (0-1) at the start of each hour
    paths:       list per field of [point, 2] metres, from passes
    route:       route(start, end) -> [point, 2] metres, the way a combine drives between them
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
                road = route(here, goal)
                along = distance_along(road)
                n_steps = (arrive - hour) * steps
                for k in range(n_steps):  # at an even speed along the way
                    positions[m, hour * steps + k] = point_along(
                        road, along, along[-1] * k / n_steps
                    )
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
