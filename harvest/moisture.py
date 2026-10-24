"""Grain moisture over time from hourly temperature and humidity (wheat, barley, oilseed rape).

Three steps, every hour:
1. equilibrium moisture the grain is heading towards (modified Henderson),
2. how fast it gets there at this temperature (Arrhenius),
3. move part of the way there (Lewis first-order drying / wetting).

Rain is ignored for now: the measured RH is used as given.
forecast_moisture() runs every crop on the temperature and humidity in data/forecast.csv.
Moisture is dry basis (kg water per kg dry matter) inside the model; simulate() takes and returns
wet basis in %, which is how harvest moisture is quoted. Every constant is in params.yaml under
"moisture_model", with its source.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).parent.parent
PARAMS_PATH = ROOT / "params.yaml"
FORECAST_PATH = ROOT / "data" / "forecast.csv"


def load_constants(path=PARAMS_PATH):
    """The "moisture_model" block of params.yaml, as a dict."""
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))["moisture_model"]


CONSTANTS = load_constants()


def crop_constants(crop, constants):
    """The constants for one crop ("wheat", "barley" or "osr")."""
    if crop not in constants["crops"]:
        raise ValueError(f"unknown crop {crop!r}, expected one of {list(constants['crops'])}")
    return constants["crops"][crop]


def wb_to_db(m_wb):
    """Wet basis (decimal, kg water per kg grain) -> dry basis (kg water per kg dry matter)."""
    return m_wb / (1 - m_wb)


def db_to_wb(m_db):
    """Dry basis (kg water per kg dry matter) -> wet basis (decimal, kg water per kg grain)."""
    return m_db / (1 + m_db)


def emc_db(crop, T, RH, constants=CONSTANTS):
    """Equilibrium moisture content, dry basis (kg/kg), from the modified Henderson equation.

    T:       any shape  air temperature, °C
    RH:      same shape relative humidity, decimal (clipped to [rh_min, rh_max] first)
    returns: same shape equilibrium moisture, kg water per kg dry matter
    """
    c = crop_constants(crop, constants)
    rh = np.clip(RH, constants["rh_min"], constants["rh_max"])
    inside = -np.log(1 - rh) / (c["henderson_k"] * (np.asarray(T) + c["henderson_c"]))
    # Henderson's constants were fitted to EMC in % dry basis (e.g. 17.6 = 17.6 kg water per 100 kg
    # dry matter), but the model works in kg per kg (0.176), so divide by 100
    emc_db_pct = inside ** (1 / c["henderson_n"])
    return emc_db_pct / 100


def k_of_T(crop, T, constants=CONSTANTS):
    """Drying constant k (1/hour) at temperature T (°C), scaled from k_ref at t_ref_c by Arrhenius.

    The same k is used for wetting: the direction comes from whether EMC is above or below M.
    T:       any shape, °C
    returns: same shape, 1/hour
    """
    c = crop_constants(crop, constants)
    t_k = np.asarray(T) + constants["kelvin_offset"]
    t_ref_k = c["t_ref_c"] + constants["kelvin_offset"]
    ea_over_r = c["ea_j_per_mol"] / constants["gas_constant_j_per_mol_k"]
    return c["k_ref_per_hour"] * np.exp(-ea_over_r * (1 / t_k - 1 / t_ref_k))


def simulate(crop, M0_wb_percent, T_c, RH, dt=1.0, constants=CONSTANTS):
    """Grain moisture after each time step, % wet basis.

    Each step holds EMC and k constant and restarts the Lewis solution from the current moisture:
    M(t + dt) = Me + (M(t) - Me) * exp(-k dt), all in dry basis.

    Hour is always the LAST axis, so T_c and RH can be one series [hour] or a whole forecast
    [member, field, hour].

    M0_wb_percent: float, or the shape without hour  starting moisture, % wet basis
                   (params.yaml has one per crop: moisture_model -> crops -> start_moisture_pct)
    T_c:           [..., hour]  air temperature, °C
    RH:            [..., hour]  relative humidity, decimal
    dt:            float        hours per step
    returns:       [..., hour]  moisture at the END of each step, % wet basis
    """
    T_c, RH = np.asarray(T_c, dtype=float), np.asarray(RH, dtype=float)  # also accepts lists
    me = emc_db(crop, T_c, RH, constants)  # [..., hour]
    keep = np.exp(-k_of_T(crop, T_c, constants) * dt)  # fraction of the gap left after a step
    m_db = wb_to_db(np.asarray(M0_wb_percent, dtype=float) / 100)
    moisture_wb_pct = np.zeros(me.shape)
    for hour in range(me.shape[-1]):
        m_db = me[..., hour] + (m_db - me[..., hour]) * keep[..., hour]
        moisture_wb_pct[..., hour] = 100 * db_to_wb(m_db)
    return moisture_wb_pct


def forecast_moisture(path=FORECAST_PATH, constants=CONSTANTS):
    """Moisture of every crop at every hour, member and field of the forecast CSV.

    Each crop starts at its start_moisture_pct and is run on the temp_c and humidity_pct columns.
    path:    the forecast CSV (format in data/README.md)
    returns: the CSV as a table, plus one column per crop, e.g. "wheat_moisture_pct": moisture
             (% wet basis) at the end of that hour
    """
    table = pd.read_csv(path).sort_values(["member", "field", "hour"], ignore_index=True)
    n_hours = table["hour"].nunique()
    # one row per (member, field), one column per hour
    T_c = table["temp_c"].to_numpy(dtype=float).reshape(-1, n_hours)
    RH = table["humidity_pct"].to_numpy(dtype=float).reshape(-1, n_hours) / 100
    for crop, c in constants["crops"].items():
        moisture = simulate(crop, c["start_moisture_pct"], T_c, RH, constants=constants)
        table[f"{crop}_moisture_pct"] = moisture.ravel()
    return table


def synthetic_weather(demo):
    """Made-up hourly weather with a daily cycle: warm and dry in the afternoon, cool and humid at
    dawn. demo is the "moisture_demo" block of params.yaml.

    returns: (T_c [hour] in °C, RH [hour] as a decimal)
    """
    hours = np.arange(demo["days"] * 24)
    daily = np.cos(2 * np.pi * (hours - demo["warmest_hour"]) / 24)  # 1 at the warmest hour
    T_c = demo["mean_temp_c"] + demo["temp_swing_c"] * daily
    RH = demo["mean_rh"] - demo["rh_swing"] * daily
    return T_c, RH
