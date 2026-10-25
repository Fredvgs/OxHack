"""Value function: how much is each field worth if we harvest it in a given hour?

Worked out separately for every forecast member, then averaged at the end.
"""

import numpy as np

from harvest.moisture import simulate


def start_moisture(weather, params):
    """Grain moisture (%) of every field at hour 0.

    From the moisture forecast (weather["moisture_pct"], averaged over members) when it is
    loaded, otherwise the same placeholder, temp_start_moisture_pct, for every field.

    weather: {name: [member, field, hour]}  forecast
    returns: [field]                        grain moisture at hour 0, %
    """
    if "moisture_pct" in weather:
        return weather["moisture_pct"][:, :, 0].mean(axis=0)
    return np.full(len(params["fields"]), float(params["temp_start_moisture_pct"]))


def predict_moisture(start_moisture, weather, params):
    """Grain moisture (%) every hour, starting from the latest reading.

    With weather["moisture_pct"] (the moisture forecast CSV, see harvest/moisture.py) each member
    keeps its own hour-to-hour change but is shifted to start at the reading. With
    weather["temp_c"] (the past forecasts in replay.py), the grain moisture model in moisture.py
    runs from the reading. Without either, a simple model: dries with low humidity, wets with rain.

    start_moisture: [field]                        latest moisture reading, %
    weather:        {name: [member, field, hour]}  "moisture_pct", or "temp_c" and
                                                   "humidity_pct", or "rain_mm" and "humidity_pct"
    returns:        [member, field, hour]          grain moisture, %
    """
    if "moisture_pct" in weather:
        moisture = weather["moisture_pct"]
        return moisture - moisture[:, :, :1] + start_moisture[None, :, None]

    if "temp_c" in weather:
        moisture = np.zeros(weather["temp_c"].shape)
        constants = params["moisture_model"]
        for f, field in enumerate(params["fields"]):
            temp_c = weather["temp_c"][:, f]  # [member, hour]
            rh = weather["humidity_pct"][:, f] / 100  # [member, hour] as a decimal
            rain_mm = weather["rain_mm"][:, f]  # [member, hour]
            end_of_hour = simulate(
                field["crop"], start_moisture[f], temp_c, rh, rain_mm, constants=constants
            )
            # the model gives the moisture at the END of each hour; we want the start
            moisture[:, f, 0] = start_moisture[f]
            moisture[:, f, 1:] = end_of_hour[:, :-1]
        return moisture

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


def crop_numbers(params, key):
    """One crop number per field, e.g. key="price_gbp_per_t". Returns [1, field, 1]."""
    crops = [params["crops"][field["crop"]] for field in params["fields"]]
    return np.array([crop[key] for crop in crops], dtype=float)[None, :, None]


def drying_cost_gbp_per_t(moisture, params):
    """£ per tonne to have the store dry the grain, using Camgrain's published charges.

    Source: https://www.camgrain.co.uk/charges-for-2025 (cereals, harvest 2026). The handling
    charge and throughput loss are paid whatever the moisture, so they're left out.

    moisture: [member, field, hour]  grain moisture, % (from predict_moisture)
    returns:  [member, field, hour]  drying charge + value of the weight deducted, £/t
    """
    # a flat charge per 0.5% band above 15%: 15.1-15.5% -> £2, 15.6-16.0% -> £4, ...
    # (rounding first so 15.5% lands in the first band, not the second)
    excess_pct = np.round(moisture, 1) - params["free_drying_up_to_pct"]
    bands = np.maximum(0, np.ceil(np.round(excess_pct / params["drying_band_pct"], 6)))
    charge_gbp_per_t = params["drying_charge_gbp_per_band"] * bands

    # the store also keeps some weight for every point of moisture it removes
    removed_pct = np.maximum(0, moisture - params["target_moisture_pct"])
    weight_loss_pct = params["weight_loss_pct_per_pct"] * removed_pct
    price = crop_numbers(params, "price_gbp_per_t")
    return charge_gbp_per_t + price * weight_loss_pct / 100


def field_values(weather, start_moisture, params, first_hour=0):
    """Expected £ per hectare if each field is harvested in each hour (0 when it can't be).

    weather:        {name: [member, field, hour]}  forecast, starting at season hour first_hour
    start_moisture: [field]                        latest moisture reading, %
    first_hour:     int                            season hour of the first column
    returns:        [field, hour]                  £/ha, averaged over forecast members
    """
    return member_values(weather, start_moisture, params, first_hour).mean(axis=0)


def member_values(weather, start_moisture, params, first_hour=0):
    """£ per hectare if each field is harvested in each hour, in each forecast member separately.

    Same inputs as field_values. returns: [member, field, hour] £/ha, 0 when it can't be harvested
    """
    moisture = predict_moisture(start_moisture, weather, params)  # [member, field, hour]

    price = crop_numbers(params, "price_gbp_per_t")
    tonnes = crop_numbers(params, "yield_t_per_ha")

    # grain sold, minus what the store charges to dry it
    gbp_per_ha = tonnes * (price - drying_cost_gbp_per_t(moisture, params))

    # the longer the crop stands, the more of it is lost
    hours_waited = first_hour + np.arange(moisture.shape[2])
    gbp_per_ha = gbp_per_ha * (1 - params["loss_pct_per_hour"] / 100) ** hours_waited

    # no harvesting in the rain, or when the grain is too wet
    no_rain = weather["rain_mm"] <= params["rain_limit_mm"]
    dry_enough = moisture <= params["max_harvest_moisture_pct"]
    return gbp_per_ha * (no_rain & dry_enough)
