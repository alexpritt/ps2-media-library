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
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "ps2-media-library-date-refresh/1.0 (personal)"
REQUEST_DELAY = 0.55
MAX_RETRIES = 3


def request_json(url: str, params: dict[str, str]) -> Optional[dict]:
    full_url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT})
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except BaseException as exc:
            if attempt == MAX_RETRIES - 1:
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def warm_up_ssl() -> None:
    """Pre-load the Windows SSL cert store with a throwaway request."""
    try:
        req = urllib.request.Request(
            "https://en.wikipedia.org/w/api.php?action=query&format=json",
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=15):
            pass
    except BaseException:
        pass
    time.sleep(0.3)


def search_wikipedia_title(item: MediaItem) -> Optional[str]:
    """Return the best-matching Wikipedia page title for the media item."""
    if item.category == "Games":
        terms = [f"{item.title} video game", item.title]
    else:
        artist = item.artist or ""
        terms = [f"{item.title} album {artist}".strip(), item.title]

    wanted = item.title.lower()

    for term in terms:
        payload = request_json(WIKI_API, {
            "action": "query",
            "list": "search",
            "srsearch": term,
            "srlimit": "6",
            "format": "json",
        })
        time.sleep(REQUEST_DELAY)
        if not payload:
            continue
        results = payload.get("query", {}).get("search", [])
        if not results:
            continue

        # Prefer a result whose title starts with the item title
        for result in results:
            title = str(result.get("title", "")).strip()
            if title.lower().startswith(wanted):
                return title

        # Fall back to first result
        first = str(results[0].get("title", "")).strip()
        if first:
            return first

    return None


def get_wikidata_id(page_title: str) -> Optional[str]:
    """Get the Wikidata QID (e.g. Q12345) for a Wikipedia page title."""
    payload = request_json(WIKI_API, {
        "action": "query",
        "prop": "pageprops",
        "ppprop": "wikibase_item",
        "titles": page_title,
        "format": "json",
    })
    time.sleep(REQUEST_DELAY)
    if not payload:
        return None
    pages = payload.get("query", {}).get("pages", {})
    for page in pages.values():
        qid = page.get("pageprops", {}).get("wikibase_item")
        if qid:
            return qid
    return None


def get_wikidata_release_date(qid: str) -> Optional[str]:
    """
    Query Wikidata for P577 (publication date). Returns YYYY-MM-DD.
    Precision: 11=day, 10=month, 9=year. We pad missing parts with 01.
    """
    payload = request_json(WIKIDATA_API, {
        "action": "wbgetentities",
        "ids": qid,
        "props": "claims",
        "format": "json",
    })
    time.sleep(REQUEST_DELAY)
    if not payload:
        return None

    entities = payload.get("entities", {})
    entity = entities.get(qid, {})
    claims = entity.get("claims", {})

    # P577 = publication date
    p577 = claims.get("P577", [])
    if not p577:
        # P571 = inception (sometimes used for games)
        p577 = claims.get("P571", [])
    if not p577:
        return None

    # Pick the earliest preferred/normal rank claim
    candidates = []
    for claim in p577:
        rank = claim.get("rank", "normal")
        snak = claim.get("mainsnak", {})
        if snak.get("snaktype") != "value":
            continue
        val = snak.get("datavalue", {}).get("value", {})
        if not isinstance(val, dict):
            continue
        time_str = val.get("time", "")
        precision = val.get("precision", 9)
        # time_str format: +YYYY-MM-DDTHH:MM:SSZ
        match = re.match(r"[+-](\d{4})-(\d{2})-(\d{2})", time_str)
        if not match:
            continue
        year, month, day = match.groups()
        year, month, day = int(year), int(month), int(day)
        if year < 1970:
            continue
        candidates.append((rank, precision, year, month, day))

    if not candidates:
        return None

    # Prefer preferred rank, then highest precision, then earliest date
    def sort_key(c):
        rank_order = {"preferred": 0, "normal": 1, "deprecated": 2}
        return (rank_order.get(c[0], 1), -c[1], c[2], c[3], c[4])

    candidates.sort(key=sort_key)
    _, precision, year, month, day = candidates[0]

    if precision >= 11:  # day precision
        return f"{year:04d}-{month:02d}-{day:02d}"
    elif precision >= 10:  # month precision
        return f"{year:04d}-{month:02d}-01"
    else:  # year precision
        return f"{year:04d}-01-01"


def fetch_date_for_item(item: MediaItem) -> Optional[str]:
    title = search_wikipedia_title(item)
    if not title:
        return None
    qid = get_wikidata_id(title)
    if not qid:
        return None
    return get_wikidata_release_date(qid)


