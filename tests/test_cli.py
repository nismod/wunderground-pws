import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from wunderground_pws.cli import API_BASE_URL, build_parser, download_station


def response(observations):
    result = Mock(status_code=200)
    result.json.return_value = {"observations": observations}
    return result


def observation(epoch=2):
    return {
        "stationID": "TEST1",
        "tz": "Indian/Mauritius",
        "lat": -20.1,
        "lon": 57.5,
        "epoch": epoch,
    }


class CliTests(unittest.TestCase):
    def test_subcommands_parse(self):
        parser = build_parser()
        download = parser.parse_args(["download", "--record-type", "daily", "--station-id", "TEST1"])
        self.assertEqual(download.command, "download")
        self.assertEqual(download.record_type, "daily")
        self.assertEqual(
            parser.parse_args(["metadata-to-gpkg", "data", "stations.gpkg"]).command,
            "metadata-to-gpkg",
        )
        self.assertEqual(
            parser.parse_args(
                ["observations-to-parquet", "--record-type", "hourly", "data", "observations.parquet"]
            ).command,
            "observations-to-parquet",
        )

    def test_record_type_is_required(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["download", "--station-id", "TEST1"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["observations-to-parquet", "data", "observations.parquet"])

    def test_each_record_type_selects_its_endpoint(self):
        for record_type in ("daily", "hourly", "all"):
            with self.subTest(record_type=record_type), tempfile.TemporaryDirectory() as directory:
                session = Mock()
                session.get.side_effect = [response([])]
                download_station("TEST1", Path(directory), "secret", session, record_type)
                self.assertEqual(session.get.call_args.args[0], f"{API_BASE_URL}/{record_type}")

    def test_writes_metadata_from_first_observation_and_walks_backwards(self):
        session = Mock()
        session.get.side_effect = [response([observation()]), response([])]
        with tempfile.TemporaryDirectory() as directory, patch("wunderground_pws.cli.date") as mocked_date:
            mocked_date.today.return_value = date(2026, 9, 24)
            mocked_date.side_effect = date
            output = Path(directory)
            download_station("TEST1", output, "secret", session, "daily")
            self.assertEqual(
                json.loads((output / "TEST1.metadata.json").read_text()),
                {"stationID": "TEST1", "tz": "Indian/Mauritius", "lat": -20.1, "lon": 57.5},
            )
            self.assertEqual(len((output / "TEST1.daily.jsonl").read_text().splitlines()), 1)
        first = session.get.call_args_list[0].kwargs["params"]
        second = session.get.call_args_list[1].kwargs["params"]
        self.assertEqual((first["startDate"], first["endDate"]), ("20260826", "20260924"))
        self.assertEqual((second["startDate"], second["endDate"]), ("20260727", "20260825"))

    def test_repairs_invalid_metadata_and_deduplicates_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "TEST1.metadata.json").write_text("{}\n")
            (output / "TEST1.hourly.jsonl").write_text('{"stationID":"TEST1","epoch":2}\n')
            session = Mock()
            session.get.side_effect = [response([observation()]), response([])]
            download_station("TEST1", output, "secret", session, "hourly")
            self.assertEqual(json.loads((output / "TEST1.metadata.json").read_text())["stationID"], "TEST1")
            self.assertEqual(len((output / "TEST1.hourly.jsonl").read_text().splitlines()), 1)

    def test_preserves_valid_metadata(self):
        original = {"stationID": "TEST1", "tz": "Old/Zone", "lat": 1.0, "lon": 2.0}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "TEST1.metadata.json").write_text(json.dumps(original))
            session = Mock()
            session.get.side_effect = [response([observation()]), response([])]
            download_station("TEST1", output, "secret", session, "all")
            self.assertEqual(json.loads((output / "TEST1.metadata.json").read_text()), original)

    def test_no_observations_does_not_create_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            session = Mock()
            session.get.side_effect = [response([])]
            download_station("TEST1", output, "secret", session, "daily")
            self.assertFalse((output / "TEST1.metadata.json").exists())

    def test_record_types_use_independent_output_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "TEST1.daily.jsonl").write_text('{"stationID":"TEST1","epoch":2}\n')
            session = Mock()
            session.get.side_effect = [response([observation()]), response([])]
            download_station("TEST1", output, "secret", session, "hourly")
            self.assertEqual(len((output / "TEST1.daily.jsonl").read_text().splitlines()), 1)
            self.assertEqual(len((output / "TEST1.hourly.jsonl").read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
