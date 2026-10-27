# Access automatic weather station records from Weather Underground

Personal weather station records are accessible via api.weather.com and can sometimes
complement or extend official records.

See API docs:
- [Personal Weather Station (PWS) Historical API](https://developer.weather.com/docs/openapi/pws-historical-2-0)
- [units of measure](https://developer.weather.com/docs/units-of-measure)

## CLI

This Python package provides a command-line interface to save weather station records.

We recommend using [`uv`](https://docs.astral.sh/uv/) to manage a Python virtual environment
and install dependencies, but any dependency manager should do the job.

Start by cloning this repository and setting up a virtual environment with dependencies:

```sh
git clone git@github.com:nismod/wunderground-pws.git
cd wunderground-pws
uv sync
```

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

## Find stations in an area

Search a longitude/latitude bounding box (`west south east north`) or a place
name, and optionally save IDs in the format accepted by `download --station-file`:

```sh
uv run wunderground-pws find-stations --bbox 57.3 -20.6 57.8 -19.9
uv run wunderground-pws find-stations --place "Port Louis, Mauritius" --output stations.txt
uv run wunderground-pws find-stations --bbox 57.2 -20.8 59.5 -19.5 --max-tiles 150 --output stations.txt
uv run wunderground-pws download --record-type daily --station-file stations.txt --output-dir data
```

Place names are resolved with OpenStreetMap Nominatim. Discovery uses the
current Weather.com station layer, so results represent stations currently
visible there, not a complete historical inventory. The search is limited to
100 map tiles per invocation by default. Increase this with `--max-tiles N`
for larger regions; the command then makes one station request per tile.

## Convert station metadata to GeoPackage

```sh
uv run wunderground-pws metadata-to-gpkg data outputs/stations.gpkg
```

This combines the `*.metadata.json` files into a `stations` point layer in
WGS84 (`EPSG:4326`). The attribute table retains `stationID`, `tz`, `lat`, and
`lon`.

## Convert observations to Parquet

```sh
uv run wunderground-pws observations-to-parquet --record-type daily data outputs/observations.parquet
```

This combines the `*.<record-type>.jsonl` files into one Parquet file. Each
output therefore contains only daily, hourly, or all-observation records. UTC
and local observation times are stored as typed timestamps. Values nested below
`metric` are flattened to columns such as `metric.tempHigh` and
`metric.precipTotal`. Legacy untyped `<station-id>.jsonl` files are ignored.

Conversion fails if the output exists. Pass `--overwrite` to replace it after a
successful conversion. Invalid input is reported with its filename and, for
JSON Lines, its line number.
