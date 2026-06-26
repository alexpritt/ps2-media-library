from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple
import secrets
import base64
import os
import re
import time
import unicodedata
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

import requests
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlmodel import Field, Session, SQLModel, create_engine, select

DATABASE_PATH = Path(__file__).parent / "media.db"
FRONTEND_BUILD_DIR = Path(__file__).parent.parent / "frontend" / "build"

app = FastAPI(title="PS2 Media Library API")

allowed_origins = [
    "http://127.0.0.1:4173",
    "http://localhost:4173",
    "https://theavenoircollection.com",
    "https://www.theavenoircollection.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "foreverandalways2015")
admin_tokens: Dict[str, bool] = {}


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


ENABLE_KEYLESS_METADATA_FALLBACK = env_flag("ENABLE_KEYLESS_METADATA_FALLBACK", default=True)
ENABLE_SCREENSCRAPER_FALLBACK = env_flag("ENABLE_SCREENSCRAPER_FALLBACK", default=False)
ENABLE_MOBYGAMES_SCRAPE_FALLBACK = env_flag("ENABLE_MOBYGAMES_SCRAPE_FALLBACK", default=False)
MOBYGAMES_MIN_REQUEST_INTERVAL = env_float("MOBYGAMES_MIN_REQUEST_INTERVAL", default=1.5)
DEFAULT_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0"}
MOBYGAMES_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}
MOBYGAMES_BASE_URL = "https://www.mobygames.com"
_mobygames_html_cache: Dict[str, str] = {}
_mobygames_last_request_at = 0.0


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
    star_rating: Optional[int] = None
    gameplay_rating: Optional[int] = None
    plot_rating: Optional[int] = None


class GameSystem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    system_id: str = Field(unique=True)
    name: str
    short_name: str
    logo: str
    logo_image: Optional[str] = None  # Base64 encoded image data
    case_type: str = "disc"
    appearance_preset: Optional[str] = None
    is_cartridge_inferred: bool = False
    display_order: int = Field(default=0)


class AdminLoginRequest(SQLModel):
    password: str


class LaunchboxGameDataRequest(SQLModel):
    title: str
    platform: str
    item_id: Optional[int] = None


class LaunchboxGameArtOptionsRequest(SQLModel):
    title: str
    platform: str
    art_type: str


class DeezerMusicDataRequest(SQLModel):
    title: str
    artist: str


class BulkGamesRequest(SQLModel):
    items: List[str]
    platform: Optional[str] = None


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


def ensure_star_rating_columns() -> None:
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(mediaitem)")).fetchall()
        column_names = {column[1] for column in columns}
        if "star_rating" not in column_names:
            connection.execute(text("ALTER TABLE mediaitem ADD COLUMN star_rating INTEGER"))
        if "gameplay_rating" not in column_names:
            connection.execute(text("ALTER TABLE mediaitem ADD COLUMN gameplay_rating INTEGER"))
        if "plot_rating" not in column_names:
            connection.execute(text("ALTER TABLE mediaitem ADD COLUMN plot_rating INTEGER"))


def ensure_system_case_type_column() -> None:
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(gamesystem)")).fetchall()
        has_case_type = any(column[1] == "case_type" for column in columns)
        if not has_case_type:
            connection.execute(text("ALTER TABLE gamesystem ADD COLUMN case_type VARCHAR DEFAULT 'disc'"))
            connection.execute(text("UPDATE gamesystem SET case_type = 'disc' WHERE case_type IS NULL OR case_type = ''"))


def ensure_system_appearance_preset_column() -> None:
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(gamesystem)")).fetchall()
        has_appearance_preset = any(column[1] == "appearance_preset" for column in columns)
        if not has_appearance_preset:
            connection.execute(text("ALTER TABLE gamesystem ADD COLUMN appearance_preset VARCHAR"))


def ensure_system_is_cartridge_inferred_column() -> None:
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(gamesystem)")).fetchall()
        has_is_cartridge_inferred = any(column[1] == "is_cartridge_inferred" for column in columns)
        if not has_is_cartridge_inferred:
            connection.execute(text("ALTER TABLE gamesystem ADD COLUMN is_cartridge_inferred BOOLEAN DEFAULT 0"))
            connection.execute(text("UPDATE gamesystem SET is_cartridge_inferred = 0 WHERE is_cartridge_inferred IS NULL"))


def ensure_system_display_order_column() -> None:
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(gamesystem)")).fetchall()
        has_display_order = any(column[1] == "display_order" for column in columns)
        if not has_display_order:
            connection.execute(text("ALTER TABLE gamesystem ADD COLUMN display_order INTEGER DEFAULT 0"))
            # Set display_order alphabetically by name for existing systems
            systems = connection.execute(text("SELECT id, name FROM gamesystem ORDER BY name ASC")).fetchall()
            for order, (system_id, _) in enumerate(systems):
                connection.execute(text("UPDATE gamesystem SET display_order = ? WHERE id = ?"), {"order": order, "id": system_id})


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


CARTRIDGE_PRESET_ALIASES: Dict[str, str] = {
    # Nintendo handhelds
    "nds": "nds",
    "nintendods": "nds",
    "ds": "nds",
    "3ds": "3ds",
    "nintendo3ds": "3ds",
    "newnintendo3ds": "3ds",
    "gb": "gb",
    "gameboy": "gb",
    "gameboycolor": "gb",
    "gbc": "gb",
    "gameboyadvance": "gba",
    "gameboyadvancesp": "gba",
    "gba": "gba",
    "gbasp": "gba",
    "nintendoswitch": "switch",
    "switch": "switch",
    "nintendoswitchlite": "switch",
    "switchlite": "switch",
    "nintendoswitcholed": "switch",
    "switcholed": "switch",
    "nintendo64": "n64",
    "n64": "n64",
    "nes": "nes",
    "nintendoentertainmentsystem": "nes",
    "snes": "snes",
    "supernintendo": "snes",
    "supernintendoentertainmentsystem": "snes",
    "virtualboy": "virtualboy",
    # Sega cartridge systems
    "genesis": "genesis",
    "segagenesis": "genesis",
    "megadrive": "genesis",
    "segamegadrive": "genesis",
    "segamastersystem": "mastersystem",
    "mastersystem": "mastersystem",
    "sg1000": "sg1000",
    "gamegear": "gamegear",
    "segagamegear": "gamegear",
    # Atari cartridge systems
    "atari2600": "atari2600",
    "atari5200": "atari5200",
    "atari7800": "atari7800",
    "atarilynx": "atarilynx",
    "lynx": "atarilynx",
    "jaguar": "jaguar",
    "atarijaguar": "jaguar",
    # Other common cartridge systems
    "intellivision": "intellivision",
    "colecovision": "colecovision",
    "neogeo": "neogeo",
    "neogeoaes": "neogeo",
    "neogeopocket": "neogeopocket",
    "neogeopocketcolor": "neogeopocket",
    "turbografx16": "turbografx16",
    "pcengine": "turbografx16",
    "wonderswan": "wonderswan",
    "wonderswancolor": "wonderswan",
    "vectrex": "vectrex",
    "psvita": "psvita",
    "playstationvita": "psvita",
}


