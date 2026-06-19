from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from typing import Optional

from sqlmodel import Session, select

from main import MediaItem, create_db_and_tables, engine, ensure_release_date_column

WIKI_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "ps2-media-library-detail-refresh/1.0"
REQUEST_DELAY_SECONDS = 0.45
MAX_RETRIES = 4


def request_json(params: dict[str, str]) -> Optional[dict]:
    query = urllib.parse.urlencode(params)
    url = f"{WIKI_API}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except BaseException:
            if attempt == MAX_RETRIES - 1:
                return None
            time.sleep(1.2 * (attempt + 1))

    return None


def normalize(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum() or ch.isspace()).strip()


def sentence_split(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]


def truncate(text: str, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def search_best_title(item: MediaItem) -> Optional[str]:
    search_terms = []
    if item.category == "Games":
        search_terms.append(f"{item.title} video game")
    else:
        artist = item.artist or ""
        search_terms.append(f"{item.title} album {artist}".strip())
    search_terms.append(item.title)

    wanted = normalize(item.title)

    for term in search_terms:
        payload = request_json(
            {
                "action": "query",
                "list": "search",
                "srsearch": term,
                "srlimit": "6",
                "format": "json",
            }
        )
        time.sleep(REQUEST_DELAY_SECONDS)
        if not payload:
            continue

        results = payload.get("query", {}).get("search", [])
        if not isinstance(results, list) or not results:
            continue

        for result in results:
            title = str(result.get("title", "")).strip()
            if wanted and normalize(title).startswith(wanted):
                return title

        first_title = str(results[0].get("title", "")).strip()
        if first_title:
            return first_title

    return None


def fetch_extract(page_title: str) -> Optional[str]:
    payload = request_json(
        {
            "action": "query",
            "prop": "extracts",
            "explaintext": "1",
            "titles": page_title,
            "exchars": "3600",
            "format": "json",
        }
    )
    time.sleep(REQUEST_DELAY_SECONDS)
    if not payload:
        return None

    pages = payload.get("query", {}).get("pages", {})
    if not isinstance(pages, dict):
        return None

    for page in pages.values():
        extract = page.get("extract")
        if isinstance(extract, str) and extract.strip():
            return extract.strip()

    return None


def pick_game_summary(item: MediaItem, extract: str) -> str:
    sentences = sentence_split(extract)
    if not sentences:
        return item.notes or "No description available."

    developer = None
    for sentence in sentences[:5]:
        match = re.search(r"developed by ([^.]+?)(?: and published| and|,|\.)", sentence, re.IGNORECASE)
        if match:
            developer = truncate(match.group(1).strip(), 80)
            break

    plot_sentence = None
    for sentence in sentences:
        lower = sentence.lower()
        if any(keyword in lower for keyword in ["plot", "story", "follows", "player", "protagonist", "set in"]):
            plot_sentence = sentence
            break

    if plot_sentence is None:
        plot_sentence = sentences[1] if len(sentences) > 1 else sentences[0]

    dev_text = f"Developer: {developer}. " if developer else ""
    return truncate(f"{dev_text}Plot: {plot_sentence}", 260)


def pick_music_summary(item: MediaItem, extract: str) -> str:
    sentences = sentence_split(extract)
    if not sentences:
        return item.notes or "No description available."

    album_sentence = sentences[0]

    meaning_sentence = None
    meaning_keywords = [
        "meaning",
        "theme",
        "concept",
        "lyric",
        "lyrics",
        "inspired",
        "said",
        "described",
        "about",
    ]
    for sentence in sentences[1:18]:
        lower = sentence.lower()
        if any(keyword in lower for keyword in meaning_keywords):
            meaning_sentence = sentence
            break

    if meaning_sentence is None:
        artist_name = (item.artist or "artist").strip()
        meaning_sentence = f"Public commentary from {artist_name} on the album's meaning is limited in widely available sources."

    return truncate(f"Album: {album_sentence} Meaning: {meaning_sentence}", 320)


def refresh_item(item: MediaItem) -> bool:
    page_title = search_best_title(item)
    if not page_title:
        return False

    extract = fetch_extract(page_title)
    if not extract:
        return False

    if item.category == "Games":
        item.notes = pick_game_summary(item, extract)
    else:
        item.notes = pick_music_summary(item, extract)

    return True


def main() -> None:
    create_db_and_tables()
    ensure_release_date_column()

    updated = 0
    skipped = 0

    with Session(engine) as session:
        items = session.exec(select(MediaItem)).all()
        total = len(items)

        for index, item in enumerate(items, start=1):
            print(f"[{index}/{total}] Refreshing {item.category}: {item.title}")
            ok = refresh_item(item)
            if ok:
                session.add(item)
                updated += 1
                print("  -> updated")
            else:
                skipped += 1
                print("  -> skipped")

        session.commit()

    print(f"Detail refresh complete. Updated: {updated}, Skipped: {skipped}, Total: {updated + skipped}")


if __name__ == "__main__":
    main()
