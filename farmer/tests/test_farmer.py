"""Tests for the farmer site's Python side. No internet; no web server needed.

uv run pytest farmer/tests -q
"""

import json

import numpy as np

from farmer import source


def test_field_status_from_when_it_can_be_cut():
    soon = 3
    assert source.field_status(0, np.array([True]), soon) == "done"  # nothing left standing
    assert source.field_status(5, np.array([True, False]), soon) == "ready"
    assert source.field_status(5, np.array([False, False, True, True]), soon) == "soon"
    assert source.field_status(5, np.array([False, False, False, True]), soon) == "wait"  # too late


def test_farm_and_season_are_plain_json_and_consistent():
    farm = source.farm()
    season = source.season()
    json.dumps(farm)  # what the browser gets must be plain JSON
    json.dumps(season)

    n_fields, n_hours = len(farm["fields"]), farm["hours"]
    assert len(season["status"]) == n_fields and len(season["status"][0]) == n_hours
    assert len(season["labels"]) == n_hours + 1
    assert farm["season_start_utc"].endswith("Z")
    for f in range(n_fields):
        for hour in range(n_hours):
            status = season["status"][f][hour]
            assert status in {"ready", "soon", "wait", "done"}
            assert (status == "done") == (season["cut_pct"][f][hour] >= 100)


def test_totals_only_go_up():
    season = source.season()
    assert (np.diff(season["harvested_ha"]) >= -1e-9).all()
    assert (np.diff(season["earned_gbp"]) >= -1e-9).all()
