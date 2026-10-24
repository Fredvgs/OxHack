"""Value function: how much is each field worth if we harvest it in a given hour?

Worked out separately for every forecast member, then averaged at the end.
"""

import numpy as np


def start_moisture(weather, params):
    """Grain moisture (%) of every field at hour 0.

    The moisture vs time graph will provide this. Until then every field gets the same
    placeholder, temp_start_moisture_pct.

    weather: {name: [member, field, hour]}  forecast (unused by the placeholder)
    returns: [field]                        grain moisture at hour 0, %
    """
    return np.full(len(params["fields"]), float(params["temp_start_moisture_pct"]))


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
    return (gbp_per_ha * (no_rain & dry_enough)).mean(axis=0)
