"""Grain moisture over time from hourly temperature and humidity (wheat, barley, oilseed rape).

Every dry hour, three steps:
1. equilibrium moisture the grain is heading towards (modified Henderson),
2. how fast it gets there at this temperature (Arrhenius),
3. move part of the way there (Lewis first-order drying / wetting).

Every rain hour (rain_mm >= rain_threshold_mm and rain_mm > 0), for every crop, those steps are
REPLACED by a fixed rise, capped (Smith, Bailey & Ingram 1981, eqns 6a and 6b):
    m_db = min(m_db + rain_rise_per_hour * rain_rise_scale * dt, rain_max_mc)
rain_rise_scale is per crop: 1.0 for wheat and barley (the rule unchanged). Oilseed rape takes the
rule through its rain_rise_scale too, but its value is an unsourced analogy with barley.

Limitations of the rain rule:
- It was fitted together with Smith et al.'s own k and EMC. Paired with the Henderson/Arrhenius
  dry-hour constants here it is NOT validated: in one comparison, grain recovered from rain much
  faster here than in their model.
- It predicts moisture at the END of a rain period; values during rain hours aren't validated.
- It depends on how long it rains, not how much (amount-based terms fitted no better).
- Smith et al.'s RMS error against field data was about 0.03-0.065 kg/kg (3-6.5 moisture points).
- It was fitted to rain-gauge readings. Forecast rain is a different kind of data. Every hour at or
  above rain_threshold_mm counts as a full rain hour; the threshold is the project's own choice.
- Oilseed rape: its rain rise is the barley rule applied by analogy, with no published source for
  rapeseed; its cap rain_max_mc (0.52 kg/kg) comes from barley and has no rapeseed basis; and its
  k_ref is still a placeholder, which sets how fast it recovers after rain.

forecast_moisture() runs every crop on the temperature, humidity and rain in data/forecast.csv.
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
WEATHER_COLUMNS = ["temp_c", "humidity_pct", "rain_mm"]  # forecast CSV columns the model reads


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


def check_rain(rain_mm, T_c):
    """Rain as a float array, after checking it has T_c's shape and no NaN or negative values."""
    rain = np.asarray(rain_mm, dtype=float)
    if rain.shape != T_c.shape:
        raise ValueError(f"rain_mm has shape {rain.shape}, but T_c has shape {T_c.shape}")
    if np.isnan(rain).any():
        raise ValueError("rain_mm contains NaN: fill missing hours before simulating")
    if (rain < 0).any():
        raise ValueError(f"rain_mm contains negative values (lowest {rain.min()})")
    return rain


def rain_hours(rain_mm, constants=CONSTANTS):
    """True for every rain hour: rain_mm >= rain_threshold_mm and rain_mm > 0.

    The "> 0" stops a threshold of 0 turning every dry hour into a rain hour.
    rain_mm: any shape, mm per step
    returns: same shape, bool
    """
    rain = np.asarray(rain_mm, dtype=float)
    return (rain >= constants["rain_threshold_mm"]) & (rain > 0)


