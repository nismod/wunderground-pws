"""Command-line tools for Weather Underground observations."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests

from .convert import metadata_to_gpkg, observations_to_parquet

API_BASE_URL = "https://api.weather.com/v2/pws/history"
API_KEY_ENV = "WEATHER_API_KEY"
MAX_RETRIES = 3
METADATA_FIELDS = ("stationID", "tz", "lat", "lon")
RECORD_TYPES = ("daily", "hourly", "all")


def _station_ids(args: argparse.Namespace) -> list[str]:
    if args.station_id:
        return [args.station_id]
    ids: list[str] = []
    for line in args.station_file.read_text().splitlines():
        station_id = line.split("#", 1)[0].strip()
        if station_id and station_id not in ids:
            ids.append(station_id)
    if not ids:
        raise ValueError("station file contains no station IDs")
    return ids


def _request(
    session: requests.Session,
    station_id: str,
    start: date,
    end: date,
    api_key: str,
    record_type: str,
) -> dict[str, Any]:
    params = {
        "stationId": station_id,
        "format": "json",
        "units": "m",
        "startDate": start.strftime("%Y%m%d"),
        "endDate": end.strftime("%Y%m%d"),
        "numericPrecision": "decimal",
        "apiKey": api_key,
    }
    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(f"{API_BASE_URL}/{record_type}", params=params, timeout=30)
            if response.status_code == 429 or response.status_code >= 500:
                response.raise_for_status()
                raise requests.HTTPError(f"retryable HTTP status {response.status_code}")
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("API response is not a JSON object")
            return payload
        except (requests.RequestException, ValueError):
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def _existing_epochs(path: Path) -> set[tuple[str, int]]:
    if not path.exists():
        return set()
    identities: set[tuple[str, int]] = set()
    for line in path.read_text().splitlines():
        try:
            observation = json.loads(line)
            identities.add((str(observation["stationID"]), int(observation["epoch"])))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
    return identities


def _metadata_from_observation(observation: dict[str, Any], station_id: str) -> dict[str, Any]:
    try:
        metadata = {field: observation[field] for field in METADATA_FIELDS}
    except KeyError as error:
        raise ValueError(f"observation is missing metadata field {error.args[0]!r}") from error
    if metadata["stationID"] != station_id:
        raise ValueError(
            f"observation stationID {metadata['stationID']!r} does not match requested station {station_id!r}"
        )
    if not isinstance(metadata["tz"], str) or not metadata["tz"]:
        raise ValueError("observation tz must be a non-empty string")
    for field in ("lat", "lon"):
        value = metadata[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"observation {field} must be numeric")
        metadata[field] = float(value)
    return metadata


def _valid_metadata(path: Path, station_id: str) -> bool:
    if not path.exists():
        return False
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict) or set(value) != set(METADATA_FIELDS):
            return False
        _metadata_from_observation(value, station_id)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    return True


def download_station(
    station_id: str,
    output_dir: Path,
    api_key: str,
    session: requests.Session,
    record_type: str,
) -> None:
    if record_type not in RECORD_TYPES:
        raise ValueError(f"invalid record type: {record_type}")
    output_dir.mkdir(parents=True, exist_ok=True)
    observations_path = output_dir / f"{station_id}.{record_type}.jsonl"
    metadata_path = output_dir / f"{station_id}.metadata.json"
    identities = _existing_epochs(observations_path)
    end = date.today()
    metadata_written = _valid_metadata(metadata_path, station_id)

    while True:
        start = end - timedelta(days=29)
        payload = _request(session, station_id, start, end, api_key, record_type)
        observations = payload.get("observations", [])
        if not isinstance(observations, list):
            raise ValueError("API response observations field is not a list")
        if not metadata_written and observations:
            first_observation = observations[0]
            if not isinstance(first_observation, dict):
                raise ValueError("first observation is not a JSON object")
            metadata = _metadata_from_observation(first_observation, station_id)
            metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
            metadata_written = True
        new_observations = []
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            try:
                identity = (str(observation["stationID"]), int(observation["epoch"]))
            except (KeyError, TypeError, ValueError):
                identity = (station_id, hash(json.dumps(observation, sort_keys=True)))
            if identity not in identities:
                identities.add(identity)
                new_observations.append(observation)
        if new_observations:
            with observations_path.open("a") as output:
                for observation in new_observations:
                    output.write(json.dumps(observation, separators=(",", ":")) + "\n")
        if not observations:
            return
        end = start - timedelta(days=1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download and convert daily weather observations.")
    commands = parser.add_subparsers(dest="command", required=True)

    download = commands.add_parser("download", help="download observations from Weather.com")
    group = download.add_mutually_exclusive_group(required=True)
    group.add_argument("--station-id", help="single weather station ID")
    group.add_argument("--station-file", type=Path, help="text file containing one station ID per line")
    download.add_argument("--api-key", help=f"Weather.com API key (default: ${API_KEY_ENV})")
    download.add_argument("--output-dir", type=Path, default=Path("."))
    download.add_argument("--record-type", choices=RECORD_TYPES, required=True)

    metadata = commands.add_parser("metadata-to-gpkg", help="combine station metadata into a GeoPackage")
    metadata.add_argument("input_dir", type=Path)
    metadata.add_argument("output", type=Path)
    metadata.add_argument("--overwrite", action="store_true")

    observations = commands.add_parser("observations-to-parquet", help="combine observations into Parquet")
    observations.add_argument("input_dir", type=Path)
    observations.add_argument("output", type=Path)
    observations.add_argument("--record-type", choices=RECORD_TYPES, required=True)
    observations.add_argument("--overwrite", action="store_true")
    return parser


def _run_download(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    api_key = args.api_key or os.environ.get(API_KEY_ENV)
    if not api_key:
        parser.error(f"provide --api-key or set {API_KEY_ENV}")
    try:
        station_ids = _station_ids(args)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    failures = 0
    with requests.Session() as session:
        for station_id in station_ids:
            try:
                download_station(station_id, args.output_dir, api_key, session, args.record_type)
                print(f"completed {station_id} ({args.record_type})")
            except Exception as error:  # noqa: BLE001 - continue batch processing
                failures += 1
                print(f"failed {station_id} ({args.record_type}): {error}", file=sys.stderr)
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "download":
        return _run_download(args, parser)
    try:
        if args.command == "metadata-to-gpkg":
            count = metadata_to_gpkg(args.input_dir, args.output, overwrite=args.overwrite)
            print(f"wrote {count} stations to {args.output}")
        else:
            count = observations_to_parquet(
                args.input_dir,
                args.output,
                args.record_type,
                overwrite=args.overwrite,
            )
            print(f"wrote {count} {args.record_type} observations to {args.output}")
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
