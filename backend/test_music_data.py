import unittest
from unittest.mock import patch
from datetime import datetime, timezone

import main
from fastapi import HTTPException


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HTTPException(status_code=self.status_code, detail="request failed")


class DeezerMusicDataTests(unittest.TestCase):
    def test_fetch_music_album_data_includes_detail_fields(self):
        def fake_get(url, timeout=20, headers=None):
            if "search/album" in url:
                return FakeResponse(
                    {
                        "data": [
                            {
                                "id": 42,
                                "title": "Discovery",
                                "artist": {"name": "Daft Punk"},
                                "cover_medium": "https://images.example/discovery.jpg",
                            },
                            {
                                "id": 7,
                                "title": "Homework",
                                "artist": {"name": "Daft Punk"},
                                "cover_medium": "https://images.example/homework.jpg",
                            },
                        ]
                    }
                )
            if url.endswith("/album/42"):
                return FakeResponse(
                    {
                        "title": "Discovery",
                        "artist": {"name": "Daft Punk"},
                        "release_date": "2001-03-12",
                        "genres": {"data": [{"name": "Electronic"}]},
                        "cover_xl": "https://images.example/discovery-xl.jpg",
                    }
                )
            raise AssertionError(f"Unexpected URL {url}")

        with patch.object(main.requests, "get", side_effect=fake_get), patch.object(
            main, "fetch_image_data_uri", return_value="data:image/jpeg;base64,abc"
        ):
            data = main.fetch_music_album_data("Discovery", "Daft Punk")

        self.assertEqual(data["title"], "Discovery")
        self.assertEqual(data["artist"], "Daft Punk")
        self.assertEqual(data["genre"], "Electronic")
        self.assertEqual(data["release_date"], "2001-03-12")
        self.assertEqual(data["year_released"], 2001)
        self.assertEqual(data["coverImage"], "data:image/jpeg;base64,abc")

    def test_fetch_music_data_endpoint_trims_inputs(self):
        main.admin_tokens["unit-test-token"] = True
        auth_header = "Bearer " + "unit-test-token"
        try:
            with patch.object(
                main,
                "fetch_music_album_data",
                return_value={"title": "Discovery", "artist": "Daft Punk", "coverImage": "data:image/jpeg;base64,abc"},
            ) as fetch_mock:
                data = main.fetch_music_data(
                    main.DeezerMusicDataRequest(title="  Discovery  ", artist="  Daft Punk  "),
                    authorization=auth_header,
                )
        finally:
            main.admin_tokens.pop("unit-test-token", None)

        fetch_mock.assert_called_once_with("Discovery", "Daft Punk")
        self.assertEqual(data["title"], "Discovery")

    def test_fetch_wishlist_price_data_returns_price_fields_for_music_item(self):
        main.admin_tokens["unit-test-token"] = True
        auth_header = "Bearer " + "unit-test-token"
        try:
            with patch.object(
                main,
                "fetch_price_data_for_item",
                return_value={"kind": "music", "averageStandard": {"value": 42.0, "url": "https://example.test"}},
            ) as fetch_mock, patch.object(
                main,
                "utc_now",
                return_value=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            ):
                data = main.fetch_wishlist_item_price_data(
                    main.WishlistPriceFetchRequest(title="  Discovery  ", category="Music", artist="  Daft Punk  "),
                    authorization=auth_header,
                )
        finally:
            main.admin_tokens.pop("unit-test-token", None)

        fetch_mock.assert_called_once()
        self.assertEqual(data.title, "Discovery")
        self.assertEqual(data.artist, "Daft Punk")
        self.assertIn('"kind":"music"', data.price_data_json or "")
        self.assertEqual(data.price_last_fetched_at, "2026-01-02T03:04:05Z")


if __name__ == "__main__":
    unittest.main()
