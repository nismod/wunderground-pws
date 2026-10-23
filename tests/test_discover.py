import unittest
from unittest.mock import Mock

from wunderground_pws.discover import find_stations, geocode_place, validate_bbox


def response(payload):
    result = Mock()
    result.json.return_value = payload
    return result


class DiscoveryTests(unittest.TestCase):
    def test_tiles_are_deduplicated_and_points_clipped_to_bbox(self):
        time = "current-time"
        inside = {"id": "IMOKA3", "geometry": {"type": "Point", "coordinates": [57.484, -20.205]}}
        outside = {"id": "OUTSIDE", "geometry": {"type": "Point", "coordinates": [58.0, -20.205]}}
        session = Mock()
        session.get.side_effect = [
            response({"products": {"614": {"time": [time]}}}),
            response({time: {"features": [inside, outside, inside]}}),
        ]
        self.assertEqual(find_stations((57.483, -20.206, 57.485, -20.204), "key", session), ["IMOKA3"])
        call = session.get.call_args_list[1]
        self.assertEqual((call.kwargs["params"]["x"], call.kwargs["params"]["y"]), (1351, 1141))
        self.assertEqual(call.kwargs["params"]["time"], time)

    def test_place_bbox_order_and_invalid_bbox(self):
        session = Mock()
        session.get.return_value = response([{"boundingbox": ["-20.6", "-19.9", "57.3", "57.8"]}])
        self.assertEqual(geocode_place("Mauritius", session), (57.3, -20.6, 57.8, -19.9))
        with self.assertRaisesRegex(ValueError, "bbox"):
            validate_bbox((58, -20, 57, -19))

    def test_large_area_rejected_before_api_call(self):
        session = Mock()
        with self.assertRaisesRegex(ValueError, "narrow"):
            find_stations((-180, -80, 180, 80), "key", session)
        with self.assertRaisesRegex(ValueError, "positive"):
            find_stations((57.483, -20.206, 57.485, -20.204), "key", session, max_tiles=0)
        with self.assertRaisesRegex(ValueError, "current limit 1"):
            find_stations((57.47, -20.22, 57.49, -20.19), "key", session, max_tiles=1)
        session.get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