def simulate(crop, M0_wb_percent, T_c, RH, rain_mm, dt=1.0, constants=CONSTANTS):
    """Grain moisture after each time step, % wet basis.

    Dry step: hold EMC and k constant and restart the Lewis solution from the current moisture,
    M(t + dt) = Me + (M(t) - Me) * exp(-k dt), all in dry basis.
    Rain step (rain_mm >= rain_threshold_mm and rain_mm > 0, every crop): replaces the dry step,
    M(t + dt) = min(M(t) + rain_rise_per_hour * rain_rise_scale * dt, rain_max_mc). With
    rain_rise_scale 0, rain hours take the dry step instead. See the module docstring for the
    rain rule's limitations.

    Hour is always the LAST axis, so T_c, RH and rain_mm can be one series [hour] or a whole
    forecast [member, field, hour].

    M0_wb_percent: float, or the shape without hour  starting moisture, % wet basis
                   (params.yaml has one per crop: moisture_model -> crops -> start_moisture_pct)
    T_c:           [..., hour]  air temperature, °C
    RH:            [..., hour]  relative humidity, decimal
    rain_mm:       [..., hour]  rain during each step, mm (required)
    dt:            float        hours per step
    returns:       [..., hour]  moisture at the END of each step, % wet basis
    """
    c = crop_constants(crop, constants)
    T_c, RH = np.asarray(T_c, dtype=float), np.asarray(RH, dtype=float)  # also accepts lists
    rain = check_rain(rain_mm, T_c)
    rise = constants["rain_rise_per_hour"] * c["rain_rise_scale"] * dt  # kg/kg per rain step
    # with no rise (rain_rise_scale 0) rain hours are ordinary dry hours, not frozen ones
    rain_hour = rain_hours(rain, constants) & (rise > 0)  # [..., hour]
    me = emc_db(crop, T_c, RH, constants)  # [..., hour]
    keep = np.exp(-k_of_T(crop, T_c, constants) * dt)  # fraction of the gap left after a step
    m_db = wb_to_db(np.asarray(M0_wb_percent, dtype=float) / 100)
    moisture_wb_pct = np.zeros(me.shape)
    for hour in range(me.shape[-1]):
        dry = me[..., hour] + (m_db - me[..., hour]) * keep[..., hour]
        wet = np.minimum(m_db + rise, constants["rain_max_mc"])
        m_db = np.where(rain_hour[..., hour], wet, dry)
        moisture_wb_pct[..., hour] = 100 * db_to_wb(m_db)
    return moisture_wb_pct


def forecast_moisture(path=FORECAST_PATH, constants=CONSTANTS):
    """Moisture of every crop at every hour, member and field of the forecast CSV.

    Each crop starts at its start_moisture_pct and is run on the temp_c, humidity_pct and rain_mm
    (mm per hour) columns.
    path:    the forecast CSV (format in data/README.md)
    returns: the CSV as a table, plus one column per crop, e.g. "wheat_moisture_pct": moisture
             (% wet basis) at the end of that hour, including the rain rule (all crops)
    """
    table = pd.read_csv(path)
    missing = [name for name in WEATHER_COLUMNS if name not in table.columns]
    if missing:
        raise ValueError(f"{path} has no {missing} column(s); expected {WEATHER_COLUMNS}")
    table = table.sort_values(["member", "field", "hour"], ignore_index=True)
    n_hours = table["hour"].nunique()
    # one row per (member, field), one column per hour
    T_c = table["temp_c"].to_numpy(dtype=float).reshape(-1, n_hours)
    RH = table["humidity_pct"].to_numpy(dtype=float).reshape(-1, n_hours) / 100
    rain_mm = table["rain_mm"].to_numpy(dtype=float).reshape(-1, n_hours)
    for crop, c in constants["crops"].items():
        moisture = simulate(crop, c["start_moisture_pct"], T_c, RH, rain_mm, constants=constants)
        table[f"{crop}_moisture_pct"] = moisture.ravel()
    return table


def synthetic_weather(demo):
    """Made-up hourly weather with a daily cycle: warm and dry in the afternoon, cool and humid at
    dawn, plus a few spells of rain. demo is the "moisture_demo" block of params.yaml.

    returns: (T_c [hour] in °C, RH [hour] as a decimal, rain_mm [hour] in mm)
    """
    hours = np.arange(demo["days"] * 24)
    daily = np.cos(2 * np.pi * (hours - demo["warmest_hour"]) / 24)  # 1 at the warmest hour
    T_c = demo["mean_temp_c"] + demo["temp_swing_c"] * daily
    RH = demo["mean_rh"] - demo["rh_swing"] * daily
    rain_mm = np.zeros(len(hours))
    for first_hour, n_hours in demo["rain_spells"]:
        rain_mm[first_hour : first_hour + n_hours] = demo["rain_mm_per_hour"]
    return T_c, RH, rain_mm
