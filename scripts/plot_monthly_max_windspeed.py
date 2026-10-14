"""Plot monthly maximum windspeed for each downloaded station."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

INPUT_PATH = Path("outputs/observations.daily.parquet")
OUTPUT_PATH = Path("outputs/monthly_max_windspeed.png")


observations = pd.read_parquet(
    INPUT_PATH,
    columns=["stationID", "obsTimeUtc", "metric.windspeedHigh"],
)
observations = observations.dropna(subset=["metric.windspeedHigh"]).copy()
observations["month"] = (
    observations["obsTimeUtc"].dt.tz_convert(None).dt.to_period("M").dt.to_timestamp()
)
monthly = (
    observations.groupby(["month", "stationID"], as_index=False)["metric.windspeedHigh"]
    .max()
    .pivot(index="month", columns="stationID", values="metric.windspeedHigh")
)

axis = monthly.plot(figsize=(14, 8), linewidth=1.5)
axis.set_title("Monthly maximum windspeed by station")
axis.set_xlabel("Month")
axis.set_ylabel("Maximum windspeed (km/h)")
axis.grid(True, alpha=0.25)
axis.legend(title="Station", bbox_to_anchor=(1.02, 1), loc="upper left")
axis.figure.tight_layout()
axis.figure.savefig(OUTPUT_PATH, dpi=200, bbox_inches="tight")
plt.close(axis.figure)
