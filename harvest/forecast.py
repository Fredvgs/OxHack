"""Load the prediction data (the weather forecast) from a CSV. The format is in data/README.md.

To use a different prediction format, rewrite load_forecast() so it returns the same thing.
"""

import numpy as np
import pandas as pd

COLUMNS = ["rain_mm", "humidity_pct"]


def sort_by_field(table, params):
    """Keep the fields in params.yaml and sort rows by member, field (params.yaml order), hour.

    returns: (sorted table, shape (member, field, hour) to reshape one column into)
    """
    names = [field["name"] for field in params["fields"]]
    table = table[table["field"].isin(names)].copy()
    table["field_index"] = table["field"].map(names.index)
    table = table.sort_values(["member", "field_index", "hour"], ignore_index=True)
    shape = (table["member"].nunique(), len(names), table["hour"].nunique())
    return table, shape


def load_forecast(path, params, moisture_path=None):
    """Read the forecast CSV, and optionally the grain moisture CSV made from it.

    path:          the forecast CSV file
    params:        settings from params.yaml (the field order comes from params["fields"])
    moisture_path: outputs/moisture_forecast.csv (from moisture_forecast.py), or None
    returns: {"rain_mm": [member, field, hour], "humidity_pct": [member, field, hour]},
             plus "moisture_pct": [member, field, hour] when moisture_path is given
    """
    table, shape = sort_by_field(pd.read_csv(path), params)
    weather = {column: table[column].to_numpy(dtype=float).reshape(shape) for column in COLUMNS}
    if moisture_path is not None:
        weather["moisture_pct"] = load_moisture(moisture_path, params)
        # an old moisture CSV from a different forecast would silently give the wrong values
        if weather["moisture_pct"].shape != shape:
            raise ValueError(
                f"{moisture_path} does not match {path}: rerun `uv run python moisture_forecast.py`"
            )
    return weather


def load_moisture(path, params):
    """Read the grain moisture CSV written by moisture_forecast.py (outputs/moisture_forecast.csv).

    The CSV has one column per crop ("wheat_moisture_pct", ...); every field gets the column of
    the crop growing on it.
    path:    the CSV file
    params:  settings from params.yaml (field order and crop from params["fields"])
    returns: [member, field, hour]  grain moisture at the END of each hour, % wet basis
    """
    table, shape = sort_by_field(pd.read_csv(path), params)
    crop_of = {field["name"]: field["crop"] for field in params["fields"]}
    crop = table["field"].map(crop_of)
    moisture = np.zeros(len(table))
    for name in crop.unique():
        rows = (crop == name).to_numpy()
        moisture[rows] = table.loc[rows, f"{name}_moisture_pct"]
    return moisture.reshape(shape)
