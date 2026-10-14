"""Conversion of downloaded station data into analysis-ready formats."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

import geopandas as gpd
import pyarrow as pa
import pyarrow.parquet as pq

METADATA_FIELDS = ("stationID", "tz", "lat", "lon")
RECORD_TYPES = ("daily", "hourly", "all")
FLOAT_FIELDS = (
    "solarRadiationHigh",
    "uvHigh",
    "humidityHigh",
    "humidityLow",
    "humidityAvg",
)
METRIC_FIELDS = (
    "tempHigh",
    "tempLow",
    "tempAvg",
    "windspeedHigh",
    "windspeedLow",
    "windspeedAvg",
    "windgustHigh",
    "windgustLow",
    "windgustAvg",
    "dewptHigh",
    "dewptLow",
    "dewptAvg",
    "windchillHigh",
    "windchillLow",
    "windchillAvg",
    "heatindexHigh",
    "heatindexLow",
    "heatindexAvg",
    "pressureMax",
    "pressureMin",
    "pressureTrend",
    "precipRate",
    "precipTotal",
)
OBSERVATION_FIELDS = {
    "stationID",
    "tz",
    "obsTimeUtc",
    "obsTimeLocal",
    "epoch",
    "lat",
    "lon",
    *FLOAT_FIELDS,
    "winddirAvg",
    "qcStatus",
    "metric",
}
PARQUET_SCHEMA = pa.schema(
    [
        pa.field("stationID", pa.string(), nullable=False),
        pa.field("tz", pa.string(), nullable=False),
        pa.field("obsTimeUtc", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("obsTimeLocal", pa.timestamp("us"), nullable=False),
        pa.field("epoch", pa.int64(), nullable=False),
        pa.field("lat", pa.float64(), nullable=False),
        pa.field("lon", pa.float64(), nullable=False),
        *(pa.field(field, pa.float64()) for field in FLOAT_FIELDS),
        pa.field("winddirAvg", pa.int64()),
        pa.field("qcStatus", pa.int64(), nullable=False),
        *(pa.field(f"metric.{field}", pa.float64()) for field in METRIC_FIELDS),
    ]
)


def _files(input_dir: Path, pattern: str) -> list[Path]:
    if not input_dir.is_dir():
        raise ValueError(f"input directory does not exist: {input_dir}")
    paths = sorted(input_dir.glob(pattern))
    if not paths:
        raise ValueError(f"no {pattern} files found in {input_dir}")
    return paths


def _number(value: Any, field: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric{(' or null' if nullable else '')}")
    return float(value)


def _integer(value: Any, field: str, *, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer{(' or null' if nullable else '')}")
    return value


def _metadata(value: Any, station_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("metadata must be a JSON object")
    if set(value) != set(METADATA_FIELDS):
        raise ValueError(f"metadata fields must be exactly {', '.join(METADATA_FIELDS)}")
    if value["stationID"] != station_id:
        raise ValueError(f"stationID {value['stationID']!r} does not match filename station {station_id!r}")
    if not isinstance(value["tz"], str) or not value["tz"]:
        raise ValueError("tz must be a non-empty string")
    return {
        "stationID": station_id,
        "tz": value["tz"],
        "lat": _number(value["lat"], "lat"),
        "lon": _number(value["lon"], "lon"),
    }


def _prepare_output(output: Path, overwrite: bool) -> None:
    if output.exists() and not overwrite:
        raise ValueError(f"output already exists: {output}; use --overwrite to replace it")
    output.parent.mkdir(parents=True, exist_ok=True)


def _temporary_path(output: Path, suffix: str) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=f".{output.stem}.", suffix=suffix, dir=output.parent)
    os.close(descriptor)
    path = Path(name)
    path.unlink()
    return path


def metadata_to_gpkg(input_dir: Path, output: Path, *, overwrite: bool = False) -> int:
    """Combine station metadata files into a WGS84 GeoPackage."""
    _prepare_output(output, overwrite)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in _files(input_dir, "*.metadata.json"):
        station_id = path.name.removesuffix(".metadata.json")
        try:
            row = _metadata(json.loads(path.read_text()), station_id)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise ValueError(f"{path}: {error}") from error
        if station_id in seen:
            raise ValueError(f"{path}: duplicate stationID {station_id!r}")
        seen.add(station_id)
        rows.append(row)

    frame = gpd.GeoDataFrame(
        rows,
        geometry=gpd.points_from_xy([row["lon"] for row in rows], [row["lat"] for row in rows]),
        crs="EPSG:4326",
    )
    temporary = _temporary_path(output, ".gpkg")
    try:
        frame.to_file(temporary, layer="stations", driver="GPKG", engine="pyogrio", index=False)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return len(rows)


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("obsTimeUtc must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("obsTimeUtc must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError("obsTimeUtc must include a UTC offset")
    return parsed.astimezone(UTC)


def _parse_local(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("obsTimeLocal must be a string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("obsTimeLocal must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is not None:
        raise ValueError("obsTimeLocal must not include a UTC offset")
    return parsed


def _flatten_observation(value: Any, expected_station: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("observation must be a JSON object")
    if set(value) != OBSERVATION_FIELDS:
        missing = sorted(OBSERVATION_FIELDS - set(value))
        extra = sorted(set(value) - OBSERVATION_FIELDS)
        raise ValueError(f"observation schema mismatch (missing={missing}, extra={extra})")
    if value["stationID"] != expected_station:
        raise ValueError(f"stationID {value['stationID']!r} does not match filename station {expected_station!r}")
    if not isinstance(value["stationID"], str) or not isinstance(value["tz"], str):
        raise ValueError("stationID and tz must be strings")
    metric = value["metric"]
    if not isinstance(metric, dict) or set(metric) != set(METRIC_FIELDS):
        raise ValueError("metric fields do not match the expected schema")

    row: dict[str, Any] = {
        "stationID": value["stationID"],
        "tz": value["tz"],
        "obsTimeUtc": _parse_utc(value["obsTimeUtc"]),
        "obsTimeLocal": _parse_local(value["obsTimeLocal"]),
        "epoch": _integer(value["epoch"], "epoch"),
        "lat": _number(value["lat"], "lat"),
        "lon": _number(value["lon"], "lon"),
        "winddirAvg": _integer(value["winddirAvg"], "winddirAvg", nullable=True),
        "qcStatus": _integer(value["qcStatus"], "qcStatus"),
    }
    row.update({field: _number(value[field], field, nullable=True) for field in FLOAT_FIELDS})
    row.update(
        {f"metric.{field}": _number(metric[field], f"metric.{field}", nullable=True) for field in METRIC_FIELDS}
    )
    return row


def _observation_rows(paths: list[Path], record_type: str) -> Iterator[dict[str, Any]]:
    suffix = f".{record_type}.jsonl"
    for path in paths:
        station_id = path.name.removesuffix(suffix)
        with path.open() as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    yield _flatten_observation(json.loads(line), station_id)
                except (ValueError, TypeError, json.JSONDecodeError) as error:
                    raise ValueError(f"{path}:{line_number}: {error}") from error


def observations_to_parquet(
    input_dir: Path,
    output: Path,
    record_type: str,
    *,
    overwrite: bool = False,
) -> int:
    """Combine JSON Lines observations into one flat Parquet file."""
    if record_type not in RECORD_TYPES:
        raise ValueError(f"invalid record type: {record_type}")
    _prepare_output(output, overwrite)
    paths = _files(input_dir, f"*.{record_type}.jsonl")
    temporary = _temporary_path(output, ".parquet")
    writer: pq.ParquetWriter | None = None
    count = 0
    batch: list[dict[str, Any]] = []
    try:
        writer = pq.ParquetWriter(temporary, PARQUET_SCHEMA)
        for row in _observation_rows(paths, record_type):
            batch.append(row)
            count += 1
            if len(batch) == 10_000:
                writer.write_table(pa.Table.from_pylist(batch, schema=PARQUET_SCHEMA))
                batch.clear()
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=PARQUET_SCHEMA))
        writer.close()
        writer = None
        os.replace(temporary, output)
    finally:
        if writer is not None:
            writer.close()
        temporary.unlink(missing_ok=True)
    return count
