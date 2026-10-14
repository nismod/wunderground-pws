"""Plot Mauritius weather stations with Rodrigues in an inset map."""

from pathlib import Path

import contextily as ctx
import geopandas as gpd
import matplotlib.pyplot as plt
from adjustText import adjust_text

INPUT_PATH = Path("outputs/stations.gpkg")
OUTPUT_PATH = Path("outputs/stations.png")


stations = gpd.read_file(INPUT_PATH, layer="stations").to_crs(epsg=3857)
mauritius = stations.loc[stations["stationID"] != "ICRVECUR4"].copy()
rodrigues = stations.loc[stations["stationID"] == "ICRVECUR4"].copy()

fig, (ax, inset) = plt.subplots(nrows=1, ncols=2, figsize=(16, 10))

ax.set_xlim(left=6.375e6, right=6.44e6)
ax.set_ylim(bottom=-2.34e6, top=-2.265e6)

mauritius.plot(
    ax=ax,
    color="#d62728",
    edgecolor="white",
    linewidth=1.0,
    zorder=2
)

ctx.add_basemap(
    ax,
    source=ctx.providers.OpenStreetMap.HOT,
    zoom=12,
    attribution=False,
    interpolation="bilinear",
)

labels = [
    ax.text(
        row.geometry.x,
        row.geometry.y,
        row.stationID,
        fontsize=9,
        fontweight="bold",
        bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": "none", "alpha": 0.3},
        zorder=3,
    )
    for row in mauritius.itertuples()
]
adjust_text(
    labels,
    ax=ax,
    arrowprops={"arrowstyle": "-", "color": "#555555", "linewidth": 0.6},
)
ax.set_axis_off()

rodrigues.plot(
    ax=inset,
    color="#d62728",
    edgecolor="white",
    linewidth=1.0,
    markersize=80,
    zorder=2,
)
ctx.add_basemap(
    inset,
    source=ctx.providers.OpenStreetMap.HOT,
    zoom=12,
    attribution=False,
    interpolation="bilinear",
)
point = rodrigues.geometry.iloc[0]
inset.annotate(
    "ICRVECUR4",
    xy=(point.x, point.y),
    xytext=(8, 8),
    textcoords="offset points",
    fontsize=9,
    fontweight="bold",
    bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": "none", "alpha": 0.9},
    zorder=3,
)
inset.set_title("Rodrigues", fontsize=11, fontweight="bold")

fig.suptitle("Weather stations of Mauritius and Rodrigues", fontsize=17, y=0.97)
fig.text(
    0.01,
    0.01,
    ctx.providers.OpenStreetMap.HOT.attribution,
    fontsize=7,
    color="#333333",
)
plt.show()
plt.close()

# fig.subplots_adjust(left=0.03, right=0.98, bottom=0.04, top=0.93, wspace=0.05, hspace=0.18)
# fig.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight", facecolor="white")
# plt.close(fig)
