"""Load the prediction data (the weather forecast) from a CSV. The format is in data/README.md.

To use a different prediction format, rewrite load_forecast() so it returns the same thing.
"""

import pandas as pd

COLUMNS = ["rain_mm", "humidity_pct"]


def load_forecast(path, params):
    """Read the forecast CSV.

    path:    the CSV file
    params:  settings from params.yaml (the field order comes from params["fields"])
    returns: {"rain_mm": [member, field, hour], "humidity_pct": [member, field, hour]}
    """
    table = pd.read_csv(path)
    names = [field["name"] for field in params["fields"]]
    table = table[table["field"].isin(names)].copy()
    table["field_index"] = table["field"].map(names.index)
    table = table.sort_values(["member", "field_index", "hour"])
    shape = (table["member"].nunique(), len(names), table["hour"].nunique())
    return {column: table[column].to_numpy(dtype=float).reshape(shape) for column in COLUMNS}
