import json
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import pyarrow.parquet as pq

from wunderground_pws.convert import METRIC_FIELDS, metadata_to_gpkg, observations_to_parquet


def full_observation(station_id="TEST1"):
    metric = {field: 1.5 for field in METRIC_FIELDS}
    metric["precipRate"] = None
    return {
        "stationID": station_id,
        "tz": "Indian/Mauritius",
        "obsTimeUtc": "2026-08-26T19:59:00Z",
        "obsTimeLocal": "2026-08-26 23:59:00",
        "epoch": 1787774340,
        "lat": -20.1,
        "lon": 57.5,
        "solarRadiationHigh": 785.2,
        "uvHigh": 7.0,
        "winddirAvg": 130,
        "humidityHigh": 85.0,
        "humidityLow": 45.0,
        "humidityAvg": 71.6,
        "qcStatus": -1,
        "metric": metric,
    }


class ConvertTests(unittest.TestCase):
    def test_metadata_to_gpkg(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = {"stationID": "TEST1", "tz": "Indian/Mauritius", "lat": -20.1, "lon": 57.5}
            (root / "TEST1.metadata.json").write_text(json.dumps(metadata))
            target = root / "out" / "stations.gpkg"
            self.assertEqual(metadata_to_gpkg(root, target), 1)
            frame = gpd.read_file(target, layer="stations")
            self.assertEqual(list(frame.columns), ["stationID", "tz", "lat", "lon", "geometry"])
            self.assertEqual(frame.crs.to_epsg(), 4326)
            self.assertEqual((frame.geometry.iloc[0].x, frame.geometry.iloc[0].y), (57.5, -20.1))
            with self.assertRaisesRegex(ValueError, "--overwrite"):
                metadata_to_gpkg(root, target)

    def test_observations_to_parquet_flattens_metric_and_types_times(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "TEST1.daily.jsonl").write_text(json.dumps(full_observation()) + "\n")
            target = root / "out" / "observations.parquet"
            self.assertEqual(observations_to_parquet(root, target, "daily"), 1)
            table = pq.read_table(target)
            self.assertIn("metric.precipRate", table.column_names)
            self.assertNotIn("metric", table.column_names)
            self.assertEqual(str(table.schema.field("obsTimeUtc").type), "timestamp[us, tz=UTC]")
            self.assertEqual(str(table.schema.field("obsTimeLocal").type), "timestamp[us]")
            self.assertIsNone(table.column("metric.precipRate")[0].as_py())

    def test_reports_invalid_json_line(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "TEST1.hourly.jsonl").write_text("not json\n")
            with self.assertRaisesRegex(ValueError, r"TEST1\.hourly\.jsonl:1"):
                observations_to_parquet(root, root / "observations.parquet", "hourly")
            self.assertFalse((root / "observations.parquet").exists())

    def test_rejects_station_filename_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "OTHER.all.jsonl").write_text(json.dumps(full_observation()) + "\n")
            with self.assertRaisesRegex(ValueError, "does not match filename"):
                observations_to_parquet(root, root / "observations.parquet", "all")

    def test_selects_only_requested_record_type_and_ignores_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "TEST1.daily.jsonl").write_text(json.dumps(full_observation()) + "\n")
            (root / "TEST1.hourly.jsonl").write_text("not json\n")
            (root / "TEST1.jsonl").write_text("not json\n")
            target = root / "observations.parquet"
            self.assertEqual(observations_to_parquet(root, target, "daily"), 1)
            self.assertEqual(pq.read_table(target).num_rows, 1)

    def test_rejects_invalid_record_type_and_missing_matching_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "invalid record type"):
                observations_to_parquet(root, root / "observations.parquet", "weekly")
            (root / "TEST1.jsonl").write_text(json.dumps(full_observation()) + "\n")
            with self.assertRaisesRegex(ValueError, r"no \*\.daily\.jsonl files"):
                observations_to_parquet(root, root / "observations.parquet", "daily")


if __name__ == "__main__":
    unittest.main()