DISC_PRESET_ALIASES: Dict[str, str] = {
    # Sony
    "ps1": "ps1",
    "playstation": "ps1",
    "playstation1": "ps1",
    "psx": "ps1",
    "ps2": "ps2",
    "playstation2": "ps2",
    "ps3": "ps3",
    "playstation3": "ps3",
    "ps4": "ps4",
    "playstation4": "ps4",
    "ps5": "ps5",
    "playstation5": "ps5",
    "psp": "psp",
    "playstationportable": "psp",
    # Nintendo optical systems
    "gc": "gamecube",
    "gamecube": "gamecube",
    "wii": "wii",
    "wiiu": "wiiu",
    # Microsoft
    "xbox": "xbox",
    "xbox360": "xbox360",
    "xboxone": "xboxone",
    "xboxseries": "xboxseries",
    "xboxseriess": "xboxseries",
    "xboxseriesx": "xboxseries",
    # Sega optical systems
    "dreamcast": "dreamcast",
    "segacd": "segacd",
    "sega32xcd": "segacd",
    "saturn": "saturn",
    # Other optical systems
    "pcfx": "pcfx",
    "3do": "3do",
    "amiga32cd": "amiga32cd",
    "atarijaguarcd": "jaguarcd",
}


def infer_system_appearance(system_id: str, name: str) -> Tuple[str, str, bool]:
    key = normalize_launchbox_key(system_id or name)
    name_key = normalize_launchbox_key(name)
    token_source = " ".join(part for part in [system_id or "", name or ""] if part)
    tokens = set(title_tokens(token_source))

    def alias_matches(alias: str) -> bool:
        if alias == key or alias == name_key or alias in tokens:
            return True
        return False

    for alias, preset in sorted(CARTRIDGE_PRESET_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias_matches(alias):
            return ("cartridge", preset, True)

    for alias, preset in sorted(DISC_PRESET_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias_matches(alias):
            return ("disc", preset, False)

    return ("disc", "generic-disc", False)


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


def parse_optional_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def normalize_release_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return value
    if re.match(r"^\d{4}-\d{2}$", value):
        return f"{value}-01"
    year_m = re.search(r"\b(19|20)\d{2}\b", value)
    if year_m:
        return f"{year_m.group(0)}-01-01"
    return parse_launchbox_date(value)


def fetch_wikidata_game_data(title: str, platform: str) -> Optional[dict]:
    """Fetch minimal keyless metadata from Wikidata as a LaunchBox-down fallback."""

    search_response = requests.get(
        "https://www.wikidata.org/w/api.php",
        params={
            "action": "wbsearchentities",
            "format": "json",
            "language": "en",
            "type": "item",
            "search": title,
            "limit": 5,
        },
        timeout=20,
        headers={"User-Agent": "PS2MediaLibrary/1.0"},
    )
    search_response.raise_for_status()
    candidates = search_response.json().get("search", [])
    if not candidates:
        return None

    title_key = normalize_title_for_match(title)
    platform_key = normalize_title_for_match(platform)
    best_candidate = None
    best_score = -1

    for candidate in candidates:
        label = candidate.get("label", "")
        description = candidate.get("description", "") or ""
        candidate_score = 0

        if normalize_title_for_match(label) == title_key:
            candidate_score += 120
        elif title_key and title_key in normalize_title_for_match(label):
            candidate_score += 80

        if "video game" in description.lower() or "videogame" in description.lower():
            candidate_score += 35

        if platform_key and platform_key in normalize_title_for_match(description):
            candidate_score += 20

        if candidate_score > best_score:
            best_score = candidate_score
            best_candidate = candidate

    if not best_candidate or best_score < 60:
        return None

    entity_id = best_candidate.get("id")
    if not entity_id:
        return None

    entity_response = requests.get(
        "https://www.wikidata.org/w/api.php",
        params={
            "action": "wbgetentities",
            "format": "json",
            "ids": entity_id,
            "languages": "en",
            "props": "labels|descriptions|claims",
        },
        timeout=20,
        headers={"User-Agent": "PS2MediaLibrary/1.0"},
    )
    entity_response.raise_for_status()
    entity = (entity_response.json().get("entities") or {}).get(entity_id) or {}
    claims = entity.get("claims") or {}

    def claim_time(prop: str) -> Optional[str]:
        claim_entries = claims.get(prop) or []
        for claim in claim_entries:
            datavalue = (((claim.get("mainsnak") or {}).get("datavalue")) or {})
            value = datavalue.get("value") or {}
            time_value = value.get("time")
            if isinstance(time_value, str):
                normalized = time_value.lstrip("+")
                if len(normalized) >= 10:
                    return normalized[:10]
        return None

    release_date = claim_time("P577")
    year_released = parse_optional_int(release_date[:4] if release_date else None)
    description = ((entity.get("descriptions") or {}).get("en") or {}).get("value")

    return {
        "title": ((entity.get("labels") or {}).get("en") or {}).get("value") or best_candidate.get("label") or title,
        "platform": platform,
        "release_date": release_date,
        "year_released": year_released,
        "rating": None,
        "players": None,
        "cooperative": None,
        "publishers": [],
        "gameGenres": [],
        "notes": description,
        "coverImage": None,
        "spineImage": None,
        "discImage": None,
        "data_source": "wikidata",
        "is_partial_fallback": True,
        "completeness": {
            "metadata": True,
            "cover": False,
            "disc": False,
            "spine": False,
            "cart": False,
        },
    }


def fetch_game_data_with_fallback(title: str, platform: str) -> dict:
    try:
        payload = fetch_launchbox_game_data(title, platform)
        payload["data_source"] = "launchbox"
        payload["is_partial_fallback"] = False
        payload["completeness"] = {
            "metadata": True,
            "cover": bool(payload.get("coverImage")),
            "disc": bool(payload.get("discImage")),
            "spine": bool(payload.get("spineImage")),
            "cart": False,
        }
        return payload
    except Exception as exc:
        if ENABLE_KEYLESS_METADATA_FALLBACK:
            try:
                metadata_payload = fetch_wikidata_game_data(title, platform)
                if metadata_payload:
                    return metadata_payload
            except Exception:
                pass

        raise HTTPException(
            status_code=502,
            detail=(
                "Could not fetch game data. LaunchBox is unavailable and no approved "
                "keyless metadata fallback source returned a match."
            ),
        ) from exc


def fetch_game_art_options_with_fallback(title: str, platform: str, art_type: str) -> dict:
    try:
        launchbox_options = fetch_launchbox_game_art_options(title, platform, art_type)
        launchbox_options["data_source"] = "launchbox"
        return launchbox_options
    except Exception as exc:
        if ENABLE_MOBYGAMES_SCRAPE_FALLBACK:
            try:
                mobygames_options = fetch_mobygames_game_art_options(title, platform, art_type)
                mobygames_options["data_source"] = "mobygames"
                return mobygames_options
            except Exception:
                pass

        raise HTTPException(
            status_code=404,
            detail=(
                f"Could not fetch {art_type} art. LaunchBox art is unavailable"
                + (" and MobyGames fallback did not return an approved NTSC-US match" if ENABLE_MOBYGAMES_SCRAPE_FALLBACK else "")
                + ". This art type will not be inferred from other media. Use manual upload while LaunchBox is down."
            ),
        ) from exc


def apply_fetched_game_data_to_item(item: MediaItem, fetched: dict) -> None:
    source = (fetched.get("data_source") or "").lower()
    is_launchbox_source = source == "launchbox"

    item.cover_image = fetched.get("coverImage") or item.cover_image
    if is_launchbox_source:
        item.spine_image = fetched.get("spineImage") or item.spine_image
        item.disc_image = fetched.get("discImage") or item.disc_image

    incoming_release_date = normalize_release_date(fetched.get("release_date"))
    incoming_year_released = fetched.get("year_released")
    incoming_rating = normalize_esrb_rating(fetched.get("rating"))
    incoming_cooperative = fetched.get("cooperative")

    if is_launchbox_source:
        item.release_date = incoming_release_date or item.release_date
        item.year_released = incoming_year_released or item.year_released
        item.rating = incoming_rating or item.rating
        item.cooperative = incoming_cooperative or item.cooperative
    else:
        item.release_date = item.release_date or incoming_release_date
        item.year_released = item.year_released or incoming_year_released
        item.rating = item.rating or incoming_rating
        item.cooperative = item.cooperative or incoming_cooperative

    if fetched.get("notes") and (is_launchbox_source or not item.notes):
        item.notes = fetched.get("notes")

    publishers = [entry.strip() for entry in fetched.get("publishers", []) if isinstance(entry, str) and entry.strip()]
    game_genres = [entry.strip() for entry in fetched.get("gameGenres", []) if isinstance(entry, str) and entry.strip()]

    if publishers and (is_launchbox_source or not (item.publisher or "").strip()):
        item.publisher = ", ".join(publishers)
    if game_genres and (is_launchbox_source or not (item.genres or item.genre or "").strip()):
        item.genres = ", ".join(game_genres)
        item.genre = game_genres[0]

    players_int = parse_optional_int(fetched.get("players"))
    if players_int is not None:
        item.players = players_int


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
    """Fetch album metadata and cover art from Deezer API."""
    url = f"https://api.deezer.com/search/album?q={quote(artist + ' ' + album)}&limit=25"
    response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    items = response.json().get("data", [])
    if not items:
        raise HTTPException(status_code=404, detail=f'Could not find "{album}" by {artist} on Deezer.')

    ranked = sorted(items, key=lambda i: score_music_match(i, artist, album), reverse=True)
    best = ranked[0]
    album_details: dict = {}
    album_id = best.get("id")
    if album_id:
        try:
            detail_response = requests.get(
                f"https://api.deezer.com/album/{album_id}",
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            detail_response.raise_for_status()
            detail_payload = detail_response.json()
            if isinstance(detail_payload, dict):
                album_details = detail_payload
        except Exception:
            album_details = {}

    cover_url = (
        album_details.get("cover_xl")
        or album_details.get("cover_big")
        or album_details.get("cover_medium")
        or best.get("cover_xl")
        or best.get("cover_big")
        or best.get("cover_medium")
        or ""
    )
    cover_image = None
    if cover_url:
        try:
            cover_image = fetch_image_data_uri(cover_url)
        except Exception:
            cover_image = None

    genres = []
    detail_genres_root = album_details.get("genres")
    detail_genres = detail_genres_root.get("data", []) if isinstance(detail_genres_root, dict) else []
    for entry in detail_genres:
        if isinstance(entry, dict):
            genre_name = str(entry.get("name") or "").strip()
            if genre_name:
                genres.append(genre_name)

    release_date = str(album_details.get("release_date") or "").strip() or None
    year_released = None
    if release_date:
        year_match = re.match(r"^(\d{4})", release_date)
        if year_match:
            year_released = int(year_match.group(1))

    detail_artist = album_details.get("artist")
    best_artist = best.get("artist")
    resolved_artist = artist
    if isinstance(detail_artist, dict):
        resolved_artist = detail_artist.get("name", artist)
    elif isinstance(best_artist, dict):
        resolved_artist = best_artist.get("name", artist)
    return {
        "title": album_details.get("title") or best.get("title", album),
        "artist": resolved_artist,
        "genre": genres[0] if genres else "",
        "release_date": release_date,
        "year_released": year_released,
        "coverImage": cover_image,
    }


def fetch_image_data_uri(image_url: str) -> Optional[str]:
    if not image_url:
        return None
    try:
        response = requests.get(image_url, timeout=20, headers=DEFAULT_HTTP_HEADERS)
    except requests.RequestException:
        if image_url.startswith("https://gamesdb-images.launchbox.gg/"):
            response = requests.get(image_url.replace("https://", "http://", 1), timeout=20, headers=DEFAULT_HTTP_HEADERS)
        else:
            raise
    response.raise_for_status()
    content_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[0].strip() or "image/jpeg"
    encoded = base64.b64encode(response.content).decode("utf-8")
    return f"data:{content_type};base64,{encoded}"


def mobygames_throttle() -> None:
    global _mobygames_last_request_at

    elapsed = time.monotonic() - _mobygames_last_request_at
    if elapsed < MOBYGAMES_MIN_REQUEST_INTERVAL:
        time.sleep(MOBYGAMES_MIN_REQUEST_INTERVAL - elapsed)
    _mobygames_last_request_at = time.monotonic()


def fetch_mobygames_html(url: str) -> str:
    cached = _mobygames_html_cache.get(url)
    if cached is not None:
        return cached

    mobygames_throttle()
    response = requests.get(url, timeout=20, headers=MOBYGAMES_HTTP_HEADERS)
    response.raise_for_status()
    _mobygames_html_cache[url] = response.text
    return response.text


def fetch_mobygames_soup(url: str) -> BeautifulSoup:
    return BeautifulSoup(fetch_mobygames_html(url), "html.parser")


def extract_mobygames_link(href: str) -> Optional[str]:
    if not href:
        return None
    if href.startswith("/"):
        href = urljoin("https://www.bing.com", href)
    parsed = urlparse(href)
    if "mobygames.com" in parsed.netloc and "/game/" in parsed.path:
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    if "bing.com" not in parsed.netloc:
        return None

    query_url = parse_qs(parsed.query).get("u") or parse_qs(parsed.query).get("url") or parse_qs(parsed.query).get("q")
    if not query_url:
        return None
    candidate = unquote(query_url[0])
    candidate_parsed = urlparse(candidate)
    if "mobygames.com" in candidate_parsed.netloc and "/game/" in candidate_parsed.path:
        return f"{candidate_parsed.scheme}://{candidate_parsed.netloc}{candidate_parsed.path}".rstrip("/")
    return None


def mobygames_platform_aliases(platform: str) -> List[str]:
    normalized = normalize_title_for_match(platform)
    aliases = [normalized]
    alias_map = {
        "nintendo 3ds": ["3ds", "nintendo 3ds"],
        "nintendo ds": ["ds", "nintendo ds", "nds"],
        "playstation 2": ["ps2", "playstation 2"],
        "playstation 3": ["ps3", "playstation 3"],
        "playstation 4": ["ps4", "playstation 4"],
        "xbox 360": ["xbox 360"],
        "xbox": ["xbox"],
        "wii": ["wii"],
        "gamecube": ["gamecube", "gc"],
        "game boy": ["game boy", "gb"],
        "game boy advance": ["game boy advance", "gba"],
        "playstation portable": ["psp", "playstation portable"],
        "playstation vita": ["ps vita", "vita", "playstation vita"],
        "nintendo switch": ["switch", "nintendo switch"],
    }
    for key, values in alias_map.items():
        if normalized == key:
            aliases.extend(values)
            break
    deduped: List[str] = []
    for alias in aliases:
        alias = alias.strip()
        if alias and alias not in deduped:
            deduped.append(alias)
    return deduped


def score_mobygames_candidate(candidate_title: str, candidate_platform: str, title: str, platform: str) -> int:
    target_title = normalize_launchbox_key(title)
    candidate_title_key = normalize_launchbox_key(candidate_title)
    target_title_loose = normalize_title_for_match(title)
    candidate_title_loose = normalize_title_for_match(candidate_title)
    target_tokens = set(title_tokens(title))
    candidate_tokens = set(title_tokens(candidate_title))
    score = 0

    if candidate_title_key == target_title:
        score += 140
    elif target_title and (target_title in candidate_title_key or candidate_title_key in target_title):
        score += 90

    if target_tokens and candidate_tokens:
        overlap = len(target_tokens.intersection(candidate_tokens))
        union = len(target_tokens.union(candidate_tokens))
        if union:
            score += int((overlap / union) * 80)

    if candidate_title_loose == target_title_loose:
        score += 20

    platform_haystack = normalize_title_for_match(candidate_platform)
    for alias in mobygames_platform_aliases(platform):
        if alias and alias in platform_haystack:
            score += 35
            break

    return score


def resolve_mobygames_game_detail(title: str, platform: str) -> Tuple[str, BeautifulSoup, str, str]:
    query = quote(f'site:mobygames.com/game "{title}" "{platform}"')
    search_url = f"https://www.bing.com/search?q={query}"
    search_response = requests.get(search_url, timeout=20, headers=MOBYGAMES_HTTP_HEADERS)
    search_response.raise_for_status()
    search_soup = BeautifulSoup(search_response.text, "html.parser")

    candidates: List[dict] = []
    seen_urls = set()
    for link in search_soup.find_all("a", href=True):
        resolved_href = extract_mobygames_link(link.get("href", ""))
        if not resolved_href or resolved_href in seen_urls:
            continue

        candidate_title = link.get_text(" ", strip=True)
        platform_slug = ""
        path_parts = [part for part in urlparse(resolved_href).path.split("/") if part]
        if len(path_parts) >= 3 and path_parts[0] == "game":
            platform_slug = path_parts[1].replace("-", " ")

        seen_urls.add(resolved_href)
        candidates.append({
            "title": candidate_title,
            "platform": platform_slug,
            "href": resolved_href,
        })

    if not candidates:
        raise HTTPException(status_code=404, detail=f'MobyGames could not find "{title}" for {platform}.')

    best_match = max(candidates, key=lambda candidate: score_mobygames_candidate(candidate["title"], candidate["platform"], title, platform))
    best_score = score_mobygames_candidate(best_match["title"], best_match["platform"], title, platform)
    if best_score < 90:
        raise HTTPException(status_code=404, detail=f'MobyGames did not return a confident match for "{title}" on {platform}.')

    detail_url = best_match["href"]
    detail_soup = fetch_mobygames_soup(detail_url)
    resolved_title = detail_soup.find("h1").get_text(" ", strip=True) if detail_soup.find("h1") else best_match["title"]
    resolved_platform = best_match["platform"] or platform
    return detail_url, detail_soup, resolved_platform, resolved_title


def mobygames_region_score(context: str) -> int:
    normalized = normalize_title_for_match(context)
    if any(term in normalized for term in ["north america", "usa", "u s a", "united states"]):
        return 2
    if re.search(r"\bus\b", normalized):
        return 2
    if any(term in normalized for term in ["japan", "europe", "germany", "france", "spain", "italy", "australia", "korea"]):
        return -1
    return 0


def mobygames_image_url(image_tag) -> Optional[str]:
    for attribute in ["data-src", "data-lazy", "src"]:
        image_url = image_tag.get(attribute)
        if image_url:
            return image_url.split(" ", 1)[0]
    srcset = image_tag.get("srcset")
    if srcset:
        return srcset.split(",", 1)[0].split(" ", 1)[0]
    return None


def mobygames_collect_context(image_tag) -> str:
    parts: List[str] = []
    for attribute in ["alt", "title", "aria-label"]:
        value = image_tag.get(attribute)
        if value:
            parts.append(value)

    parent = image_tag.parent
    if parent:
        parent_text = parent.get_text(" ", strip=True)
        if parent_text:
            parts.append(parent_text)

    ancestor = parent.parent if parent else None
    if ancestor:
        ancestor_text = ancestor.get_text(" ", strip=True)
        if ancestor_text:
            parts.append(ancestor_text)

    return " | ".join(part for part in parts if part)


def mobygames_art_type_matches(context: str, art_type: str, platform: str) -> bool:
    normalized = normalize_title_for_match(context)
    cartridge_platform = is_cartridge_platform_name(platform)

    if art_type == "cover":
        return any(term in normalized for term in ["cover", "box front", "front cover", "front box", "box"])
    if art_type == "spine":
        return any(term in normalized for term in ["spine", "side"])
    if art_type == "disc":
        if cartridge_platform:
            return any(term in normalized for term in ["cartridge", "cart", "label", "media"])
        return any(term in normalized for term in ["disc", "cd", "dvd", "media"])
    if art_type == "cart":
        return any(term in normalized for term in ["cartridge", "cart", "label"])
    return False


def mobygames_cover_gallery_links(detail_soup: BeautifulSoup, detail_url: str) -> List[str]:
    links: List[str] = []
    for anchor in detail_soup.find_all("a", href=True):
        href = anchor.get("href", "")
        label = anchor.get_text(" ", strip=True)
        full_url = urljoin(detail_url, href)
        parsed = urlparse(full_url)
        path = parsed.path.lower()
        if "/covers/" not in path and "cover" not in label.lower():
            continue
        normalized_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if normalized_url not in links:
            links.append(normalized_url)
    return links[:4]


def mobygames_extract_art_urls(page_soup: BeautifulSoup, page_url: str, art_type: str, platform: str) -> List[str]:
    candidates: List[Tuple[int, str]] = []
    seen = set()

    for image_tag in page_soup.find_all("img"):
        image_url = mobygames_image_url(image_tag)
        if not image_url or image_url.startswith("data:"):
            continue

        full_image_url = urljoin(page_url, image_url)
        if full_image_url in seen:
            continue

        context = mobygames_collect_context(image_tag)
        if not mobygames_art_type_matches(context, art_type, platform):
            continue

        region_score = mobygames_region_score(context)
        if region_score <= 0:
            continue

        seen.add(full_image_url)
        candidates.append((region_score, full_image_url))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [image_url for _score, image_url in candidates[:12]]


def fetch_mobygames_game_art_options(title: str, platform: str, art_type: str) -> dict:
    if art_type not in {"cover", "spine", "disc", "cart"}:
        raise HTTPException(status_code=400, detail="Invalid art_type. Use cover, disc, spine, or cart.")

    detail_url, detail_soup, resolved_platform, resolved_title = resolve_mobygames_game_detail(title, platform)
    gallery_urls = mobygames_cover_gallery_links(detail_soup, detail_url)
    search_pages = [detail_url, *gallery_urls]

    image_urls: List[str] = []
    for page_url in search_pages:
        page_soup = detail_soup if page_url == detail_url else fetch_mobygames_soup(page_url)
        for image_url in mobygames_extract_art_urls(page_soup, page_url, art_type, resolved_platform):
            if image_url not in image_urls:
                image_urls.append(image_url)

    if not image_urls:
        raise HTTPException(
            status_code=404,
            detail=f"MobyGames did not return an approved NTSC-US {art_type} image for {resolved_title}.",
        )

    data_uri_options: List[str] = []
    for image_url in image_urls:
        try:
            image_data = fetch_image_data_uri(image_url)
        except Exception:
            continue
        if image_data and image_data not in data_uri_options:
            data_uri_options.append(image_data)

    if not data_uri_options:
        raise HTTPException(status_code=502, detail="Could not download approved MobyGames art options.")

    return {
        "title": resolved_title,
        "platform": platform,
        "artType": art_type,
        "options": data_uri_options,
    }


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
    images = section_images_by_region(detail_soup, section_title, region)
    return images[0] if images else None


def section_images_by_region(detail_soup: BeautifulSoup, section_title: str, region: str = "North America") -> List[str]:
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
        return []
    article = heading.find_parent("article")
    if not article:
        return []
    images = []
    for image in article.find_all("img"):
        image_url = image.get("src")
        if not image_url:
            continue
        images.append((image.get("alt", ""), image_url))
    if not images:
        return []

    region_lower = (region or "").lower().strip()
    preferred = [image_url for alt, image_url in images if region_lower and region_lower in (alt or "").lower()]
    fallback = [image_url for alt, image_url in images if image_url not in preferred]

    ordered = preferred + fallback
    deduped: List[str] = []
    for image_url in ordered:
        if image_url and image_url not in deduped:
            deduped.append(image_url)
    return deduped


def section_image_from_titles(detail_soup: BeautifulSoup, titles: List[str], region: str = "North America") -> Optional[str]:
    images = section_images_from_titles(detail_soup, titles, region, limit=1)
    return images[0] if images else None


def section_images_from_titles(detail_soup: BeautifulSoup, titles: List[str], region: str = "North America", limit: int = 20) -> List[str]:
    collected: List[str] = []
    for title in titles:
        image_urls = section_images_by_region(detail_soup, title, region)
        if not image_urls:
            continue
        for image_url in image_urls:
            if image_url and image_url not in collected:
                collected.append(image_url)
                if len(collected) >= limit:
                    return collected
    return collected


def is_cartridge_platform_name(platform: Optional[str]) -> bool:
    case_type, _preset, _inferred = infer_system_appearance(platform or "", platform or "")
    return case_type == "cartridge"


def launchbox_disc_section_titles(platform: Optional[str]) -> List[str]:
    if is_cartridge_platform_name(platform):
        return [
            "Cart - Front",
            "Cartridge - Front",
            "Cartridge",
            "Cart",
            "Label - Front",
            "Disc",
        ]
    return ["Disc"]


def resolve_launchbox_game_detail(title: str, platform: str) -> Tuple[str, BeautifulSoup, str, str]:
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

        if candidate_title == target_title:
            candidate_score += 140
        elif target_title in candidate_title or candidate_title in target_title:
            candidate_score += 90

        if target_tokens and candidate_tokens:
            overlap = len(target_tokens.intersection(candidate_tokens))
            union = len(target_tokens.union(candidate_tokens))
            if union:
                candidate_score += int((overlap / union) * 80)

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
    resolved_platform = first_text_from_definition(detail_soup, "Platform") or best_match["platform"] or platform
    resolved_title = detail_soup.find("h1").get_text(" ", strip=True) if detail_soup.find("h1") else best_match["title"]
    return detail_url, detail_soup, resolved_platform, resolved_title


def fetch_launchbox_game_data(title: str, platform: str) -> dict:
    detail_url, detail_soup, resolved_platform, resolved_title = resolve_launchbox_game_detail(title, platform)

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

    cover_section_url = section_image_from_titles(detail_soup, ["Box - Front"])
    disc_section_titles = launchbox_disc_section_titles(resolved_platform)
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
        "title": resolved_title,
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


def fetch_launchbox_game_art_options(title: str, platform: str, art_type: str) -> dict:
    detail_url, detail_soup, resolved_platform, resolved_title = resolve_launchbox_game_detail(title, platform)

    if art_type == "cover":
        section_titles = ["Box - Front"]
    elif art_type == "spine":
        section_titles = [
            "Box - Spine",
            "Box Spine",
            "Spine",
            "Box - Spine (Left)",
            "Box - Spine (Right)",
            "Box - Side",
            "Case - Spine",
        ]
    elif art_type == "disc":
        section_titles = launchbox_disc_section_titles(resolved_platform)
    elif art_type == "cart":
        section_titles = [
            "Cart - Front",
            "Cartridge - Front",
            "Cartridge",
            "Cart",
            "Label - Front",
        ]
    else:
        raise HTTPException(status_code=400, detail="Invalid art_type. Use cover, disc, spine, or cart.")

    section_urls = section_images_from_titles(detail_soup, section_titles, limit=24)

    if art_type in {"disc", "cart"} and is_cartridge_platform_name(resolved_platform) and not section_urls:
        section_urls = section_images_from_titles(detail_soup, ["Box - Front"], limit=24)

    if art_type == "spine" and not section_urls:
        section_urls = section_images_from_titles(detail_soup, ["Box - Front"], limit=24)

    if not section_urls:
        raise HTTPException(status_code=404, detail="No LaunchBox art options found for that category.")

    data_uri_options: List[str] = []
    for section_url in section_urls:
        image_url = urljoin(detail_url, section_url)
        try:
            image_data = fetch_image_data_uri(image_url)
        except Exception:
            continue
        if image_data and image_data not in data_uri_options:
            data_uri_options.append(image_data)

    if not data_uri_options:
        raise HTTPException(status_code=502, detail="Could not download LaunchBox art options.")

    return {
        "title": resolved_title,
        "platform": resolved_platform,
        "artType": art_type,
        "options": data_uri_options,
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
        {"system_id": "3ds", "name": "Nintendo 3DS", "short_name": "3DS", "logo": "3DS",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/8/89/Nintendo_3DS_logo.svg", "case_type": "cartridge", "appearance_preset": "3ds"},
        {"system_id": "gb", "name": "GameBoy", "short_name": "GB", "logo": "GB",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/f/f2/Nintendo_Game_Boy_Logo.svg", "case_type": "cartridge", "appearance_preset": "gb"},
        {"system_id": "gc", "name": "GameCube", "short_name": "GC", "logo": "GC",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/2/29/Nintendo_GameCube_Official_Logo.svg", "case_type": "disc", "appearance_preset": "gamecube"},
        {"system_id": "nds", "name": "Nintendo DS", "short_name": "NDS", "logo": "NDS",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/a/af/Nintendo_DS_Logo.svg", "case_type": "cartridge", "appearance_preset": "nds"},
        {"system_id": "ps2", "name": "PlayStation 2", "short_name": "PS2", "logo": "PS2",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/7/76/PlayStation_2_logo.svg", "case_type": "disc", "appearance_preset": "ps2"},
        {"system_id": "ps3", "name": "PlayStation 3", "short_name": "PS3", "logo": "PS3",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/d/dc/PlayStation_3_logo.svg", "case_type": "disc", "appearance_preset": "ps3"},
        {"system_id": "ps4", "name": "PlayStation 4", "short_name": "PS4", "logo": "PS4",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/8/87/PlayStation_4_logo_and_wordmark.svg", "case_type": "disc", "appearance_preset": "ps4"},
        {"system_id": "wii", "name": "Wii", "short_name": "Wii", "logo": "Wii",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/b/bc/Wii.svg", "case_type": "disc", "appearance_preset": "wii"},
        {"system_id": "xbox", "name": "Xbox", "short_name": "XBX", "logo": "XBX",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/0/06/Xbox_wordmark.svg", "case_type": "disc", "appearance_preset": "xbox"},
        {"system_id": "xbox360", "name": "Xbox 360", "short_name": "360", "logo": "360",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/1/1b/Xbox_360_logo.svg", "case_type": "disc", "appearance_preset": "xbox360"},
    ]

    with Session(engine) as session:
        for order, system_data in enumerate(default_systems):
            existing = session.exec(select(GameSystem).where(GameSystem.system_id == system_data["system_id"])).first()
            if not existing:
                logo_image_data = None
                try:
                    logo_image_data = fetch_image_data_uri(system_data["logo_url"])
                except Exception:
                    pass  # If fetching fails, just leave logo_image as None

                system = GameSystem(
                    system_id=system_data["system_id"],
                    name=system_data["name"],
                    short_name=system_data["short_name"],
                    logo=system_data["logo"],
                    logo_image=logo_image_data,
                    case_type=system_data["case_type"],
                    appearance_preset=system_data["appearance_preset"],
                    is_cartridge_inferred=False,
                    display_order=order,
                )
                session.add(system)
            else:
                existing.case_type = system_data["case_type"]
                existing.appearance_preset = system_data["appearance_preset"]
                existing.is_cartridge_inferred = False
                if existing.display_order is None or existing.display_order == 0:
                    existing.display_order = order
                session.add(existing)
        session.commit()


def svg_data_uri(svg: str) -> str:
        return f"data:image/svg+xml;utf8,{quote(svg)}"


def make_case_cover_art(label: str, accent: str, accent_dark: str) -> str:
        svg = f"""
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 720 1080'>
    <defs>
        <linearGradient id='bg' x1='0' y1='0' x2='1' y2='1'>
            <stop offset='0%' stop-color='{accent}'/>
            <stop offset='100%' stop-color='{accent_dark}'/>
        </linearGradient>
    </defs>
    <rect width='720' height='1080' fill='url(#bg)'/>
    <rect x='34' y='34' width='652' height='1012' rx='26' fill='none' stroke='rgba(255,255,255,0.42)' stroke-width='6'/>
    <text x='360' y='450' fill='white' font-family='Arial, sans-serif' font-size='90' font-weight='700' text-anchor='middle'>CASE FIT</text>
    <text x='360' y='565' fill='white' font-family='Arial, sans-serif' font-size='80' font-weight='700' text-anchor='middle'>{label}</text>
    <text x='360' y='662' fill='rgba(255,255,255,0.92)' font-family='Arial, sans-serif' font-size='44' font-weight='600' text-anchor='middle'>ICON SCALE TEST</text>
</svg>
""".strip()
        return svg_data_uri(svg)


def make_case_spine_art(label: str, accent: str, accent_dark: str) -> str:
        svg = f"""
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 140 1080'>
    <defs>
        <linearGradient id='spine' x1='0' y1='0' x2='0' y2='1'>
            <stop offset='0%' stop-color='{accent}'/>
            <stop offset='100%' stop-color='{accent_dark}'/>
        </linearGradient>
    </defs>
    <rect width='140' height='1080' fill='url(#spine)'/>
    <rect x='12' y='12' width='116' height='1056' rx='14' fill='none' stroke='rgba(255,255,255,0.34)' stroke-width='4'/>
    <text x='70' y='540' fill='white' font-family='Arial, sans-serif' font-size='52' font-weight='700' text-anchor='middle' transform='rotate(-90 70 540)'>{label}</text>
</svg>
""".strip()
        return svg_data_uri(svg)


def make_disc_or_cartridge_art(label: str, accent: str, accent_dark: str, cartridge: bool) -> str:
        if cartridge:
                svg = f"""
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 440 540'>
    <defs>
        <linearGradient id='cart' x1='0' y1='0' x2='1' y2='1'>
            <stop offset='0%' stop-color='{accent}'/>
            <stop offset='100%' stop-color='{accent_dark}'/>
        </linearGradient>
    </defs>
    <rect width='440' height='540' rx='24' fill='url(#cart)'/>
    <rect x='22' y='22' width='396' height='496' rx='16' fill='none' stroke='rgba(255,255,255,0.42)' stroke-width='5'/>
    <text x='220' y='280' fill='white' font-family='Arial, sans-serif' font-size='62' font-weight='700' text-anchor='middle'>{label}</text>
</svg>
""".strip()
                return svg_data_uri(svg)

        svg = f"""
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 640 640'>
    <defs>
        <radialGradient id='disc' cx='35%' cy='30%' r='70%'>
            <stop offset='0%' stop-color='{accent}'/>
            <stop offset='100%' stop-color='{accent_dark}'/>
        </radialGradient>
    </defs>
    <circle cx='320' cy='320' r='312' fill='url(#disc)'/>
    <circle cx='320' cy='320' r='88' fill='rgba(0,0,0,0.36)'/>
    <text x='320' y='540' fill='white' font-family='Arial, sans-serif' font-size='58' font-weight='700' text-anchor='middle'>{label}</text>
</svg>
""".strip()
        return svg_data_uri(svg)


def ensure_console_test_games() -> None:
        presets = [
                {"platform": "PlayStation 2", "short": "PS2", "accent": "#2a49c8", "accent_dark": "#121a52", "cartridge": False},
                {"platform": "PlayStation 3", "short": "PS3", "accent": "#1f5ec6", "accent_dark": "#12264f", "cartridge": False},
                {"platform": "PlayStation 4", "short": "PS4", "accent": "#0f55aa", "accent_dark": "#0b1e3f", "cartridge": False},
                {"platform": "Nintendo DS", "short": "NDS", "accent": "#535a69", "accent_dark": "#1f2330", "cartridge": True},
                {"platform": "Nintendo 3DS", "short": "3DS", "accent": "#b3262d", "accent_dark": "#4f1215", "cartridge": True},
                {"platform": "GameBoy", "short": "GB", "accent": "#5d6b8f", "accent_dark": "#23314e", "cartridge": True},
                {"platform": "GameCube", "short": "GC", "accent": "#5a40a5", "accent_dark": "#291b53", "cartridge": False},
                {"platform": "Wii", "short": "WII", "accent": "#9ca7b8", "accent_dark": "#4b5665", "cartridge": False},
                {"platform": "Xbox", "short": "XBOX", "accent": "#2f9d44", "accent_dark": "#144920", "cartridge": False},
                {"platform": "Xbox 360", "short": "360", "accent": "#4ea95f", "accent_dark": "#244d2c", "cartridge": False},
        ]

        with Session(engine) as session:
                existing_platforms = {
                        platform
                        for platform in session.exec(
                                select(MediaItem.platform).where(MediaItem.category == "Games")
                        ).all()
                        if platform
                }

                created_any = False
                for preset in presets:
                        platform = preset["platform"]
                        if platform in existing_platforms:
                                continue

                        label = preset["short"]
                        cover = make_case_cover_art(label, preset["accent"], preset["accent_dark"])
                        spine = make_case_spine_art(label, preset["accent"], preset["accent_dark"])
                        disc = make_disc_or_cartridge_art(label, preset["accent"], preset["accent_dark"], preset["cartridge"])

                        item = MediaItem(
                                title=f"{platform} Case Fit Test",
                                category="Games",
                                platform=platform,
                                genre="Action",
                                genres="Action",
                                year_released=2006,
                                rating="E",
                                players=1,
                                cooperative="No",
                                publisher="PS2 Media Library",
                                notes="Auto-generated QA entry for verifying per-console case, spine, and cover scaling.",
                                cover_image=cover,
                                spine_image=spine,
                                disc_image=disc,
                        )
                        session.add(item)
                        created_any = True

                if created_any:
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
    ensure_star_rating_columns()
    ensure_system_case_type_column()
    ensure_system_appearance_preset_column()
    ensure_system_is_cartridge_inferred_column()
    ensure_system_display_order_column()
    ensure_systems()
    ensure_console_test_games()

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
            data = media_item_to_game_data(cached_item)
            data["data_source"] = "cache"
            return data

    fetched = fetch_game_data_with_fallback(title, platform)

    with Session(engine) as session:
        item_to_update = find_cached_game_item(session, title, platform, payload.item_id)
        if item_to_update:
            apply_fetched_game_data_to_item(item_to_update, fetched)

            session.add(item_to_update)
            session.commit()
            session.refresh(item_to_update)
            data = media_item_to_game_data(item_to_update)
            data["data_source"] = fetched.get("data_source", "launchbox")
            data["is_partial_fallback"] = bool(fetched.get("is_partial_fallback"))
            data["completeness"] = fetched.get("completeness")
            return data

    return fetched


@app.post("/api/refresh-game/{item_id}")
def refresh_game_data(item_id: int, authorization: Optional[str] = Header(default=None)) -> dict:
    require_admin(authorization)

    with Session(engine) as session:
        item = session.get(MediaItem, item_id)
        if not item or item.category != "Games":
            raise HTTPException(status_code=404, detail="Game item not found")

        if not item.title or not item.platform:
            raise HTTPException(status_code=400, detail="Game must have title and platform to refresh data")

        fetched = fetch_game_data_with_fallback(item.title, item.platform)
        apply_fetched_game_data_to_item(item, fetched)

        session.add(item)
        session.commit()
        session.refresh(item)

        data = media_item_to_game_data(item)
        data["data_source"] = fetched.get("data_source", "launchbox")
        data["is_partial_fallback"] = bool(fetched.get("is_partial_fallback"))
        data["completeness"] = fetched.get("completeness")
        return data


@app.post("/api/launchbox/game-art-options")
def fetch_game_art_options(payload: LaunchboxGameArtOptionsRequest, authorization: Optional[str] = Header(default=None)) -> dict:
    require_admin(authorization)

    title = payload.title.strip()
    platform = payload.platform.strip()
    art_type = payload.art_type.strip().lower()
    if not title or not platform:
        raise HTTPException(status_code=400, detail="Game title and platform are required.")

    if art_type not in {"cover", "disc", "spine", "cart"}:
        raise HTTPException(status_code=400, detail="Invalid art_type. Use cover, disc, spine, or cart.")

    try:
        return fetch_game_art_options_with_fallback(title, platform, art_type)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch art options: {exc}") from exc


@app.post("/api/deezer/music-data")
def fetch_music_data(payload: DeezerMusicDataRequest, authorization: Optional[str] = Header(default=None)) -> dict:
    require_admin(authorization)
    title = payload.title.strip()
    artist = payload.artist.strip()
    if not title or not artist:
        raise HTTPException(status_code=400, detail="Album title and artist are required.")

    try:
        return fetch_music_album_data(title, artist)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch music data: {exc}") from exc


@app.post("/api/bulk/games")
def bulk_upload_games(payload: BulkGamesRequest, authorization: Optional[str] = Header(default=None)) -> dict:
    """Bulk-create game entries by fetching metadata from LaunchBox."""
    require_admin(authorization)
    platform = (payload.platform or "").strip()
    if not platform:
        raise HTTPException(status_code=400, detail="A platform filter selection is required for bulk game upload.")

    results = []
    for raw_line in payload.items:
        line = raw_line.strip()
        if not line:
            continue
        title_part = line
        if not title_part:
            results.append({"line": line, "status": "error", "error": "Invalid format - provide a game title per line"})
            continue
        try:
            game_data = fetch_game_data_with_fallback(title_part, platform)
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
            platform=platform,
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
    """Get all gaming systems with their logos, sorted by display_order."""
    with Session(engine) as session:
        systems = session.exec(select(GameSystem).order_by(GameSystem.display_order)).all()
        return [
            {
                "id": s.system_id,
                "name": s.name,
                "shortName": s.short_name,
                "logo": s.logo,
                "logoImage": s.logo_image,
                "caseType": s.case_type,
                "appearancePreset": s.appearance_preset,
                "isCartridgeInferred": s.is_cartridge_inferred,
                "displayOrder": s.display_order,
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
    case_type = (system_data.get("caseType") or "").strip().lower()
    appearance_preset = (system_data.get("appearancePreset") or "").strip().lower() or None
    
    if not system_id or not name or not short_name:
        raise HTTPException(status_code=400, detail="Missing required fields: id, name, shortName")
    
    with Session(engine) as session:
        existing = session.exec(select(GameSystem).where(GameSystem.system_id == system_id)).first()
        if existing:
            raise HTTPException(status_code=409, detail="System ID already exists")

        inferred_case_type, inferred_preset, inferred_flag = infer_system_appearance(system_id, name)
        effective_case_type = case_type if case_type in {"disc", "cartridge", "hybrid"} else inferred_case_type
        effective_preset = appearance_preset or inferred_preset
        
        logo_image_data = None
        if logo_image_url.startswith("data:image"):
            logo_image_data = logo_image_url
        elif logo_image_url:
            try:
                logo_image_data = fetch_image_data_uri(logo_image_url)
            except Exception:
                pass
        
        system = GameSystem(
            system_id=system_id,
            name=name,
            short_name=short_name,
            logo=logo,
            logo_image=logo_image_data,
            case_type=effective_case_type,
            appearance_preset=effective_preset,
            is_cartridge_inferred=inferred_flag and not case_type,
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
            "caseType": system.case_type,
            "appearancePreset": system.appearance_preset,
            "isCartridgeInferred": system.is_cartridge_inferred,
            "displayOrder": system.display_order,
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
        if "caseType" in system_data:
            requested_case_type = (system_data.get("caseType") or "").strip().lower()
            if requested_case_type in {"disc", "cartridge", "hybrid"}:
                system.case_type = requested_case_type
                system.is_cartridge_inferred = False
            elif requested_case_type in {"", "auto"}:
                system.case_type = ""
        if "appearancePreset" in system_data:
            requested_preset = (system_data.get("appearancePreset") or "").strip().lower()
            system.appearance_preset = requested_preset or None
        
        # Handle logo image update (URL or base64)
        if "logoImageUrl" in system_data:
            logo_image_url = system_data["logoImageUrl"].strip()
            if logo_image_url.startswith("data:image"):
                system.logo_image = logo_image_url
            elif logo_image_url:
                try:
                    system.logo_image = fetch_image_data_uri(logo_image_url)
                except Exception:
                    pass

        if not system.case_type or not system.appearance_preset:
            inferred_case_type, inferred_preset, inferred_flag = infer_system_appearance(system.system_id, system.name)
            if not system.case_type:
                system.case_type = inferred_case_type
            if not system.appearance_preset:
                system.appearance_preset = inferred_preset
            system.is_cartridge_inferred = bool(inferred_flag and system.case_type == "cartridge")
        
        session.add(system)
        session.commit()
        session.refresh(system)
        
        return {
            "id": system.system_id,
            "name": system.name,
            "shortName": system.short_name,
            "logo": system.logo,
            "logoImage": system.logo_image,
            "caseType": system.case_type,
            "appearancePreset": system.appearance_preset,
            "isCartridgeInferred": system.is_cartridge_inferred,
            "displayOrder": system.display_order,
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


@app.patch("/api/systems/reorder")
def reorder_systems(payload: dict, authorization: Optional[str] = Header(default=None)):
    """Update display order for systems.
    
    Expected payload: {"order": ["system_id_1", "system_id_2", ...]}
    """
    require_admin(authorization)
    
    system_ids = payload.get("order", [])
    if not system_ids or not isinstance(system_ids, list):
        raise HTTPException(status_code=400, detail="Expected 'order' array of system IDs")
    
    with Session(engine) as session:
        for order, system_id in enumerate(system_ids):
            system = session.exec(select(GameSystem).where(GameSystem.system_id == system_id)).first()
            if system:
                system.display_order = order
                session.add(system)
        session.commit()
        
        return {"success": True}


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
