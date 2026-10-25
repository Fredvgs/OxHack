"""Plot the loaded forecast for each field: rain and humidity, every member plus the average.

A quick look at the data the pipeline runs on. Run it by hand:

uv run python scripts/plot_forecast.py
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))  # so "harvest" imports when run from scripts/

from harvest.forecast import load_forecast  # noqa: E402


def main():
    params = yaml.safe_load((ROOT / "params.yaml").read_text(encoding="utf-8"))
    weather = load_forecast(ROOT / "data" / "forecast.csv", params)
    plot_forecast(weather, params)
    plt.show()


def plot_forecast(weather, params):
    """One row per field, rain on the left and humidity on the right, sharing the hour axis.

    weather: {"rain_mm": [member, field, hour], "humidity_pct": [member, field, hour]}
    """
    fields = params["fields"]
    columns = [("rain_mm", "rain (mm/hour)"), ("humidity_pct", "humidity (%)")]
    fig, axes = plt.subplots(
        len(fields), 2, figsize=(12, 2 * len(fields)), sharex=True, squeeze=False
    )

    for f, field in enumerate(fields):
        for c, (key, label) in enumerate(columns):
            ax = axes[f, c]
            members = weather[key][:, f, :]  # [member, hour]
            # every member as a faint line shows the spread; the average is the one to read
            ax.plot(members.T, color="grey", linewidth=0.5, alpha=0.25)
            ax.plot(members.mean(axis=0), color="tab:blue", linewidth=2, label="average")
            ax.set_ylabel(label)
            ax.grid(alpha=0.3)
            if c == 0:
                ax.set_title(f"{field['name']} ({field['crop']})", loc="left")

    axes[0, 1].plot([], [], color="grey", linewidth=0.5, label="each member")
    axes[0, 1].legend(loc="upper right")
    for ax in axes[-1]:
        ax.set_xlabel("hour")
    fig.suptitle(f"Forecast per field ({weather['rain_mm'].shape[0]} members)")
    fig.tight_layout()
    return fig


if __name__ == "__main__":
    main()