def main() -> None:
    create_db_and_tables()
    ensure_release_date_column()

    print("Warming up SSL connection...")
    warm_up_ssl()

    updated = 0
    skipped = 0

    with Session(engine) as session:
        items = session.exec(select(MediaItem)).all()
        total = len(items)

        for index, item in enumerate(items, start=1):
            print(f"[{index}/{total}] {item.category}: {item.title}", end=" ... ", flush=True)
            date_str = fetch_date_for_item(item)

            if date_str:
                item.release_date = date_str
                item.year_released = int(date_str[:4])
                session.add(item)
                updated += 1
                print(date_str)
            else:
                skipped += 1
                print("skipped")

        session.commit()

    print(f"\nDone. Updated: {updated}, Skipped: {skipped}, Total: {total}")


if __name__ == "__main__":
    main()


WIKI_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "ps2-media-library-date-refresh/1.0"
REQUEST_DELAY_SECONDS = 0.5
MAX_RETRIES = 3

# Patterns to extract dates from Wikipedia infobox revisions
# Matches: "2004-03-22", "March 22, 2004", "22 March 2004", "22 March, 2004"
MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def request_json(params: dict[str, str]) -> Optional[dict]:
    query = urllib.parse.urlencode(params)
    url = f"{WIKI_API}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except BaseException:
            if attempt == MAX_RETRIES - 1:
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def search_page_title(item: MediaItem) -> Optional[str]:
    """Find the most relevant Wikipedia page title for this media item."""
    if item.category == "Games":
        terms = [f"{item.title} video game", item.title]
    else:
        artist = item.artist or ""
        terms = [f"{item.title} album {artist}".strip(), f"{item.title} {artist}".strip(), item.title]

    wanted_lower = item.title.lower()

    for term in terms:
        payload = request_json({
            "action": "query",
            "list": "search",
            "srsearch": term,
            "srlimit": "6",
            "format": "json",
        })
        time.sleep(REQUEST_DELAY_SECONDS)
        if not payload:
            continue
        results = payload.get("query", {}).get("search", [])
        if not isinstance(results, list) or not results:
            continue
        for result in results:
            title = str(result.get("title", "")).strip()
            if title.lower().startswith(wanted_lower):
                return title
        # Fall back to first result on second term pass
        first = str(results[0].get("title", "")).strip()
        if first:
            return first

    return None


def fetch_page_revisions(page_title: str) -> Optional[str]:
    """Fetch the raw wikitext of a page (first ~8000 bytes) to parse infobox dates."""
    payload = request_json({
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "rvsection": "0",
        "titles": page_title,
        "format": "json",
    })
    time.sleep(REQUEST_DELAY_SECONDS)
    if not payload:
        return None
    pages = payload.get("query", {}).get("pages", {})
    for page in pages.values():
        revisions = page.get("revisions", [])
        if revisions:
            slots = revisions[0].get("slots", {})
            main = slots.get("main", {})
            content = main.get("*", "") or main.get("content", "")
            if content:
                return content[:12000]
    return None


def parse_date_from_wikitext(wikitext: str, item: MediaItem) -> Optional[str]:
    """Extract release date from wikitext infobox. Returns YYYY-MM-DD or None."""

    # ---- Strategy 1: {{Start date|YYYY|MM|DD}} or {{Film date|YYYY|MM|DD}} style ----
    start_date_match = re.search(
        r"\{\{(?:Start date|Film date|Birth date)[^}]*?\|(\d{4})\|(\d{1,2})\|(\d{1,2})",
        wikitext, re.IGNORECASE
    )
    if start_date_match:
        y, m, d = start_date_match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"

    # ---- Strategy 2: released = {{Date|YYYY|MM|DD}} ----
    date_template = re.search(
        r"\{\{Date\|(\d{4})\|(\d{1,2})\|(\d{1,2})",
        wikitext, re.IGNORECASE
    )
    if date_template:
        y, m, d = date_template.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"

    # ---- Strategy 3: released = YYYY-MM-DD plain ----
    iso_match = re.search(
        r"(?:released|release[_ ]date|release)\s*=\s*(\d{4}-\d{2}-\d{2})",
        wikitext, re.IGNORECASE
    )
    if iso_match:
        return iso_match.group(1)

    # ---- Strategy 4: released = Month DD, YYYY or DD Month YYYY ----
    month_name_pattern = "|".join(MONTH_NAMES.keys())
    mdy_match = re.search(
        rf"(?:released|release[_ ]date|release)\s*=\s*(?:\[\[)?({month_name_pattern})\s+(\d{{1,2}}),?\s+(\d{{4}})",
        wikitext, re.IGNORECASE
    )
    if mdy_match:
        mon_str, day_str, year_str = mdy_match.groups()
        m = MONTH_NAMES.get(mon_str.lower())
        if m:
            return f"{year_str}-{m:02d}-{int(day_str):02d}"

    dmy_match = re.search(
        rf"(?:released|release[_ ]date|release)\s*=\s*(?:\[\[)?(\d{{1,2}})\s+({month_name_pattern})\s+(\d{{4}})",
        wikitext, re.IGNORECASE
    )
    if dmy_match:
        day_str, mon_str, year_str = dmy_match.groups()
        m = MONTH_NAMES.get(mon_str.lower())
        if m:
            return f"{year_str}-{m:02d}-{int(day_str):02d}"

    # ---- Strategy 5: Year-only fallback from infobox ----
    year_only = re.search(
        r"(?:released|release[_ ]date|release)\s*=\s*(?:\[\[)?(\d{4})",
        wikitext, re.IGNORECASE
    )
    if year_only:
        # Return Jan 1 of year as sentinel so we at least have year_released
        return f"{year_only.group(1)}-01-01"

    return None


