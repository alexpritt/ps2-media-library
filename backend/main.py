from pathlib import Path
from typing import Dict, Iterator, List, Optional
import secrets
import base64
import os
import re
import unicodedata
from urllib.parse import quote, urljoin

import requests
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlmodel import Field, Session, SQLModel, create_engine, select

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(Path(__file__).parent / "media.db")))
FRONTEND_BUILD_DIR = Path(__file__).parent.parent / "frontend" / "build"
SUGGESTIONS_DIR = Path(__file__).parent.parent / "frontend" / "suggestions"

app = FastAPI(title="PS2 Media Library API")

ADMIN_PASSWORD = "foreverandalways"
admin_tokens: Dict[str, bool] = {}


def iter_file_range(file_path: Path, start: int, end: int, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    with file_path.open("rb") as file_obj:
        file_obj.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            read_size = min(chunk_size, remaining)
            data = file_obj.read(read_size)
            if not data:
                break
            remaining -= len(data)
            yield data

class MediaItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    category: str
    platform: Optional[str] = None
    genre: str
    genres: Optional[str] = None
    release_date: Optional[str] = None
    year_released: Optional[int] = None
    rating: Optional[str] = None
    players: Optional[int] = None
    cooperative: Optional[str] = None
    artist: Optional[str] = None
    publisher: Optional[str] = None
    format: Optional[str] = None
    region: Optional[str] = None
    cover_image: Optional[str] = None
    spine_image: Optional[str] = None
    disc_image: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None


class GameSystem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    system_id: str = Field(unique=True)
    name: str
    short_name: str
    logo: str
    logo_image: Optional[str] = None  # Base64 encoded image data


class AdminLoginRequest(SQLModel):
    password: str


class LaunchboxGameDataRequest(SQLModel):
    title: str
    platform: str
    item_id: Optional[int] = None


class BulkGamesRequest(SQLModel):
    items: List[str]


class BulkMusicRequest(SQLModel):
    items: List[str]


class SystemLogoDataRequest(SQLModel):
    name: str

engine = create_engine(f"sqlite:///{DATABASE_PATH}", echo=False, connect_args={"check_same_thread": False})

def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def ensure_release_date_column() -> None:
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(mediaitem)")).fetchall()
        has_release_date = any(column[1] == "release_date" for column in columns)
        if not has_release_date:
            connection.execute(text("ALTER TABLE mediaitem ADD COLUMN release_date VARCHAR"))


def ensure_rating_column() -> None:
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(mediaitem)")).fetchall()
        has_rating = any(column[1] == "rating" for column in columns)
        if not has_rating:
            connection.execute(text("ALTER TABLE mediaitem ADD COLUMN rating VARCHAR"))
            connection.execute(text("UPDATE mediaitem SET rating = 'RP' WHERE category = 'Games' AND (rating IS NULL OR rating = '')"))


def ensure_genres_column() -> None:
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(mediaitem)")).fetchall()
        has_genres = any(column[1] == "genres" for column in columns)
        if not has_genres:
            connection.execute(text("ALTER TABLE mediaitem ADD COLUMN genres VARCHAR"))
        connection.execute(
            text(
                "UPDATE mediaitem SET genres = genre WHERE (genres IS NULL OR genres = '') AND genre IS NOT NULL AND genre != ''"
            )
        )


def ensure_cooperative_column() -> None:
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(mediaitem)")).fetchall()
        has_cooperative = any(column[1] == "cooperative" for column in columns)
        if not has_cooperative:
            connection.execute(text("ALTER TABLE mediaitem ADD COLUMN cooperative VARCHAR"))


def ensure_disc_image_column() -> None:
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(mediaitem)")).fetchall()
        has_disc_image = any(column[1] == "disc_image" for column in columns)
        if not has_disc_image:
            connection.execute(text("ALTER TABLE mediaitem ADD COLUMN disc_image VARCHAR"))


def ensure_spine_image_column() -> None:
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(mediaitem)")).fetchall()
        has_spine_image = any(column[1] == "spine_image" for column in columns)
        if not has_spine_image:
            connection.execute(text("ALTER TABLE mediaitem ADD COLUMN spine_image VARCHAR"))


def normalize_game_title(title: str) -> str:
    normalized = re.sub(r"\s+", " ", title.strip())
    if not normalized:
        return normalized

    def capitalize_token(token: str) -> str:
        segments = re.split(r"([:-])", token)
        normalized_segments = []
        for segment in segments:
            if segment in {":", "-"}:
                normalized_segments.append(segment)
                continue
            if not segment:
                continue
            normalized_segments.append(segment[:1].upper() + segment[1:].lower())
        return "".join(normalized_segments)

    normalized = " ".join(capitalize_token(token) for token in normalized.split(" "))
    roman_numerals = {
        "Ii": "II",
        "Iii": "III",
        "Iv": "IV",
        "Vi": "VI",
        "Vii": "VII",
        "Viii": "VIII",
        "Ix": "IX",
        "Xi": "XI",
        "Xii": "XII",
        "Xiii": "XIII",
        "Xiv": "XIV",
        "Xv": "XV",
    }
    for source, target in roman_numerals.items():
        normalized = re.sub(rf"\b{source}\b", target, normalized)
    return normalized


def normalize_launchbox_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def normalize_title_for_match(value: str) -> str:
    # Normalize accents and punctuation so inputs like "Pokemon" still match "Pokemon".
    ascii_text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower().replace("&", " and ")
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def title_tokens(value: str) -> List[str]:
    return [token for token in normalize_title_for_match(value).split(" ") if token]


def normalize_esrb_rating(rating_str: Optional[str]) -> str:
    s = (rating_str or "").upper().strip()
    if "E10" in s or "EVERYONE 10" in s:
        return "E10+"
    if s.startswith("AO") or "ADULTS ONLY" in s:
        return "AO"
    if s.startswith("M") or "MATURE" in s:
        return "M"
    if s.startswith("T") or "TEEN" in s:
        return "T"
    if s.startswith("E") or "EVERYONE" in s:
        return "E"
    return "RP"


def parse_launchbox_date(date_str: Optional[str]) -> Optional[str]:
    """Convert 'January 31, 1997' → '1997-01-31'."""
    if not date_str:
        return None
    import datetime as dt
    cleaned = date_str.strip()
    cleaned = re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", cleaned, flags=re.IGNORECASE)

    for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %Y", "%b %Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            parsed = dt.datetime.strptime(cleaned, fmt)
            if fmt in ("%B %Y", "%b %Y"):
                return f"{parsed.year}-{parsed.month:02d}-01"
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            pass
    year_m = re.search(r"\b(19|20)\d{2}\b", cleaned)
    if year_m:
        return f"{year_m.group(0)}-01-01"
    return None


def score_music_match(item: dict, artist: str, album: str) -> int:
    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9\s]", "", s.lower()).strip()

    ia = norm(item.get("artist", {}).get("name", "") if isinstance(item.get("artist"), dict) else item.get("artist", ""))
    iab = norm(item.get("title", ""))
    na, nab = norm(artist), norm(album)
    score = 0
    if na == ia:
        score += 100
    elif na in ia:
        score += 50
    if nab == iab:
        score += 100
    elif nab in iab:
        score += 40
    elif iab in nab:
        score += 20
    return score


