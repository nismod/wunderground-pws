"""Plot hourly windspeed for each downloaded station around Cyclone Belal (2024-01-13 to -18)."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

INPUT_PATH = Path("outputs/observations.hourly.parquet")
OUTPUT_PATH = Path("outputs/hourly_belal_2024-01.png")


observations = (
    pd.read_parquet(
        INPUT_PATH,
        columns=["stationID", "obsTimeUtc", "metric.windspeedHigh"],
        filters=[("obsTimeUtc", ">", pd.Timestamp("2024-01-14", tz='UTC')), ("obsTimeUtc", "<", pd.Timestamp("2024-01-19", tz='UTC'))],
    )
    .dropna(subset=["metric.windspeedHigh"])
)
observations["hour"] = (
    observations["obsTimeUtc"].dt.tz_convert(None).dt.to_period("h").dt.to_timestamp()
)

observations = (
    observations
    .groupby(["hour", "stationID"], as_index=False)["metric.windspeedHigh"]
    .max()
    .pivot(index="hour", columns="stationID", values="metric.windspeedHigh")
)


axis = observations.plot(figsize=(14, 8), linewidth=1.5, marker='x')
axis.set_title("Maximum windspeed by station")
axis.set_xlabel("Time")
axis.set_ylabel("Maximum windspeed (km/h)")
axis.grid(True, alpha=0.25)
axis.legend(title="Station", bbox_to_anchor=(1.02, 1), loc="upper left")
axis.figure.tight_layout()
axis.figure.savefig(OUTPUT_PATH, dpi=200, bbox_inches="tight")
plt.close(axis.figure)


#
# Go again, with "all" reported data
#

INPUT_PATH = Path("outputs/observations.all.parquet")
OUTPUT_PATH = Path("outputs/all_belal_2024-01.png")


observations = (
    pd.read_parquet(
        INPUT_PATH,
        columns=["stationID", "obsTimeUtc", "metric.windspeedHigh"],
        filters=[("obsTimeUtc", ">", pd.Timestamp("2024-01-14 06:00", tz='UTC')), ("obsTimeUtc", "<", pd.Timestamp("2024-01-18 06:00", tz='UTC'))],
    )
    .dropna(subset=["metric.windspeedHigh"])
)
observations["hour"] = (
    observations["obsTimeUtc"].dt.tz_convert(None).dt.to_period("30min").dt.to_timestamp()
)

observations = (
    observations
    .groupby(["hour", "stationID"], as_index=False)["metric.windspeedHigh"]
    .max()
    .pivot(index="hour", columns="stationID", values="metric.windspeedHigh")
)


axis = observations.plot(figsize=(14, 8), linewidth=1.5, marker='x')
axis.set_title("Maximum windspeed by station")
axis.set_xlabel("Time")
axis.set_ylabel("Maximum windspeed (km/h)")
axis.grid(True, alpha=0.25)
axis.legend(title="Station", bbox_to_anchor=(1.02, 1), loc="upper left")
axis.figure.tight_layout()
axis.figure.savefig(OUTPUT_PATH, dpi=200, bbox_inches="tight")
plt.close(axis.figure)
