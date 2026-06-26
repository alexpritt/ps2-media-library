import unittest

from bs4 import BeautifulSoup
from fastapi import HTTPException

from main import choose_launchbox_candidate, section_images_from_titles


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


if __name__ == "__main__":
    unittest.main()
