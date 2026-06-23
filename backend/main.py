from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple
import secrets
import base64
import hashlib
import hmac
import os
import re
import time
import unicodedata
import mimetypes
from urllib.parse import quote, urljoin

import requests
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlmodel import Field, Session, SQLModel, create_engine, select

DATABASE_PATH = Path(__file__).parent / "media.db"
FRONTEND_BUILD_DIR = Path(__file__).parent.parent / "frontend" / "build"
FRONTEND_PUBLIC_DIR = Path(__file__).parent.parent / "frontend" / "public"
BOOT_VIDEO_PATH = FRONTEND_PUBLIC_DIR / "ps2-intro.mp4"
BOOT_CAPTIONS_PATH = FRONTEND_PUBLIC_DIR / "ps2-intro.en.vtt"
FRONTEND_INDEX_PATH = FRONTEND_BUILD_DIR / "index.html"


def resolve_boot_video_path() -> Optional[Path]:
    candidates = (
        FRONTEND_PUBLIC_DIR / "ps2-intro.mp4",
        FRONTEND_BUILD_DIR / "ps2-intro.mp4",
    )
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def resolve_boot_captions_path() -> Optional[Path]:
    candidates = (
        FRONTEND_PUBLIC_DIR / "ps2-intro.en.vtt",
        FRONTEND_BUILD_DIR / "ps2-intro.en.vtt",
    )
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None

app = FastAPI(title="PS2 Media Library API")

DEFAULT_ADMIN_PASSWORD = "foreverandalways2015"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "").strip()
ADMIN_TOKEN_TTL_SECONDS = 60 * 60 * 12
admin_tokens: Dict[str, float] = {}


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


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


ENABLE_KEYLESS_METADATA_FALLBACK = env_flag("ENABLE_KEYLESS_METADATA_FALLBACK", default=True)
LAUNCHBOX_MIN_REQUEST_INTERVAL = env_float("LAUNCHBOX_MIN_REQUEST_INTERVAL", default=1.5)
DEEZER_MIN_REQUEST_INTERVAL = env_float("DEEZER_MIN_REQUEST_INTERVAL", default=1.5)
ADMIN_TOKEN_TTL_SECONDS = env_int("ADMIN_TOKEN_TTL_SECONDS", default=60 * 60 * 12)
DEFAULT_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0"}
_launchbox_last_request_at = 0.0
_deezer_last_request_at = 0.0


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def verify_password_hash(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = encoded_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = _b64url_decode(salt_raw)
        expected_digest = _b64url_decode(digest_raw)
        candidate_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(candidate_digest, expected_digest)
    except Exception:
        return False


def verify_admin_password(password: str) -> bool:
    if ADMIN_PASSWORD_HASH:
        return verify_password_hash(password, ADMIN_PASSWORD_HASH)
    return hmac.compare_digest(password, ADMIN_PASSWORD)


def detect_media_type(path: Path) -> Optional[str]:
    suffix = path.suffix.lower()
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix == ".vtt":
        return "text/vtt"
    guessed, _encoding = mimetypes.guess_type(str(path))
    return guessed


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
    display_order: int = Field(default=0)


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


class DeezerAlbumArtOptionsRequest(SQLModel):
    album: str
    artist: str


class DeezerAlbumDataRequest(SQLModel):
    album: str
    artist: str
    item_id: Optional[int] = None


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


def ensure_media_display_order_column() -> None:
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(mediaitem)")).fetchall()
        has_display_order = any(column[1] == "display_order" for column in columns)
        if not has_display_order:
            connection.execute(text("ALTER TABLE mediaitem ADD COLUMN display_order INTEGER DEFAULT 0"))

        categories = [row[0] for row in connection.execute(text("SELECT DISTINCT category FROM mediaitem WHERE category IS NOT NULL")).fetchall()]
        for category in categories:
            items = connection.execute(
                text("SELECT id FROM mediaitem WHERE category = :category ORDER BY title ASC, id ASC"),
                {"category": category},
            ).fetchall()
            for order, (item_id,) in enumerate(items):
                connection.execute(
                    text("UPDATE mediaitem SET display_order = :order WHERE id = :item_id"),
                    {"order": order, "item_id": item_id},
                )


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


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

_TITLE_MAX_LENGTH = 200
_PLATFORM_MAX_LENGTH = 100

# Patterns that have no place in a video-game title but indicate injection attempts,
# URL-based abuse, or clearly non-game text.
_TITLE_BLOCKED_RE = re.compile(
    r"<[^>]*>"                          # HTML / XML tags
    r"|https?://"                       # full URLs
    r"|www\."                           # bare host URLs
    r"|\x00"                            # null bytes
    r"|[\x01-\x08\x0b\x0c\x0e-\x1f]"   # non-printable control chars (allow \t \n \r)
    r"|\bSELECT\b|\bDROP\b|\bINSERT\b|\bDELETE\b|\bUPDATE\b|\bUNION\b"  # SQL DML/DDL
    r"|--|;\s*\w"                        # SQL comment / chaining
    r"|\beval\s*\(|\bexec\s*\("         # code-execution keywords
    r"|\bscript\b",                     # <script> keyword without tag brackets
    re.IGNORECASE,
)

# A game title must have at least one letter or digit (not blank / pure punctuation).
_TITLE_HAS_ALPHANUMERIC = re.compile(r"[a-zA-Z0-9]")


def validate_game_title_input(title: str) -> None:
    """Raise 400 HTTPException if *title* fails basic game-title sanity checks."""
    if not title:
        raise HTTPException(status_code=400, detail="Game title is required.")
    if len(title) < 2:
        raise HTTPException(status_code=400, detail="Game title is too short to search.")
    if len(title) > _TITLE_MAX_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Game title must be {_TITLE_MAX_LENGTH} characters or fewer.",
        )
    if not _TITLE_HAS_ALPHANUMERIC.search(title):
        raise HTTPException(
            status_code=400,
            detail="Game title must contain at least one letter or digit.",
        )
    if _TITLE_BLOCKED_RE.search(title):
        raise HTTPException(
            status_code=400,
            detail="Game title contains invalid characters or patterns. Enter a plain game title.",
        )


