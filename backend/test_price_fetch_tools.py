import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import HTTPException

import main


class PriceFetchToolEndpointTests(unittest.TestCase):
    def test_fetch_game_price_data_endpoint_trims_inputs(self):
        main.admin_tokens["unit-test-token"] = True
        auth_header = "Bearer " + "unit-test-token"
        try:
            with patch.object(
                main,
                "fetch_pricecharting_price_data",
                return_value={"kind": "game", "average": {"cib": {"value": 42.0, "url": "https://example.com/game"}}},
            ) as fetch_mock, patch.object(
                main,
                "utc_now",
                return_value=datetime(2026, 7, 1, 5, 0, 0, tzinfo=timezone.utc),
            ):
                data = main.fetch_game_price_data(
                    main.PriceChartingPriceDataRequest(title="  God of War  ", platform="  PlayStation 2  "),
                    authorization=auth_header,
                )
        finally:
            main.admin_tokens.pop("unit-test-token", None)

        fetch_mock.assert_called_once_with("God of War", "PlayStation 2")
        self.assertEqual(
            data,
            {
                "title": "God of War",
                "platform": "PlayStation 2",
                "price_data_json": '{"kind":"game","average":{"cib":{"value":42.0,"url":"https://example.com/game"}}}',
                "price_last_fetched_at": "2026-07-01T05:00:00Z",
            },
        )

    def test_fetch_music_price_data_endpoint_trims_inputs(self):
        main.admin_tokens["unit-test-token"] = True
        auth_header = "Bearer " + "unit-test-token"
        try:
            with patch.object(
                main,
                "fetch_discogs_price_data",
                return_value={"kind": "music", "average": {"standard": {"value": 18.0, "url": "https://example.com/album"}}},
            ) as fetch_mock, patch.object(
                main,
                "utc_now",
                return_value=datetime(2026, 7, 1, 5, 1, 2, tzinfo=timezone.utc),
            ):
                data = main.fetch_music_price_data(
                    main.DiscogsPriceDataRequest(title="  Discovery  ", artist="  Daft Punk  "),
                    authorization=auth_header,
                )
        finally:
            main.admin_tokens.pop("unit-test-token", None)

        fetch_mock.assert_called_once_with("Discovery", "Daft Punk")
        self.assertEqual(
            data,
            {
                "title": "Discovery",
                "artist": "Daft Punk",
                "price_data_json": '{"kind":"music","average":{"standard":{"value":18.0,"url":"https://example.com/album"}}}',
                "price_last_fetched_at": "2026-07-01T05:01:02Z",
            },
        )

    def test_fetch_game_price_data_endpoint_requires_platform(self):
        main.admin_tokens["unit-test-token"] = True
        auth_header = "Bearer " + "unit-test-token"
        try:
            with self.assertRaises(HTTPException) as context:
                main.fetch_game_price_data(
                    main.PriceChartingPriceDataRequest(title="Title", platform=" "),
                    authorization=auth_header,
                )
        finally:
            main.admin_tokens.pop("unit-test-token", None)

        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
