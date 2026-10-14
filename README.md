# Access automatic weather station records for stations in Mauritius and Rodrigues

Personal weather station records are logged to wunderground and accessible via 
api.weather.com

See API docs:
- [Personal Weather Station (PWS) Historical API](https://developer.weather.com/docs/openapi/pws-historical-2-0)
- [units of measure](https://developer.weather.com/docs/units-of-measure)

## CLI

Set the API key in `WEATHER_API_KEY` or provide it with `--api-key` (the command-line value takes precedence):

```sh
export WEATHER_API_KEY=your-key
uv run wunderground-pws download --record-type daily --station-id IRIVIR48 --output-dir data
uv run wunderground-pws download --record-type hourly --station-file stations.txt --output-dir data
uv run wunderground-pws download --record-type all --station-id IRIVIR48 --output-dir data
```

The required `--record-type` selects daily summaries, hourly summaries, or all
individual observations. The downloader requests inclusive 30-day periods,
working backward from today until the API returns no observations. Records are
appended immediately to `<station-id>.<record-type>.jsonl`, and duplicate
observations are skipped when rerunning.

The first recorded observation also creates `<station-id>.metadata.json` with
its `stationID`, `tz`, `lat`, and `lon`. Valid existing metadata is preserved;
empty or invalid metadata is repaired when an observation is available.
Transient request failures are retried, and a failed station does not prevent
other stations from being processed.

## Convert station metadata to GeoPackage

```sh
uv run wunderground-pws metadata-to-gpkg data outputs/stations.gpkg
```

This combines the non-recursive `*.metadata.json` files into a `stations` point
layer in WGS84 (`EPSG:4326`). The attribute table retains `stationID`, `tz`,
`lat`, and `lon`.

## Convert observations to Parquet

```sh
uv run wunderground-pws observations-to-parquet --record-type daily data outputs/observations.parquet
```

This combines the non-recursive `*.<record-type>.jsonl` files into one Parquet
file. Each output therefore contains only daily, hourly, or all-observation
records. UTC and local observation times are stored as typed timestamps. Values
nested below `metric` are flattened to columns such as `metric.tempHigh` and
`metric.precipTotal`. Legacy untyped `<station-id>.jsonl` files are ignored.

Conversion fails if the output exists. Pass `--overwrite` to replace it after a
successful conversion. Invalid input is reported with its filename and, for
JSON Lines, its line number.