def parse_date_from_extract(extract: str) -> Optional[str]:
    """Try to extract a release date from the plain-text Wikipedia extract."""
    month_name_pattern = "|".join(MONTH_NAMES.keys())

    # "released on March 22, 2004" / "released March 22, 2004"
    mdy = re.search(
        rf"release[d\s]+(?:on\s+)?({month_name_pattern})\s+(\d{{1,2}}),?\s+(\d{{4}})",
        extract, re.IGNORECASE
    )
    if mdy:
        mon_str, day_str, year_str = mdy.groups()
        m = MONTH_NAMES.get(mon_str.lower())
        if m:
            return f"{year_str}-{m:02d}-{int(day_str):02d}"

    # "released on 22 March 2004"
    dmy = re.search(
        rf"release[d\s]+(?:on\s+)?(\d{{1,2}})\s+({month_name_pattern})\s+(\d{{4}})",
        extract, re.IGNORECASE
    )
    if dmy:
        day_str, mon_str, year_str = dmy.groups()
        m = MONTH_NAMES.get(mon_str.lower())
        if m:
            return f"{year_str}-{m:02d}-{int(day_str):02d}"

    return None


def fetch_plain_extract(page_title: str) -> Optional[str]:
    payload = request_json({
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "titles": page_title,
        "exchars": "2000",
        "format": "json",
    })
    time.sleep(REQUEST_DELAY_SECONDS)
    if not payload:
        return None
    pages = payload.get("query", {}).get("pages", {})
    for page in pages.values():
        extract = page.get("extract")
        if isinstance(extract, str) and extract.strip():
            return extract.strip()
    return None


def refresh_date(item: MediaItem) -> Optional[str]:
    """Return a YYYY-MM-DD string for the best found release date, or None."""
    page_title = search_page_title(item)
    if not page_title:
        return None

    # Try wikitext first (most reliable for structured dates)
    wikitext = fetch_page_revisions(page_title)
    if wikitext:
        date = parse_date_from_wikitext(wikitext, item)
        if date:
            return date

    # Fall back to plain extract
    extract = fetch_plain_extract(page_title)
    if extract:
        date = parse_date_from_extract(extract)
        if date:
            return date

    return None


def main() -> None:
    create_db_and_tables()
    ensure_release_date_column()

    updated = 0
    skipped = 0
    year_only = 0

    with Session(engine) as session:
        items = session.exec(select(MediaItem)).all()
        total = len(items)

        for index, item in enumerate(items, start=1):
            print(f"[{index}/{total}] {item.category}: {item.title}", end=" ... ")
            date_str = refresh_date(item)

            if date_str:
                # Detect year-only placeholder (Jan 1) vs full date
                is_year_only = date_str.endswith("-01-01")
                item.release_date = date_str
                item.year_released = int(date_str[:4])
                session.add(item)
                if is_year_only:
                    year_only += 1
                    print(f"year only → {date_str}")
                else:
                    updated += 1
                    print(f"✓ {date_str}")
            else:
                skipped += 1
                print("skipped")

        session.commit()

    print(
        f"\nRelease date refresh complete."
        f" Full dates: {updated}, Year-only: {year_only}, Skipped: {skipped}, Total: {total}"
    )


if __name__ == "__main__":
    main()
