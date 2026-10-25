"""Tests for the web app's Python side. No internet; no web server needed.

uv run pytest webapp/tests -q
"""

import json

import numpy as np

from webapp import demo_state, export_static, tracks


def test_passes_cover_a_rectangle_along_its_long_side():
    rectangle = np.array([[0, 0], [100, 0], [100, 40], [0, 40]], dtype=float)  # 100 m x 40 m
    path = tracks.passes(rectangle, width_m=10)
    assert path.shape == (8, 2)  # 4 passes, each a start and an end
    assert np.allclose(path[:, 1], [5, 5, 15, 15, 25, 25, 35, 35])  # 10 m apart, inside the field
    assert np.allclose(path[:, 0], [0, 100, 100, 0, 0, 100, 100, 0])  # every other pass drives back


def test_passes_stop_at_the_edge_of_an_odd_shaped_field():
    # 100 m x 40 m with a notch 40 m wide cut into the top, down to 20 m
    u_shape = np.array(
        [[0, 0], [100, 0], [100, 40], [70, 40], [70, 20], [30, 20], [30, 40], [0, 40]], dtype=float
    )
    path = tracks.passes(u_shape, width_m=10)
    assert path.shape == (12, 2)  # 2 passes right across, then 2 broken by the notch
    in_notch = (path[:, 0] > 30) & (path[:, 0] < 70) & (path[:, 1] > 20)
    assert not in_notch.any()


def test_route_follows_field_edges_and_hops_the_gap():
    a = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=float)
    b = np.array([[120, -20], [220, -20], [220, 40], [120, 40]], dtype=float)  # 28 m away
    network = tracks.edge_network([a, b], hop_m=50, off_edge_factor=3)
    way = tracks.route(network, np.array([-5, -5]), np.array([225, -25]))
    # along a's bottom edge, across the gap where the fields come closest, along b's bottom edge
    expected = [[-5, -5], [0, 0], [100, 0], [120, -20], [220, -20], [225, -25]]
    assert np.allclose(way, expected)


def test_point_along_a_path():
    path = np.array([[0, 0], [10, 0], [10, 10]], dtype=float)
    distance = tracks.distance_along(path)
    assert np.allclose(distance, [0, 10, 20])
    assert np.allclose(tracks.point_along(path, distance, 15), [10, 5])
    assert np.allclose(tracks.point_along(path, distance, 99), [10, 10])  # clipped to the end


def test_metres_and_lonlat_round_trip():
    origin = np.array([-1.11, 51.72])
    lonlat = np.array([[-1.10, 51.73], [-1.12, 51.71]])
    back = tracks.to_lonlat(tracks.to_metres(lonlat, origin), origin)
    assert np.allclose(back, lonlat)


def test_combine_drives_from_the_yard_then_follows_the_cutting():
    path = np.array([[100, 0], [200, 0]], dtype=float)  # one field, one pass
    place = np.array([[0, 0, 0]])  # [machine, hour]: field 0 throughout (1 = the yard)
    driving = np.array([[True, False, False]])  # an hour on the road, then cutting
    cut_share = np.array([[0, 0, 0.5, 1.0]])  # [field, hour + 1]

    def straight(start, end):  # no field edges here: drive straight
        return np.array([start, end])

    positions = tracks.combine_positions(
        place, driving, [1], cut_share, [path], straight, np.zeros(2), 2, gap_m=0, yard_gap_m=10
    )
    assert positions.shape == (1, 7, 2)  # 3 hours x 2 steps + the end
    assert np.allclose(positions[0, 0], [10, -10])  # parked at the yard
    assert np.allclose(positions[0, 2], [100, 0])  # arrived at the start of the field
    assert np.allclose(positions[0, 4], [150, 0])  # half cut
    assert np.allclose(positions[0, -1], [200, 0])  # all cut


def test_demo_json_is_complete_and_consistent():
    farm = demo_state.farm()
    plan = demo_state.plan()
    json.dumps(farm)  # what the browser gets must be plain JSON
    json.dumps(plan)

    n_machines, n_fields, n_hours = len(farm["machines"]), len(farm["fields"]), plan["hours"]
    assert len(plan["tracks"]) == n_machines
    assert len(plan["tracks"][0]) == n_hours * plan["steps_per_hour"] + 1
    assert len(plan["cards"]) == n_hours and len(plan["cards"][0]) == n_machines
    assert len(plan["standing_ha"]) == n_fields and len(plan["standing_ha"][0]) == n_hours + 1
    assert len(plan["labels"]) == n_hours + 1

    standing = np.array(plan["standing_ha"])
    assert (standing >= -1e-9).all()
    assert (np.diff(standing, axis=1) <= 1e-9).all()  # fields only ever get cut, never uncut


def test_every_plan_has_a_value_map_and_says_what_changed():
    plan = demo_state.plan()
    n_fields = len(demo_state.farm()["fields"])
    for p in plan["plans"]:
        value = np.array(p["value_gbp_per_ha"])  # [field, hour]
        chance = np.array(p["cut_chance"])  # [field, hour]
        assert value.shape == chance.shape and value.shape[0] == n_fields
        assert (value >= 0).all() and value.max() <= plan["value_max_gbp_per_ha"]
        assert ((chance >= 0) & (chance <= 1)).all()
        assert ((value > 0) == (chance > 0)).all()  # worth something only if some forecast can cut
        assert p["change"]  # at least one sentence


def test_cards_agree_with_what_the_combines_do():
    plan = demo_state.plan()
    for hour, cards in enumerate(plan["cards"]):
        for m, card in enumerate(cards):
            assert card["status"] == plan["activity"][m][hour]
            assert card["next"]  # always says what happens next


def test_export_saves_both_answers_for_a_static_host(tmp_path):
    farm_path, season_path = export_static.export(tmp_path)
    farm = json.loads(farm_path.read_text(encoding="utf-8"))
    season = json.loads(season_path.read_text(encoding="utf-8"))
    assert farm["saved"] and farm["season_start_utc"] and farm["hours"] > 0
    assert season
