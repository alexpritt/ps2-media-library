import unittest
from unittest.mock import patch

from fastapi import HTTPException

import main


class CoverPriorityTests(unittest.TestCase):
    def test_prefers_launchbox_cover_when_present(self):
        with patch.object(main, "fetch_igdb_cover_options", return_value=["igdb-cover"]), patch.object(
            main,
            "fetch_libretro_cover_image",
            return_value="libretro-cover",
        ):
            cover, source = main.resolve_cover_image_with_priority(
                "God of War",
                "PlayStation 2",
                "launchbox-cover",
            )

        self.assertEqual(cover, "launchbox-cover")
        self.assertEqual(source, "launchbox")

    def test_uses_igdb_before_libretro_when_launchbox_missing(self):
        with patch.object(main, "fetch_igdb_cover_options", return_value=["igdb-cover"]), patch.object(
            main,
            "fetch_libretro_cover_image",
            return_value="libretro-cover",
        ):
            cover, source = main.resolve_cover_image_with_priority(
                "God of War",
                "PlayStation 2",
                None,
            )

        self.assertEqual(cover, "igdb-cover")
        self.assertEqual(source, "igdb")

    def test_falls_back_to_libretro_when_others_missing(self):
        with patch.object(main, "fetch_igdb_cover_options", return_value=[]), patch.object(
            main,
            "fetch_libretro_cover_image",
            return_value="libretro-cover",
        ):
            cover, source = main.resolve_cover_image_with_priority(
                "God of War",
                "PlayStation 2",
                None,
            )

        self.assertEqual(cover, "libretro-cover")
        self.assertEqual(source, "libretro")

    def test_cover_art_options_follow_launchbox_igdb_libretro_order(self):
        with patch.object(main, "fetch_launchbox_game_art_options", return_value={"options": ["lb1", "lb2"]}), patch.object(
            main,
            "fetch_igdb_cover_options",
            return_value=["igdb1", "lb2"],
        ), patch.object(main, "fetch_libretro_cover_image", return_value="lib1"):
            payload = main.fetch_game_art_options_with_fallback("God of War", "PlayStation 2", "cover")

        self.assertEqual(payload["options"], ["lb1", "lb2", "igdb1", "lib1"])
        self.assertEqual(payload["data_source"], "launchbox-with-fallbacks")

    def test_launchbox_missing_disc_and_spine_remain_empty(self):
        launchbox_payload = {
            "title": "Uncharted 2: Among Thieves",
            "platform": "PlayStation 3",
            "coverImage": "launchbox-cover",
            "discImage": None,
            "spineImage": None,
            "publishers": [],
            "gameGenres": [],
            "notes": None,
            "rating": None,
            "players": None,
            "cooperative": None,
            "release_date": None,
            "year_released": None,
        }

        with patch.object(main, "launchbox_detail_payload", return_value=launchbox_payload), patch.object(
            main,
            "resolve_cover_image_with_priority",
            return_value=("launchbox-cover", "launchbox"),
        ):
            payload = main.fetch_game_data_with_fallback("Uncharted 2: Among Thieves", "PlayStation 3")

        self.assertEqual(payload["coverImage"], "launchbox-cover")
        self.assertIsNone(payload["discImage"])
        self.assertIsNone(payload["spineImage"])
        self.assertIn("disc", payload["launchbox_unavailable_resources"])
        self.assertIn("spine", payload["launchbox_unavailable_resources"])

    def test_art_options_returns_status_when_launchbox_unavailable(self):
        with patch.object(
            main,
            "fetch_launchbox_game_art_options",
            side_effect=HTTPException(status_code=404, detail="No LaunchBox art options found for that category."),
        ):
            payload = main.fetch_game_art_options_with_fallback("Resistance 3", "PlayStation 3", "spine")

        self.assertEqual(payload["options"], [])
        self.assertIn("LaunchBox has no spine art", payload["status_message"])


if __name__ == "__main__":
    unittest.main()