def validate_platform_input(platform: str) -> None:
    """Raise 400 HTTPException if *platform* fails basic sanity checks."""
    if not platform:
        raise HTTPException(status_code=400, detail="Platform is required.")
    if len(platform) > _PLATFORM_MAX_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Platform name must be {_PLATFORM_MAX_LENGTH} characters or fewer.",
        )
    if _TITLE_BLOCKED_RE.search(platform):
        raise HTTPException(
            status_code=400,
            detail="Platform name contains invalid characters or patterns.",
        )


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

    # Verify the entity is actually a video game (P31 instance-of Q7889 or related types).
    # This prevents the Wikidata fallback from returning metadata for non-game entities
    # that happen to share a name with a search query.
    _VIDEO_GAME_ENTITY_IDS = {
        "Q7889",    # video game
        "Q16927802", # video game series
        "Q20238256", # video game expansion pack
        "Q1756915",  # video game remake
        "Q209163",   # expansion pack
    }
    instance_of_claims = claims.get("P31") or []
    instance_ids = {
        (((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}).get("id")
        for c in instance_of_claims
    }
    if not instance_ids.intersection(_VIDEO_GAME_ENTITY_IDS):
        # Also accept if the candidate description explicitly mentions video game
        # (some entries are only categorised under a sub-type of Q7889)
        candidate_desc = (best_candidate.get("description") or "").lower()
        if "video game" not in candidate_desc and "videogame" not in candidate_desc:
            return None

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
        raise HTTPException(
            status_code=404,
            detail=(
                f"Could not fetch {art_type} art. LaunchBox art is unavailable."
                " Use manual upload while LaunchBox is down."
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
    """Fetch album cover art from Deezer API."""
    deezer_throttle()
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


def fetch_deezer_album_art_options(album: str, artist: str) -> dict:
    """Fetch multiple album art options from Deezer API."""
    deezer_throttle()
    url = f"https://api.deezer.com/search/album?q={quote(artist + ' ' + album)}&limit=25"
    response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    items = response.json().get("data", [])
    if not items:
        raise HTTPException(status_code=404, detail=f'Could not find "{album}" by {artist} on Deezer.')

    ranked = sorted(items, key=lambda i: score_music_match(i, artist, album), reverse=True)
    
    data_uri_options: List[str] = []
    for item in ranked:
        # Try to get the best available cover image size
        cover_url = item.get("cover_xl") or item.get("cover_big") or item.get("cover_medium")
        if not cover_url:
            continue
        try:
            image_data = fetch_image_data_uri(cover_url)
            if image_data and image_data not in data_uri_options:
                data_uri_options.append(image_data)
        except Exception:
            continue
        if len(data_uri_options) >= 12:  # Limit to 12 options like LaunchBox
            break

    if not data_uri_options:
        raise HTTPException(status_code=502, detail="Could not download Deezer album art options.")

    best = ranked[0]
    return {
        "title": best.get("title", album),
        "artist": best.get("artist", {}).get("name", artist) if isinstance(best.get("artist"), dict) else artist,
        "options": data_uri_options,
    }


def fetch_deezer_full_album_data(album: str, artist: str) -> dict:
    """Fetch full album metadata from Deezer including genres, release date, cover art, and track list."""
    deezer_throttle()
    search_url = f"https://api.deezer.com/search/album?q={quote(artist + ' ' + album)}&limit=25"
    response = requests.get(search_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    items = response.json().get("data", [])
    if not items:
        raise HTTPException(status_code=404, detail=f'Could not find "{album}" by {artist} on Deezer.')

    ranked = sorted(items, key=lambda i: score_music_match(i, artist, album), reverse=True)
    best = ranked[0]
    album_id = best.get("id")

    # Fetch full album details for genres and complete metadata
    genres: List[str] = []
    release_date: Optional[str] = None
    label: Optional[str] = None
    track_list: Optional[str] = None
    if album_id:
        try:
            detail_response = requests.get(
                f"https://api.deezer.com/album/{album_id}",
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            detail_response.raise_for_status()
            detail = detail_response.json()
            genres_data = detail.get("genres", {}).get("data", [])
            genres = [g["name"] for g in genres_data if g.get("name")]
            release_date = detail.get("release_date") or None
            label = detail.get("label") or None
            
            # Fetch track list from the album detail
            tracks_data = detail.get("tracks", {}).get("data", [])
            if tracks_data:
                track_lines = []
                for i, track in enumerate(tracks_data, 1):
                    track_title = track.get("title", "Unknown")
                    track_artist = ""
                    track_artist_obj = track.get("artist")
                    if isinstance(track_artist_obj, dict):
                        track_artist = track_artist_obj.get("name", "")
                    elif isinstance(track_artist_obj, str):
                        track_artist = track_artist_obj
                    
                    if track_artist:
                        track_lines.append(f"{i}. {track_title} - {track_artist}")
                    else:
                        track_lines.append(f"{i}. {track_title}")
                
                track_list = "\n".join(track_lines)
        except Exception:
            pass

    # Fall back to search-result release_date if detail call failed
    if not release_date:
        release_date = best.get("release_date") or None

    cover_url = best.get("cover_xl") or best.get("cover_big") or best.get("cover_medium") or ""
    cover_image: Optional[str] = None
    if cover_url:
        try:
            cover_image = fetch_image_data_uri(cover_url)
        except Exception:
            cover_image = None

    return {
        "title": best.get("title", album),
        "artist": best.get("artist", {}).get("name", artist) if isinstance(best.get("artist"), dict) else artist,
        "release_date": release_date,
        "genre": genres[0] if genres else None,
        "genres": genres,
        "label": label,
        "coverImage": cover_image,
        "trackList": track_list,
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


def launchbox_throttle() -> None:
    """Enforce a minimum interval between outbound LaunchBox requests.

    Called once per game lookup (before the search page fetch) so that bulk
    uploads of 100+ games do not hammer gamesdb.launchbox-app.com.
    The interval is governed by LAUNCHBOX_MIN_REQUEST_INTERVAL (default 1.5 s).
    """
    global _launchbox_last_request_at

    elapsed = time.monotonic() - _launchbox_last_request_at
    if elapsed < LAUNCHBOX_MIN_REQUEST_INTERVAL:
        time.sleep(LAUNCHBOX_MIN_REQUEST_INTERVAL - elapsed)
    _launchbox_last_request_at = time.monotonic()


def deezer_throttle() -> None:
    """Enforce a minimum interval between outbound Deezer lookups.

    Called once per album lookup (before the search API call) so bulk uploads
    do not spam api.deezer.com with tightly looped requests.
    The interval is governed by DEEZER_MIN_REQUEST_INTERVAL (default 1.5 s).
    """
    global _deezer_last_request_at

    elapsed = time.monotonic() - _deezer_last_request_at
    if elapsed < DEEZER_MIN_REQUEST_INTERVAL:
        time.sleep(DEEZER_MIN_REQUEST_INTERVAL - elapsed)
    _deezer_last_request_at = time.monotonic()




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
    launchbox_throttle()
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
    if not token:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    expires_at = admin_tokens.get(token)
    if expires_at is None:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    if expires_at <= time.time():
        del admin_tokens[token]
        raise HTTPException(status_code=401, detail="Admin token expired")


def ensure_systems() -> None:
    """Initialize default gaming systems if they don't exist."""
    default_systems = [
        {"system_id": "3ds", "name": "Nintendo 3DS", "short_name": "3DS", "logo": "3DS",
         "logo_url": "https://upload.wikimedia.org/wikipedia/commons/8/89/Nintendo_3DS_logo.svg", "case_type": "cartridge", "appearance_preset": "3ds"},
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


@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()
    ensure_release_date_column()
    ensure_rating_column()
    ensure_genres_column()
    ensure_cooperative_column()
    ensure_disc_image_column()
    ensure_spine_image_column()
    ensure_media_display_order_column()
    ensure_system_case_type_column()
    ensure_system_appearance_preset_column()
    ensure_system_is_cartridge_inferred_column()
    ensure_system_display_order_column()

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
        query = query.order_by(MediaItem.display_order, MediaItem.title, MediaItem.id)
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
    if not verify_admin_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    token = secrets.token_urlsafe(32)
    admin_tokens[token] = time.time() + ADMIN_TOKEN_TTL_SECONDS
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
        max_display_order = session.exec(
            select(MediaItem.display_order)
            .where(MediaItem.category == item.category)
            .order_by(MediaItem.display_order.desc())
        ).first()
        item.display_order = (max_display_order if max_display_order is not None else -1) + 1
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
    validate_game_title_input(title)
    validate_platform_input(platform)

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
    validate_game_title_input(title)
    validate_platform_input(platform)

    if art_type not in {"cover", "disc", "spine", "cart"}:
        raise HTTPException(status_code=400, detail="Invalid art_type. Use cover, disc, spine, or cart.")

    try:
        return fetch_game_art_options_with_fallback(title, platform, art_type)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch art options: {exc}") from exc


@app.post("/api/deezer/album-art-options")
def fetch_deezer_album_art(payload: DeezerAlbumArtOptionsRequest, authorization: Optional[str] = Header(default=None)) -> dict:
    require_admin(authorization)

    album = payload.album.strip()
    artist = payload.artist.strip()
    if not album or not artist:
        raise HTTPException(status_code=400, detail="Album name and artist are required.")

    try:
        return fetch_deezer_album_art_options(album, artist)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch album art options: {exc}") from exc


@app.post("/api/deezer/album-data")
def fetch_deezer_album_data(payload: DeezerAlbumDataRequest, authorization: Optional[str] = Header(default=None)) -> dict:
    require_admin(authorization)

    album = payload.album.strip()
    artist = payload.artist.strip()
    if not album or not artist:
        raise HTTPException(status_code=400, detail="Album name and artist are required.")

    try:
        return fetch_deezer_full_album_data(album, artist)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch album data: {exc}") from exc


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
    """Bulk-create music entries by fetching metadata from Deezer."""
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
        if not album_part or not artist_part:
            results.append({"line": line, "status": "error", "error": "Invalid format - use: Album Title - Artist"})
            continue
        try:
            music_data = fetch_deezer_full_album_data(album_part, artist_part)
        except HTTPException as exc:
            results.append({"line": line, "status": "error", "error": exc.detail})
            continue
        except Exception as exc:
            results.append({"line": line, "status": "error", "error": str(exc)})
            continue

        release_date_iso = normalize_release_date(music_data.get("release_date"))
        year_released = None
        if release_date_iso and len(release_date_iso) >= 4:
            try:
                year_released = int(release_date_iso[:4])
            except ValueError:
                year_released = None

        genres = [entry.strip() for entry in music_data.get("genres", []) if isinstance(entry, str) and entry.strip()]
        genre = music_data.get("genre")
        if not genre and genres:
            genre = genres[0]
        if isinstance(genre, str):
            genre = genre.strip()
        else:
            genre = ""

        item = MediaItem(
            title=music_data.get("title", album_part),
            category="Music",
            platform=None,
            genre=genre,
            genres=", ".join(genres) if genres else None,
            release_date=release_date_iso,
            year_released=year_released,
            artist=music_data.get("artist", artist_part),
            publisher=music_data.get("label"),
            cover_image=music_data.get("coverImage"),
            notes=music_data.get("trackList"),
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


@app.patch("/api/media/reorder")
def reorder_media_items(payload: dict, authorization: Optional[str] = Header(default=None)):
    """Update display order for media items.

    Expected payload:
      {
        "category": "Games" | "Music",
        "order": [1, 2, 3, ...],
        "platform": "PlayStation 2"  # optional for Games
      }
    """
    require_admin(authorization)

    category = payload.get("category")
    item_ids = payload.get("order", [])
    platform = payload.get("platform")

    if category not in {"Games", "Music"}:
        raise HTTPException(status_code=400, detail="Expected valid 'category' value")
    if not item_ids or not isinstance(item_ids, list):
        raise HTTPException(status_code=400, detail="Expected 'order' array of media IDs")

    with Session(engine) as session:
        query = select(MediaItem).where(MediaItem.category == category)
        if category == "Games" and platform:
            query = query.where(MediaItem.platform == platform)

        scoped_items = session.exec(query).all()
        scoped_by_id = {item.id: item for item in scoped_items if item.id is not None}

        for order, item_id in enumerate(item_ids):
            media_item = scoped_by_id.get(item_id)
            if media_item:
                media_item.display_order = order
                session.add(media_item)

        session.commit()

        return {"success": True}


_VIDEO_PROXY_HEADERS = {
    "Cache-Control": "no-store, no-transform",
    "X-Accel-Buffering": "no",
    "X-Content-Type-Options": "nosniff",
}


@app.get("/api/boot-video")
def stream_ps2_intro(request: Request):
    boot_video_path = resolve_boot_video_path()
    if not boot_video_path:
        raise HTTPException(status_code=404, detail="Intro video not found")

    file_size = boot_video_path.stat().st_size
    raw_headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in request.scope.get("headers", [])}
    range_header = raw_headers.get("range") or request.headers.get("range")

    base_headers = {
        **_VIDEO_PROXY_HEADERS,
        "Accept-Ranges": "bytes",
        "Content-Type": "video/mp4",
    }

    if not range_header:
        full_headers = {
            **base_headers,
            "Content-Length": str(file_size),
        }
        return StreamingResponse(
            iter_file_range(boot_video_path, 0, file_size - 1),
            status_code=200,
            headers=full_headers,
        )

    if not range_header.startswith("bytes="):
        raise HTTPException(status_code=416, detail="Invalid range header")

    start_str, end_str = range_header.replace("bytes=", "").split("-", 1)
    start = int(start_str) if start_str else 0
    end = int(end_str) if end_str else file_size - 1

    if start >= file_size:
        raise HTTPException(status_code=416, detail="Requested range not satisfiable")

    end = min(end, file_size - 1)
    content_length = end - start + 1

    range_headers = {
        **base_headers,
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Length": str(content_length),
    }
    return StreamingResponse(iter_file_range(boot_video_path, start, end), status_code=206, headers=range_headers)


@app.head("/api/boot-video")
def head_ps2_intro() -> Response:
    boot_video_path = resolve_boot_video_path()
    if not boot_video_path:
        raise HTTPException(status_code=404, detail="Intro video not found")

    file_size = boot_video_path.stat().st_size
    return Response(
        status_code=200,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": "video/mp4",
        },
    )


@app.get("/api/boot-captions.vtt")
def stream_ps2_intro_captions() -> FileResponse:
    boot_captions_path = resolve_boot_captions_path()
    if not boot_captions_path:
        raise HTTPException(status_code=404, detail="Boot captions not found")
    return FileResponse(boot_captions_path, media_type="text/vtt")


@app.head("/api/boot-captions.vtt")
def head_ps2_intro_captions() -> Response:
    boot_captions_path = resolve_boot_captions_path()
    if not boot_captions_path:
        raise HTTPException(status_code=404, detail="Boot captions not found")

    file_size = boot_captions_path.stat().st_size
    return Response(
        status_code=200,
        headers={
            "Content-Length": str(file_size),
            "Content-Type": "text/vtt",
        },
    )


if FRONTEND_INDEX_PATH.exists():
    @app.get("/")
    async def frontend_root() -> FileResponse:
        return FileResponse(FRONTEND_INDEX_PATH)

    @app.get("/{path_name:path}")
    async def frontend(path_name: str) -> FileResponse:
        public_path = FRONTEND_PUBLIC_DIR / path_name
        if public_path.exists() and public_path.is_file():
            return FileResponse(public_path, media_type=detect_media_type(public_path))

        file_path = FRONTEND_BUILD_DIR / path_name
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path, media_type=detect_media_type(file_path))
        return FileResponse(FRONTEND_INDEX_PATH)
else:
    @app.get("/")
    async def frontend_root():
        raise HTTPException(status_code=503, detail="Frontend build not found. Run npm run build.")

    @app.get("/{path_name:path}")
    async def frontend(path_name: str):
        raise HTTPException(status_code=503, detail="Frontend build not found. Run npm run build.")
