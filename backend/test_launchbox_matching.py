import unittest
import io
import zipfile

from bs4 import BeautifulSoup
from fastapi import HTTPException

from main import choose_launchbox_candidate, normalize_launchbox_detail_url, parse_launchbox_metadata_zip_entries, section_images_from_titles


class LaunchboxCandidateSelectionTests(unittest.TestCase):
    def test_prefers_exact_title_and_platform(self):
        candidates = [
            {"title": "God of War", "platform": "PlayStation 2", "href": "/games/details/1"},
            {"title": "God of War", "platform": "PlayStation 4", "href": "/games/details/2"},
            {"title": "God of War II", "platform": "PlayStation 2", "href": "/games/details/3"},
        ]

        chosen = choose_launchbox_candidate(candidates, "God of War", "PlayStation 2")
        self.assertEqual(chosen["href"], "/games/details/1")

    def test_raises_ambiguity_for_close_non_exact_matches(self):
        candidates = [
            {"title": "Crash Bandicoot 2", "platform": "PlayStation 2", "href": "/games/details/a"},
            {"title": "Crash Bandicoot 3", "platform": "PlayStation 2", "href": "/games/details/b"},
        ]

        with self.assertRaises(HTTPException) as context:
            choose_launchbox_candidate(candidates, "Crash Bandicoot", "PlayStation 2")

        self.assertEqual(context.exception.status_code, 409)

    def test_rejects_low_confidence_match(self):
        candidates = [
            {"title": "FIFA 09", "platform": "PlayStation 2", "href": "/games/details/9"},
            {"title": "Madden NFL 10", "platform": "PlayStation 2", "href": "/games/details/10"},
        ]

        with self.assertRaises(HTTPException) as context:
            choose_launchbox_candidate(candidates, "Silent Hill 2", "PlayStation 2")

        self.assertEqual(context.exception.status_code, 404)

    def test_missing_art_section_returns_empty_list(self):
        html = """
        <html>
            <body>
                <article>
                    <h2>Overview</h2>
                    <p>No box art sections on this page.</p>
                </article>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        images = section_images_from_titles(soup, ["Box - Front", "Disc"])
        self.assertEqual(images, [])

    def test_normalize_launchbox_detail_url_accepts_valid_link(self):
        normalized = normalize_launchbox_detail_url(
            "https://gamesdb.launchbox-app.com/games/details/1234-gran-turismo-4"
        )
        self.assertEqual(
            normalized,
            "https://gamesdb.launchbox-app.com/games/details/1234-gran-turismo-4",
        )

    def test_normalize_launchbox_detail_url_rejects_non_launchbox_host(self):
        with self.assertRaises(HTTPException) as context:
            normalize_launchbox_detail_url("https://example.com/games/details/1234-gran-turismo-4")
        self.assertEqual(context.exception.status_code, 400)

    def test_normalize_launchbox_detail_url_rejects_non_detail_page(self):
        with self.assertRaises(HTTPException) as context:
            normalize_launchbox_detail_url("https://gamesdb.launchbox-app.com/games/results?search=gran+turismo")
        self.assertEqual(context.exception.status_code, 400)

        def test_parse_launchbox_metadata_zip_entries_extracts_basic_fields(self):
                xml_payload = """
                <LaunchBox>
                    <Game>
                        <Title>Gran Turismo 4</Title>
                        <Platform>PlayStation 2</Platform>
                        <ReleaseDate>December 28, 2004</ReleaseDate>
                        <Genre>Racing, Simulation</Genre>
                        <Publisher>Sony Computer Entertainment</Publisher>
                        <ESRB>T</ESRB>
                    </Game>
                </LaunchBox>
                """.strip()

                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                        archive.writestr("Games.xml", xml_payload)

                parsed = parse_launchbox_metadata_zip_entries(buffer.getvalue())
                self.assertEqual(len(parsed), 1)
                self.assertEqual(parsed[0]["title"], "Gran Turismo 4")
                self.assertEqual(parsed[0]["platform"], "PlayStation 2")
                self.assertEqual(parsed[0]["release_date"], "2004-12-28")
                self.assertIn("Racing", parsed[0]["gameGenres"])
                self.assertIn("Sony Computer Entertainment", parsed[0]["publishers"])


if __name__ == "__main__":
    unittest.main()
