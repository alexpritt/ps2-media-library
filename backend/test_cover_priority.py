import unittest
from unittest.mock import patch

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
        self.assertEqual(payload["data_source"], "launchbox-igdb-libretro")


if __name__ == "__main__":
    unittest.main()
