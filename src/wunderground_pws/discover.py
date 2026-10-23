"""Discover current personal weather stations in Weather.com vector tiles."""

from __future__ import annotations

import math
from typing import Any

import requests

PRODUCT_URL = "https://api3.weather.com/v2/vector-api/products/614"
GEOCODER_URL = "https://nominatim.openstreetmap.org/search"
LOD = 12
TILE_SIZE = 512
DEFAULT_MAX_TILES = 100
HEADERS = {"User-Agent": "wunderground-pws/0.1 (station discovery)"}


def validate_bbox(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    west, south, east, north = bbox
    if not all(map(math.isfinite, bbox)) or not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("bbox must be west south east north with valid longitude and latitude ranges")
    return bbox


def geocode_place(place: str, session: requests.Session) -> tuple[float, float, float, float]:
    response = session.get(
        GEOCODER_URL,
        params={"q": place, "format": "jsonv2", "limit": 1},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    results = response.json()
    if not isinstance(results, list) or not results:
        raise ValueError(f"place not found: {place}")
    bounds = results[0]["boundingbox"]  # Nominatim order: south, north, west, east.
    return validate_bbox((float(bounds[2]), float(bounds[0]), float(bounds[3]), float(bounds[1])))


def _tile(lon: float, lat: float) -> tuple[int, int]:
    # A 512-pixel tile at lod 12 uses the same XYZ grid as 256-pixel zoom 11.
    count = 1 << (LOD - 1)
    x = min(count - 1, max(0, int((lon + 180) / 360 * count)))
    clipped_lat = max(-85.05112878, min(85.05112878, lat))
    y = min(count - 1, max(0, int((1 - math.asinh(math.tan(math.radians(clipped_lat))) / math.pi) / 2 * count)))
    return x, y


def find_stations(
    bbox: tuple[float, float, float, float], api_key: str, session: requests.Session,
    *, max_tiles: int = DEFAULT_MAX_TILES,
) -> list[str]:
    if max_tiles < 1:
        raise ValueError("max_tiles must be a positive integer")
    west, south, east, north = validate_bbox(bbox)
    x0, y0 = _tile(west, north)
    x1, y1 = _tile(east, south)
    tile_count = (x1 - x0 + 1) * (y1 - y0 + 1)
    if tile_count > max_tiles:
        raise ValueError(f"area spans {tile_count} tiles; narrow the bbox or place, or raise --max-tiles (current limit {max_tiles})")

    response = session.get(f"{PRODUCT_URL}/info", params={"apiKey": api_key, "max-times": 1}, timeout=30)
    response.raise_for_status()
    times = response.json().get("products", {}).get("614", {}).get("time", [])
    if not times:
        raise ValueError("Weather.com did not provide a current station time label")
    current_time = times[0]

    stations: set[str] = set()
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            response = session.get(
                f"{PRODUCT_URL}/features",
                params={
                    "x": x, "y": y, "lod": LOD, "apiKey": api_key,
                    "tile-size": TILE_SIZE, "time": current_time, "stepped": "true",
                },
                timeout=30,
            )
            response.raise_for_status()
            collection: Any = response.json().get(current_time, {})
            for feature in collection.get("features", []):
                geometry = feature.get("geometry", {})
                if geometry.get("type") != "Point":
                    continue
                coordinates = geometry.get("coordinates", [])
                station_id = feature.get("id")
                if len(coordinates) < 2 or not isinstance(station_id, str) or not station_id:
                    continue
                lon, lat = coordinates[:2]
                if west <= lon <= east and south <= lat <= north:
                    stations.add(station_id)
    return sorted(stations)