def fetch_music_album_data(album: str, artist: str) -> dict:
    """Fetch album cover art from Deezer API."""
    url = f"https://api.deezer.com/search/album?q={quote(artist + ' ' + album)}&limit=25"
    response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    items = response.json().get("data", [])
    if not items:
        raise HTTPException(status_code=404, detail=f'Could not find "{album}" by {artist} on Deezer.')

    ranked = sorted(items, key=lambda i: score_music_match(i, artist, album), reverse=True)
    best = ranked[0]
    cover_url = best.get("cover_xl") or best.get("cover_big") or best.get("cover_medium") or ""
    cover_image = None
    if cover_url:
        try:
            cover_image = fetch_image_data_uri(cover_url)
        except Exception:
            cover_image = None
    return {
        "title": best.get("title", album),
        "artist": best.get("artist", {}).get("name", artist) if isinstance(best.get("artist"), dict) else artist,
        "coverImage": cover_image,
    }


def fetch_image_data_uri(image_url: str) -> Optional[str]:
    if not image_url:
        return None
    try:
        response = requests.get(image_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    except requests.RequestException:
        if image_url.startswith("https://gamesdb-images.launchbox.gg/"):
            response = requests.get(image_url.replace("https://", "http://", 1), timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        else:
            raise
    response.raise_for_status()
    content_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[0].strip() or "image/jpeg"
    encoded = base64.b64encode(response.content).decode("utf-8")
    return f"data:{content_type};base64,{encoded}"


def first_text_from_definition(detail_soup: BeautifulSoup, label: str) -> Optional[str]:
    for term in detail_soup.find_all("dt"):
        if term.get_text(" ", strip=True) != label:
            continue
        definition = term.find_next("dd")
        if not definition:
            return None
        text_parts = [part.get_text(" ", strip=True) for part in definition.find_all("a")]
        if text_parts:
            return ", ".join(part for part in text_parts if part)
        text = definition.get_text(" ", strip=True)
        return text or None
    return None


def section_image_by_region(detail_soup: BeautifulSoup, section_title: str, region: str = "North America") -> Optional[str]:
    target = normalize_launchbox_key(section_title)
    heading = None
    for item in detail_soup.find_all(["h2", "h3"]):
        heading_text = item.get_text(" ", strip=True)
        normalized_heading = normalize_launchbox_key(heading_text)
        if normalized_heading == target:
            heading = item
            break
        if target and (target in normalized_heading or normalized_heading in target):
            heading = item
            break
    if not heading:
        return None
    article = heading.find_parent("article")
    if not article:
        return None
    images = []
    for image in article.find_all("img"):
        image_url = image.get("src")
        if not image_url:
            continue
        images.append((image.get("alt", ""), image_url))
    if not images:
        return None
    preferred = next((image_url for alt, image_url in images if region in alt), None)
    return preferred or images[0][1]


def section_image_from_titles(detail_soup: BeautifulSoup, titles: List[str], region: str = "North America") -> Optional[str]:
    for title in titles:
        image_url = section_image_by_region(detail_soup, title, region)
        if image_url:
            return image_url
    return None


def is_cartridge_platform_name(platform: Optional[str]) -> bool:
    key = normalize_launchbox_key(platform or "")
    return key in {"nintendods", "nds", "nintendo3ds", "3ds", "gameboy", "gb"}


def fetch_launchbox_game_data(title: str, platform: str) -> dict:
    search_url = f"https://gamesdb.launchbox-app.com/games/results/{quote(title.strip().lower())}"
    search_response = requests.get(search_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    search_response.raise_for_status()
    search_soup = BeautifulSoup(search_response.text, "html.parser")

    candidates = []
    for link in search_soup.find_all("a", href=True):
        href = link.get("href", "")
        if not href.startswith("/games/details/"):
            continue
        heading = link.find("h3")
        if not heading:
            continue
        candidate_title = heading.get_text(" ", strip=True)
        platform_block = link.find("p")
        candidate_platform = platform_block.get_text(" ", strip=True) if platform_block else ""
        candidates.append({
            "title": candidate_title,
            "platform": candidate_platform,
            "href": href,
        })

    if not candidates:
        raise HTTPException(status_code=404, detail=f'LaunchBox could not find "{title}".')

    target_title = normalize_launchbox_key(title)
    target_title_loose = normalize_title_for_match(title)
    target_tokens = set(title_tokens(title))
    target_platform = normalize_launchbox_key(platform)

    def score(candidate: dict) -> int:
        from difflib import SequenceMatcher

        candidate_title = normalize_launchbox_key(candidate["title"])
        candidate_title_loose = normalize_title_for_match(candidate["title"])
        candidate_tokens = set(title_tokens(candidate["title"]))
        candidate_platform = normalize_launchbox_key(candidate["platform"])
        candidate_score = 0

        # Strong exact/substring checks for deterministic matches.
        if candidate_title == target_title:
            candidate_score += 140
        elif target_title in candidate_title or candidate_title in target_title:
            candidate_score += 90

        # Token overlap handles missing punctuation/colons and spacing differences.
        if target_tokens and candidate_tokens:
            overlap = len(target_tokens.intersection(candidate_tokens))
            union = len(target_tokens.union(candidate_tokens))
            if union:
                candidate_score += int((overlap / union) * 80)

        # Sequence similarity catches normalized foreign characters and minor typos.
        if target_title_loose and candidate_title_loose:
            similarity = SequenceMatcher(None, target_title_loose, candidate_title_loose).ratio()
            candidate_score += int(similarity * 50)

        if target_platform and (target_platform in candidate_platform or candidate_platform in target_platform):
            candidate_score += 35
        if candidate["title"].strip().lower() == title.strip().lower():
            candidate_score += 10
        return candidate_score

    best_match = max(candidates, key=score)
    best_score = score(best_match)
    if best_score < 50:
        raise HTTPException(status_code=404, detail=f'LaunchBox could not find "{title}" for {platform}.')

    detail_url = urljoin("https://gamesdb.launchbox-app.com", best_match["href"])
    detail_response = requests.get(detail_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    detail_response.raise_for_status()
    detail_soup = BeautifulSoup(detail_response.text, "html.parser")

    release_date = first_text_from_definition(detail_soup, "Release Date")
    release_date_iso = parse_launchbox_date(release_date)
    year_released = None
    if release_date_iso:
        year_match = re.search(r"(19|20)\d{2}", release_date_iso)
        if year_match:
            year_released = int(year_match.group(0))

    overview_heading = next((item for item in detail_soup.find_all(["h2", "h3"]) if item.get_text(" ", strip=True) == "Overview"), None)
    notes = None
    if overview_heading:
        overview_article = overview_heading.find_parent("article")
        if overview_article:
            overview_parts = [paragraph.get_text(" ", strip=True) for paragraph in overview_article.find_all("p") if paragraph.get_text(" ", strip=True)]
            notes = "\n\n".join(overview_parts) if overview_parts else None

    resolved_platform = first_text_from_definition(detail_soup, "Platform") or best_match["platform"] or platform
    cover_section_url = section_image_from_titles(detail_soup, ["Box - Front"])

    disc_section_titles = ["Disc"]
    if is_cartridge_platform_name(resolved_platform):
        disc_section_titles = [
            "Cart - Front",
            "Cartridge - Front",
            "Cartridge",
            "Cart",
            "Label - Front",
            "Disc",
        ]
    disc_section_url = section_image_from_titles(detail_soup, disc_section_titles)
    spine_section_url = section_image_from_titles(
        detail_soup,
        [
            "Box - Spine",
            "Box Spine",
            "Spine",
            "Box - Spine (Left)",
            "Box - Spine (Right)",
            "Box - Side",
            "Case - Spine",
        ],
    )

    cover_image = fetch_image_data_uri(urljoin(detail_url, cover_section_url)) if cover_section_url else None
    disc_image = fetch_image_data_uri(urljoin(detail_url, disc_section_url)) if disc_section_url else None
    spine_image = fetch_image_data_uri(urljoin(detail_url, spine_section_url)) if spine_section_url else None

    # If a title has no dedicated spine section, use cover art as a visual fallback.
    if not spine_image:
        spine_image = cover_image

    # For cartridge platforms, if specific cart art is unavailable, fall back to box art.
    if is_cartridge_platform_name(resolved_platform) and not disc_image:
        disc_image = cover_image

    return {
        "title": detail_soup.find("h1").get_text(" ", strip=True) if detail_soup.find("h1") else best_match["title"],
        "platform": resolved_platform,
        "release_date": release_date_iso,
        "year_released": year_released,
        "rating": first_text_from_definition(detail_soup, "ESRB"),
        "players": first_text_from_definition(detail_soup, "Max Players"),
        "cooperative": first_text_from_definition(detail_soup, "Cooperative"),
        "publishers": [entry for entry in (first_text_from_definition(detail_soup, "Publishers") or "").split(",") if entry.strip()],
        "gameGenres": [entry for entry in (first_text_from_definition(detail_soup, "Genre") or "").split(",") if entry.strip()],
        "notes": notes,
        "coverImage": cover_image,
        "spineImage": spine_image,
        "discImage": disc_image,
    }


SYSTEM_LOGO_SOURCE_URLS: Dict[str, str] = {
    "ps2": "https://upload.wikimedia.org/wikipedia/commons/7/76/PlayStation_2_logo.svg",
    "playstation2": "https://upload.wikimedia.org/wikipedia/commons/7/76/PlayStation_2_logo.svg",
    "ps3": "https://upload.wikimedia.org/wikipedia/commons/d/dc/PlayStation_3_logo.svg",
    "playstation3": "https://upload.wikimedia.org/wikipedia/commons/d/dc/PlayStation_3_logo.svg",
    "ps4": "https://upload.wikimedia.org/wikipedia/commons/8/87/PlayStation_4_logo_and_wordmark.svg",
    "playstation4": "https://upload.wikimedia.org/wikipedia/commons/8/87/PlayStation_4_logo_and_wordmark.svg",
    "nintendods": "https://upload.wikimedia.org/wikipedia/commons/a/af/Nintendo_DS_Logo.svg",
    "nds": "https://upload.wikimedia.org/wikipedia/commons/a/af/Nintendo_DS_Logo.svg",
    "nintendo3ds": "https://upload.wikimedia.org/wikipedia/commons/8/89/Nintendo_3DS_logo.svg",
    "3ds": "https://upload.wikimedia.org/wikipedia/commons/8/89/Nintendo_3DS_logo.svg",
    "gameboy": "https://upload.wikimedia.org/wikipedia/commons/f/f2/Nintendo_Game_Boy_Logo.svg",
    "gb": "https://upload.wikimedia.org/wikipedia/commons/f/f2/Nintendo_Game_Boy_Logo.svg",
    "gamecube": "https://upload.wikimedia.org/wikipedia/commons/2/29/Nintendo_GameCube_Official_Logo.svg",
    "gc": "https://upload.wikimedia.org/wikipedia/commons/2/29/Nintendo_GameCube_Official_Logo.svg",
    "wii": "https://upload.wikimedia.org/wikipedia/commons/b/bc/Wii.svg",
    "xbox": "https://upload.wikimedia.org/wikipedia/commons/0/06/Xbox_wordmark.svg",
    "xbox360": "https://upload.wikimedia.org/wikipedia/commons/1/1b/Xbox_360_logo.svg",
}


def fetch_system_logo_data(name: str) -> dict:
    normalized_name = normalize_launchbox_key(name)
    if not normalized_name:
        raise HTTPException(status_code=400, detail="System name is required.")

    logo_url = SYSTEM_LOGO_SOURCE_URLS.get(normalized_name)
    if not logo_url:
        for key, candidate_url in SYSTEM_LOGO_SOURCE_URLS.items():
            if key in normalized_name or normalized_name in key:
                logo_url = candidate_url
                break

    if not logo_url:
        raise HTTPException(
            status_code=404,
            detail="No known logo source for that system yet. You can still upload a logo manually.",
        )

    try:
        logo_image = fetch_image_data_uri(logo_url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch system logo image: {exc}") from exc

    if not logo_image:
        raise HTTPException(status_code=404, detail="System logo image could not be loaded.")

    return {
        "name": name,
        "logoImage": logo_image,
    }


def media_item_to_game_data(item: MediaItem) -> dict:
    def split_csv(value: Optional[str]) -> List[str]:
        if not value:
            return []
        return [entry.strip() for entry in value.split(",") if entry.strip()]

    return {
        "title": item.title,
        "platform": item.platform,
        "release_date": item.release_date,
        "year_released": item.year_released,
        "rating": item.rating,
        "players": str(item.players) if item.players is not None else None,
        "cooperative": item.cooperative,
        "publishers": split_csv(item.publisher),
        "gameGenres": split_csv(item.genres or item.genre),
        "notes": item.notes,
        "coverImage": item.cover_image,
        "spineImage": item.spine_image,
        "discImage": item.disc_image,
    }


def find_cached_game_item(session: Session, title: str, platform: str, item_id: Optional[int]) -> Optional[MediaItem]:
    if item_id is not None:
        item = session.get(MediaItem, item_id)
        if item and item.category == "Games":
            return item
        return None

    title_key = normalize_launchbox_key(title)
    platform_key = normalize_launchbox_key(platform)
    items = session.exec(select(MediaItem).where(MediaItem.category == "Games")).all()
    for item in items:
        if normalize_launchbox_key(item.title or "") == title_key and normalize_launchbox_key(item.platform or "") == platform_key:
            return item
    return None


def require_admin(authorization: Optional[str]) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin authorization required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token or token not in admin_tokens:
        raise HTTPException(status_code=401, detail="Invalid admin token")


def ensure_systems() -> None:
    """Initialize default gaming systems if they don't exist."""
    default_systems = [
        {"system_id": "ps2", "name": "PlayStation 2", "short_name": "PS2", "logo": "PS2",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/7/76/PlayStation_2_logo.svg"},
        {"system_id": "ps3", "name": "PlayStation 3", "short_name": "PS3", "logo": "PS3",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/d/dc/PlayStation_3_logo.svg"},
        {"system_id": "ps4", "name": "PlayStation 4", "short_name": "PS4", "logo": "PS4",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/8/87/PlayStation_4_logo_and_wordmark.svg"},
        {"system_id": "nds", "name": "Nintendo DS", "short_name": "NDS", "logo": "NDS",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/a/af/Nintendo_DS_Logo.svg"},
        {"system_id": "3ds", "name": "Nintendo 3DS", "short_name": "3DS", "logo": "3DS",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/8/89/Nintendo_3DS_logo.svg"},
        {"system_id": "gb", "name": "GameBoy", "short_name": "GB", "logo": "GB",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/f/f2/Nintendo_Game_Boy_Logo.svg"},
        {"system_id": "gc", "name": "GameCube", "short_name": "GC", "logo": "GC",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/2/29/Nintendo_GameCube_Official_Logo.svg"},
        {"system_id": "wii", "name": "Wii", "short_name": "Wii", "logo": "Wii",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/b/bc/Wii.svg"},
        {"system_id": "xbox", "name": "Xbox", "short_name": "XBX", "logo": "XBX",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/0/06/Xbox_wordmark.svg"},
        {"system_id": "xbox360", "name": "Xbox 360", "short_name": "360", "logo": "360",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/1/1b/Xbox_360_logo.svg"},
    ]

    with Session(engine) as session:
        for system_data in default_systems:
            existing = session.exec(select(GameSystem).where(GameSystem.system_id == system_data["system_id"])).first()
            if not existing:
                # Try to fetch and encode the logo image
                logo_image_data = None
                try:
                    response = requests.get(system_data["logo_url"], timeout=5)
                    if response.status_code == 200:
                        logo_image_data = base64.b64encode(response.content).decode("utf-8")
                except Exception:
                    pass  # If fetching fails, just leave logo_image as None

                system = GameSystem(
                    system_id=system_data["system_id"],
                    name=system_data["name"],
                    short_name=system_data["short_name"],
                    logo=system_data["logo"],
                    logo_image=logo_image_data,
                )
                session.add(system)
        session.commit()


@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()
    ensure_release_date_column()
    ensure_rating_column()
    ensure_genres_column()
    ensure_cooperative_column()
    ensure_disc_image_column()
    ensure_spine_image_column()
    ensure_systems()

@app.get("/api/media", response_model=List[MediaItem])
def read_media(
    category: Optional[str] = None,
    platform: Optional[str] = None,
    genre: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    players: Optional[int] = None,
    search: Optional[str] = None,
) -> List[MediaItem]:
    with Session(engine) as session:
        query = select(MediaItem)
        if category:
            query = query.where(MediaItem.category == category)
        if platform:
            query = query.where(MediaItem.platform == platform)
        if genre:
            query = query.where(MediaItem.genre == genre)
        if year_min is not None:
            query = query.where(MediaItem.year_released >= year_min)
        if year_max is not None:
            query = query.where(MediaItem.year_released <= year_max)
        if players is not None:
            query = query.where(MediaItem.players == players)
        if search:
            like_term = f"%{search}%"
            query = query.where(
                (MediaItem.title.ilike(like_term))
                | (MediaItem.artist.ilike(like_term))
                | (MediaItem.publisher.ilike(like_term))
                | (MediaItem.genre.ilike(like_term))
                | (MediaItem.genres.ilike(like_term))
                | (MediaItem.cooperative.ilike(like_term))
                | (MediaItem.tags.ilike(like_term))
                | (MediaItem.notes.ilike(like_term))
            )
        return session.exec(query).all()

@app.get("/api/media/{item_id}", response_model=MediaItem)
def read_media_item(item_id: int) -> MediaItem:
    with Session(engine) as session:
        item = session.get(MediaItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Media item not found")
        return item


@app.post("/api/admin/login")
def admin_login(payload: AdminLoginRequest) -> dict:
    if payload.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")
    token = secrets.token_urlsafe(32)
    admin_tokens[token] = True
    return {"token": token}


@app.post("/api/admin/logout")
def admin_logout(authorization: Optional[str] = Header(default=None)) -> dict:
    require_admin(authorization)
    token = authorization.removeprefix("Bearer ").strip()
    if token in admin_tokens:
        del admin_tokens[token]
    return {"success": True}

@app.post("/api/media", response_model=MediaItem)
def create_media_item(item: MediaItem, authorization: Optional[str] = Header(default=None)) -> MediaItem:
    require_admin(authorization)
    with Session(engine) as session:
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

@app.put("/api/media/{item_id}", response_model=MediaItem)
def update_media_item(item_id: int, updated: MediaItem, authorization: Optional[str] = Header(default=None)) -> MediaItem:
    require_admin(authorization)
    with Session(engine) as session:
        item = session.get(MediaItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Media item not found")
        item_data = updated.dict(exclude_unset=True)
        for key, value in item_data.items():
            setattr(item, key, value)
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

@app.delete("/api/media/{item_id}")
def delete_media_item(item_id: int, authorization: Optional[str] = Header(default=None)) -> dict:
    require_admin(authorization)
    with Session(engine) as session:
        item = session.get(MediaItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Media item not found")
        session.delete(item)
        session.commit()
        return {"success": True}

@app.get("/api/filters")
def get_filters() -> dict:
    with Session(engine) as session:
        categories = session.exec(
            select(MediaItem.category).distinct().order_by(MediaItem.category)
        ).all()
        platforms = session.exec(
            select(MediaItem.platform).distinct().order_by(MediaItem.platform)
        ).all()
        genres = session.exec(
            select(MediaItem.genre).distinct().order_by(MediaItem.genre)
        ).all()
        extra_genres = session.exec(
            select(MediaItem.genres).distinct().order_by(MediaItem.genres)
        ).all()
        years = session.exec(
            select(MediaItem.year_released).distinct().order_by(MediaItem.year_released)
        ).all()
        genre_values = sorted(
            {
                genre.strip()
                for value in [*genres, *extra_genres]
                if value
                for genre in value.split(",")
                if genre.strip()
            }
        )
        return {
            "categories": categories,
            "platforms": platforms,
            "genres": genre_values,
            "years": sorted([year for year in years if year is not None]),
        }


@app.post("/api/launchbox/game-data")
def fetch_game_data(payload: LaunchboxGameDataRequest, authorization: Optional[str] = Header(default=None)) -> dict:
    require_admin(authorization)
    title = payload.title.strip()
    platform = payload.platform.strip()
    if not title or not platform:
        raise HTTPException(status_code=400, detail="Game title and platform are required.")

    cached_item: Optional[MediaItem] = None
    with Session(engine) as session:
        cached_item = find_cached_game_item(session, title, platform, payload.item_id)
        if cached_item and cached_item.cover_image and cached_item.disc_image and cached_item.spine_image:
            return media_item_to_game_data(cached_item)

    fetched = fetch_launchbox_game_data(title, platform)

    with Session(engine) as session:
        item_to_update = find_cached_game_item(session, title, platform, payload.item_id)
        if item_to_update:
            item_to_update.cover_image = fetched.get("coverImage") or item_to_update.cover_image
            item_to_update.spine_image = fetched.get("spineImage") or item_to_update.spine_image
            item_to_update.disc_image = fetched.get("discImage") or item_to_update.disc_image
            item_to_update.release_date = parse_launchbox_date(fetched.get("release_date")) or item_to_update.release_date
            item_to_update.year_released = fetched.get("year_released") or item_to_update.year_released
            item_to_update.rating = normalize_esrb_rating(fetched.get("rating")) or item_to_update.rating
            item_to_update.cooperative = fetched.get("cooperative") or item_to_update.cooperative
            if fetched.get("notes"):
                item_to_update.notes = fetched.get("notes")

            publishers = [entry.strip() for entry in fetched.get("publishers", []) if entry.strip()]
            game_genres = [entry.strip() for entry in fetched.get("gameGenres", []) if entry.strip()]
            if publishers:
                item_to_update.publisher = ", ".join(publishers)
            if game_genres:
                item_to_update.genres = ", ".join(game_genres)
                item_to_update.genre = game_genres[0]

            players_raw = fetched.get("players")
            if players_raw:
                try:
                    item_to_update.players = int(players_raw)
                except (TypeError, ValueError):
                    pass

            session.add(item_to_update)
            session.commit()
            session.refresh(item_to_update)
            return media_item_to_game_data(item_to_update)

    return fetched


@app.post("/api/bulk/games")
def bulk_upload_games(payload: BulkGamesRequest, authorization: Optional[str] = Header(default=None)) -> dict:
    """Bulk-create game entries by fetching metadata from LaunchBox."""
    require_admin(authorization)
    results = []
    for raw_line in payload.items:
        line = raw_line.strip()
        if not line:
            continue
        if " - " not in line:
            results.append({"line": line, "status": "error", "error": "Invalid format - use: Game Title - Platform"})
            continue
        title_part, platform_part = line.rsplit(" - ", 1)
        title_part = title_part.strip()
        platform_part = platform_part.strip()
        try:
            game_data = fetch_launchbox_game_data(title_part, platform_part)
        except HTTPException as exc:
            results.append({"line": line, "status": "error", "error": exc.detail})
            continue
        except Exception as exc:
            results.append({"line": line, "status": "error", "error": str(exc)})
            continue

        game_genres = game_data.get("gameGenres", [])
        publishers = game_data.get("publishers", [])
        release_date_raw = game_data.get("release_date")
        release_date_iso = parse_launchbox_date(release_date_raw)
        year_released = game_data.get("year_released")
        players_raw = game_data.get("players")
        try:
            players_int = int(players_raw) if players_raw else None
        except (ValueError, TypeError):
            players_int = None

        item = MediaItem(
            title=normalize_game_title(game_data.get("title", title_part)),
            category="Games",
            platform=game_data.get("platform", platform_part),
            genre=game_genres[0] if game_genres else "Action",
            genres=", ".join(game_genres) if game_genres else None,
            release_date=release_date_iso,
            year_released=year_released,
            rating=normalize_esrb_rating(game_data.get("rating")),
            players=players_int,
            cooperative=game_data.get("cooperative", "No"),
            publisher=", ".join(publishers) if publishers else None,
            notes=game_data.get("notes"),
            cover_image=game_data.get("coverImage"),
            spine_image=game_data.get("spineImage"),
            disc_image=game_data.get("discImage"),
        )
        with Session(engine) as session:
            session.add(item)
            session.commit()
            session.refresh(item)
            results.append({"line": line, "status": "success", "id": item.id, "title": item.title})

    return {"results": results}


@app.post("/api/bulk/music")
def bulk_upload_music(payload: BulkMusicRequest, authorization: Optional[str] = Header(default=None)) -> dict:
    """Bulk-create music entries by fetching cover art from Deezer."""
    require_admin(authorization)
    results = []
    for raw_line in payload.items:
        line = raw_line.strip()
        if not line:
            continue
        if " - " not in line:
            results.append({"line": line, "status": "error", "error": "Invalid format - use: Album Title - Artist"})
            continue
        album_part, artist_part = line.rsplit(" - ", 1)
        album_part = album_part.strip()
        artist_part = artist_part.strip()
        try:
            music_data = fetch_music_album_data(album_part, artist_part)
        except HTTPException as exc:
            results.append({"line": line, "status": "error", "error": exc.detail})
            continue
        except Exception as exc:
            results.append({"line": line, "status": "error", "error": str(exc)})
            continue

        item = MediaItem(
            title=music_data.get("title", album_part),
            category="Music",
            platform=None,
            genre="",
            artist=music_data.get("artist", artist_part),
            cover_image=music_data.get("coverImage"),
        )
        with Session(engine) as session:
            session.add(item)
            session.commit()
            session.refresh(item)
            results.append({"line": line, "status": "success", "id": item.id, "title": item.title})

    return {"results": results}


# ── SYSTEM MANAGEMENT ──

@app.get("/api/systems", response_model=List[dict])
def get_systems():
    """Get all gaming systems with their logos."""
    with Session(engine) as session:
        systems = session.exec(select(GameSystem)).all()
        return [
            {
                "id": s.system_id,
                "name": s.name,
                "shortName": s.short_name,
                "logo": s.logo,
                "logoImage": s.logo_image,
            }
            for s in systems
        ]


@app.post("/api/systems")
def create_system(system_data: dict, authorization: Optional[str] = Header(default=None)):
    """Create a new gaming system with optional image URL or base64 data."""
    require_admin(authorization)
    
    system_id = system_data.get("id", "").strip()
    name = system_data.get("name", "").strip()
    short_name = system_data.get("shortName", "").strip()
    logo = system_data.get("logo", "").strip()
    logo_image_url = system_data.get("logoImageUrl", "").strip()
    
    if not system_id or not name or not short_name:
        raise HTTPException(status_code=400, detail="Missing required fields: id, name, shortName")
    
    with Session(engine) as session:
        existing = session.exec(select(GameSystem).where(GameSystem.system_id == system_id)).first()
        if existing:
            raise HTTPException(status_code=409, detail="System ID already exists")
        
        logo_image_data = None
        if logo_image_url.startswith("data:image"):
            # Already base64 encoded
            logo_image_data = logo_image_url.split(",", 1)[1] if "," in logo_image_url else None
        elif logo_image_url:
            # Fetch from URL and encode
            try:
                response = requests.get(logo_image_url, timeout=10)
                if response.status_code == 200:
                    logo_image_data = base64.b64encode(response.content).decode("utf-8")
            except Exception:
                pass
        
        system = GameSystem(
            system_id=system_id,
            name=name,
            short_name=short_name,
            logo=logo,
            logo_image=logo_image_data,
        )
        session.add(system)
        session.commit()
        session.refresh(system)
        
        return {
            "id": system.system_id,
            "name": system.name,
            "shortName": system.short_name,
            "logo": system.logo,
            "logoImage": system.logo_image,
        }


@app.post("/api/systems/logo-data")
def fetch_system_logo(payload: SystemLogoDataRequest, authorization: Optional[str] = Header(default=None)) -> dict:
    require_admin(authorization)
    return fetch_system_logo_data(payload.name.strip())


@app.post("/api/system-logo-data")
def fetch_system_logo_alias(payload: SystemLogoDataRequest, authorization: Optional[str] = Header(default=None)) -> dict:
    require_admin(authorization)
    return fetch_system_logo_data(payload.name.strip())


@app.post("/api/logo/system-data")
def fetch_system_logo_stable(payload: SystemLogoDataRequest, authorization: Optional[str] = Header(default=None)) -> dict:
    require_admin(authorization)
    return fetch_system_logo_data(payload.name.strip())


@app.put("/api/systems/{system_id}")
def update_system(system_id: str, system_data: dict, authorization: Optional[str] = Header(default=None)):
    """Update an existing gaming system."""
    require_admin(authorization)
    
    with Session(engine) as session:
        system = session.exec(select(GameSystem).where(GameSystem.system_id == system_id)).first()
        if not system:
            raise HTTPException(status_code=404, detail="System not found")
        
        if "name" in system_data and system_data["name"].strip():
            system.name = system_data["name"].strip()
        if "shortName" in system_data and system_data["shortName"].strip():
            system.short_name = system_data["shortName"].strip()
        if "logo" in system_data:
            system.logo = system_data["logo"].strip()
        
        # Handle logo image update (URL or base64)
        if "logoImageUrl" in system_data:
            logo_image_url = system_data["logoImageUrl"].strip()
            if logo_image_url.startswith("data:image"):
                system.logo_image = logo_image_url.split(",", 1)[1] if "," in logo_image_url else None
            elif logo_image_url:
                try:
                    response = requests.get(logo_image_url, timeout=10)
                    if response.status_code == 200:
                        system.logo_image = base64.b64encode(response.content).decode("utf-8")
                except Exception:
                    pass
        
        session.add(system)
        session.commit()
        session.refresh(system)
        
        return {
            "id": system.system_id,
            "name": system.name,
            "shortName": system.short_name,
            "logo": system.logo,
            "logoImage": system.logo_image,
        }


@app.post("/api/systems/{system_id}")
def systems_post_compat(system_id: str, system_data: dict, authorization: Optional[str] = Header(default=None)) -> dict:
    """Compatibility handler for clients posting to /api/systems/logo-data.

    Some deployments can resolve /api/systems/logo-data through the dynamic
    /api/systems/{system_id} matcher first. Accept that path and route it to
    the logo fetch logic instead of returning 405.
    """
    require_admin(authorization)

    if system_id == "logo-data":
        name = (system_data.get("name") or "").strip()
        return fetch_system_logo_data(name)

    raise HTTPException(status_code=405, detail="Method Not Allowed")


@app.delete("/api/systems/{system_id}")
def delete_system(system_id: str, authorization: Optional[str] = Header(default=None)):
    """Delete a gaming system."""
    require_admin(authorization)
    
    with Session(engine) as session:
        system = session.exec(select(GameSystem).where(GameSystem.system_id == system_id)).first()
        if not system:
            raise HTTPException(status_code=404, detail="System not found")
        
        session.delete(system)
        session.commit()
        
        return {"success": True}


@app.get("/suggestions/ps2-intro.mp4")
def stream_ps2_intro(request: Request):
    video_path = SUGGESTIONS_DIR / "ps2-intro.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Intro video not found")

    file_size = video_path.stat().st_size
    range_header = request.headers.get("range")

    if not range_header:
        response = FileResponse(video_path, media_type="video/mp4")
        response.headers["Accept-Ranges"] = "bytes"
        return response

    if not range_header.startswith("bytes="):
        raise HTTPException(status_code=416, detail="Invalid range header")

    start_str, end_str = range_header.replace("bytes=", "").split("-", 1)
    start = int(start_str) if start_str else 0
    end = int(end_str) if end_str else file_size - 1

    if start >= file_size:
        raise HTTPException(status_code=416, detail="Requested range not satisfiable")

    end = min(end, file_size - 1)
    content_length = end - start + 1

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Length": str(content_length),
        "Content-Type": "video/mp4",
    }
    return StreamingResponse(iter_file_range(video_path, start, end), status_code=206, headers=headers)

if SUGGESTIONS_DIR.exists():
    app.mount("/suggestions", StaticFiles(directory=str(SUGGESTIONS_DIR)), name="suggestions")

if FRONTEND_BUILD_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_BUILD_DIR), html=True), name="frontend")

    @app.get("/{path_name:path}")
    async def frontend(path_name: str) -> FileResponse:
        file_path = FRONTEND_BUILD_DIR / path_name
        if file_path.exists():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_BUILD_DIR / "index.html")
else:
    @app.get("/{path_name:path}")
    async def frontend(path_name: str):
        raise HTTPException(status_code=503, detail="Frontend build not found. Run npm run build.")
