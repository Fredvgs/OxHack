"""Value function: how much is each field worth if we harvest it in a given hour?

Worked out separately for every forecast member, then averaged at the end.
"""

import numpy as np


def predict_moisture(start_moisture, weather, params):
    """Grain moisture (%) at the start of every hour.

    start_moisture: [field]                        latest moisture reading, %
    weather:        {name: [member, field, hour]}  needs "rain_mm" and "humidity_pct"
    returns:        [member, field, hour]          grain moisture, %
    """
    rain = weather["rain_mm"]
    humidity = weather["humidity_pct"]
    moisture = np.zeros(rain.shape)
    current = np.tile(start_moisture, (rain.shape[0], 1))  # [member, field]
    for hour in range(rain.shape[2]):
        moisture[:, :, hour] = current
        drying = params["drying_pct_per_hour"] * (100 - humidity[:, :, hour]) / 100
        wetting = params["rewetting_pct_per_mm"] * rain[:, :, hour]
        current = np.maximum(current - drying + wetting, params["min_moisture_pct"])
    return moisture


def field_values(weather, start_moisture, params, first_hour=0):
    """Expected £ per hectare if each field is harvested in each hour (0 when it can't be).

    weather:        {name: [member, field, hour]}  forecast, starting at season hour first_hour
    start_moisture: [field]                        latest moisture reading, %
    first_hour:     int                            season hour of the first column
    returns:        [field, hour]                  £/ha, averaged over forecast members
    """
    moisture = predict_moisture(start_moisture, weather, params)  # [member, field, hour]

    crops = [params["crops"][field["crop"]] for field in params["fields"]]
    price = np.array([crop["price_gbp_per_t"] for crop in crops])[None, :, None]
    tonnes = np.array([crop["yield_t_per_ha"] for crop in crops])[None, :, None]

    # grain sold, minus the cost of drying anything wetter than the target
    too_wet_pct = np.maximum(0, moisture - params["target_moisture_pct"])
    gbp_per_ha = tonnes * (price - params["drying_cost_gbp_per_t_per_pct"] * too_wet_pct)

    # the longer the crop stands, the more of it is lost
    hours_waited = first_hour + np.arange(moisture.shape[2])
    gbp_per_ha = gbp_per_ha * (1 - params["loss_pct_per_hour"] / 100) ** hours_waited

    # no harvesting in the rain, or when the grain is too wet
    no_rain = weather["rain_mm"] <= params["rain_limit_mm"]
    dry_enough = moisture <= params["max_harvest_moisture_pct"]
    return (gbp_per_ha * (no_rain & dry_enough)).mean(axis=0)
