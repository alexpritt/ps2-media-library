from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple
from difflib import SequenceMatcher
import secrets
import base64
import io
import json
import logging
import os
import re
import threading
import time
import unicodedata
from defusedxml import ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

import requests
try:
    import cloudscraper
except Exception:  # pragma: no cover - optional dependency fallback
    cloudscraper = None
from fastapi import Body, FastAPI, Header, HTTPException, Query, Request
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
ENABLE_IGDB_FALLBACK = env_flag("ENABLE_IGDB_FALLBACK", default=True)
ENABLE_LIBRETRO_BOXART = env_flag("ENABLE_LIBRETRO_BOXART", default=True)
ENABLE_PRICE_AUTO_REFRESH = env_flag("ENABLE_PRICE_AUTO_REFRESH", default=True)
MOBYGAMES_MIN_REQUEST_INTERVAL = env_float("MOBYGAMES_MIN_REQUEST_INTERVAL", default=1.5)
LAUNCHBOX_METADATA_REFRESH_SECONDS = max(300.0, env_float("LAUNCHBOX_METADATA_REFRESH_SECONDS", default=86400.0))
LAUNCHBOX_METADATA_ZIP_URL = (os.getenv("LAUNCHBOX_METADATA_ZIP_URL") or "").strip()
PRICE_MIN_REQUEST_INTERVAL = max(1.0, env_float("PRICE_MIN_REQUEST_INTERVAL", default=3.0))
PRICE_REFRESH_INTERVAL_SECONDS = max(3600.0, env_float("PRICE_REFRESH_INTERVAL_SECONDS", default=21600.0))
PRICE_REFRESH_BATCH_SIZE = max(1, int(env_float("PRICE_REFRESH_BATCH_SIZE", default=5.0)))
PRICE_REFRESH_DUE_DAYS = max(28, int(env_float("PRICE_REFRESH_DUE_DAYS", default=30.0)))
DISCOGS_USER_TOKEN = (os.getenv("DISCOGS_USER_TOKEN") or "").strip()

IGDB_CLIENT_ID = (os.getenv("IGDB_CLIENT_ID") or "").strip()
IGDB_CLIENT_SECRET = (os.getenv("IGDB_CLIENT_SECRET") or "").strip()
IGDB_OAUTH_URL = "https://id.twitch.tv/oauth2/token"
IGDB_API_BASE_URL = "https://api.igdb.com/v4"

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
_igdb_access_token: Optional[str] = None
_igdb_access_token_expiry = 0.0
_launchbox_metadata_cache: List[dict] = []
_launchbox_metadata_last_refresh_at = 0.0
_launchbox_metadata_source_url: Optional[str] = None
_launchbox_metadata_last_error: Optional[str] = None
_pricing_last_request_at = 0.0
_pricing_request_lock = threading.Lock()
_pricing_scheduler_started = False
logger = logging.getLogger("ps2-media-library")

PRICE_USER_AGENT = "PS2MediaLibrary/1.0 (+https://theavenoircollection.com)"

LIBRETRO_PLATFORM_REPO_ALIASES: Dict[str, List[str]] = {
    "playstation 2": ["Sony - PlayStation 2"],
    "playstation 3": ["Sony - PlayStation 3"],
    "playstation 4": ["Sony - PlayStation 4"],
    "playstation": ["Sony - PlayStation"],
    "playstation portable": ["Sony - PlayStation Portable"],
    "playstation vita": ["Sony - PlayStation Vita"],
    "nintendo ds": ["Nintendo - Nintendo DS"],
    "nintendo 3ds": ["Nintendo - Nintendo 3DS"],
    "game boy": ["Nintendo - Game Boy"],
    "game boy color": ["Nintendo - Game Boy Color"],
    "game boy advance": ["Nintendo - Game Boy Advance"],
    "gamecube": ["Nintendo - GameCube"],
    "wii": ["Nintendo - Wii"],
    "xbox": ["Microsoft - Xbox"],
    "xbox 360": ["Microsoft - Xbox 360"],
}

IGDB_PLATFORM_IDS: Dict[str, List[int]] = {
    "playstation": [7],
    "playstation 2": [8],
    "playstation 3": [9],
    "playstation 4": [48],
    "playstation 5": [167],
    "playstation portable": [38],
    "playstation vita": [46],
    "xbox": [11],
    "xbox 360": [12],
    "xbox one": [49],
    "xbox series": [169],
    "nintendo ds": [20],
    "nintendo 3ds": [37],
    "wii": [5],
    "wii u": [41],
    "gamecube": [21],
    "game boy": [33],
    "game boy advance": [24],
    "nintendo switch": [130],
}


def safe_fetch_image_data_uri(image_url: Optional[str]) -> Optional[str]:
    if not image_url:
        return None
    try:
        return fetch_image_data_uri(image_url)
    except Exception:
        return None


def ensure_igdb_access_token(force_refresh: bool = False) -> Optional[str]:
    global _igdb_access_token, _igdb_access_token_expiry

    if not ENABLE_IGDB_FALLBACK:
        return None
    if not IGDB_CLIENT_ID or not IGDB_CLIENT_SECRET:
        return None

    now = time.monotonic()
    if not force_refresh and _igdb_access_token and now < (_igdb_access_token_expiry - 60.0):
        return _igdb_access_token

    token_response = requests.post(
        IGDB_OAUTH_URL,
        params={
            "client_id": IGDB_CLIENT_ID,
            "client_secret": IGDB_CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
        timeout=20,
        headers=DEFAULT_HTTP_HEADERS,
    )
    token_response.raise_for_status()
    payload = token_response.json() or {}

    token = payload.get("access_token")
    expires_in = payload.get("expires_in") or 3600
    if not token:
        return None

    _igdb_access_token = str(token)
    _igdb_access_token_expiry = now + float(expires_in)
    return _igdb_access_token


def igdb_post(endpoint: str, apicalypse_query: str) -> list:
    token = ensure_igdb_access_token()
    if not token:
        return []

    url = f"{IGDB_API_BASE_URL}/{endpoint.lstrip('/')}"
    headers = {
        "Client-ID": IGDB_CLIENT_ID,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    response = requests.post(url, data=apicalypse_query, headers=headers, timeout=25)
    if response.status_code == 401:
        token = ensure_igdb_access_token(force_refresh=True)
        if not token:
            return []
        headers["Authorization"] = f"Bearer {token}"
        response = requests.post(url, data=apicalypse_query, headers=headers, timeout=25)

    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def igdb_cover_url(raw_url: Optional[str]) -> Optional[str]:
    if not raw_url:
        return None
    url = raw_url.strip()
    if url.startswith("//"):
        url = f"https:{url}"
    return re.sub(r"/t_[^/]+/", "/t_1080p/", url)


def igdb_platform_ids_for(platform: str) -> List[int]:
    normalized = normalize_title_for_match(platform)
    if normalized in IGDB_PLATFORM_IDS:
        return IGDB_PLATFORM_IDS[normalized]
    for key, ids in IGDB_PLATFORM_IDS.items():
        if key in normalized or normalized in key:
            return ids
    return []


def score_igdb_candidate(name: str, title: str, platform_name: str, platform: str) -> int:
    score = 0
    target_key = normalize_launchbox_key(title)
    candidate_key = normalize_launchbox_key(name)
    target_loose = normalize_title_for_match(title)
    candidate_loose = normalize_title_for_match(name)
    target_tokens = set(title_tokens(title))
    candidate_tokens = set(title_tokens(name))

    if candidate_key == target_key:
        score += 140
    elif target_key and (target_key in candidate_key or candidate_key in target_key):
        score += 90

    if target_tokens and candidate_tokens:
        overlap = len(target_tokens.intersection(candidate_tokens))
        union = len(target_tokens.union(candidate_tokens))
        if union:
            score += int((overlap / union) * 80)

    if target_loose and candidate_loose:
        similarity = SequenceMatcher(None, target_loose, candidate_loose).ratio()
        score += int(similarity * 50)

    platform_haystack = normalize_title_for_match(platform_name)
    target_platform = normalize_title_for_match(platform)
    if target_platform and (target_platform in platform_haystack or platform_haystack in target_platform):
        score += 35

    return score


def map_igdb_esrb_rating(age_ratings: list) -> Optional[str]:
    if not isinstance(age_ratings, list):
        return None
    # IGDB category=1 is ESRB. Common rating enum values map to RP/E/E10/T/M/AO.
    esrb_map = {
        6: "RP",
        7: "EC",
        8: "E",
        9: "E10+",
        10: "T",
        11: "M",
        12: "AO",
    }
    for entry in age_ratings:
        if not isinstance(entry, dict):
            continue
        if entry.get("category") != 1:
            continue
        mapped = esrb_map.get(entry.get("rating"))
        if mapped:
            return mapped
    return None


def launchbox_metadata_candidate_urls() -> List[str]:
    urls: List[str] = []
    if LAUNCHBOX_METADATA_ZIP_URL:
        urls.append(LAUNCHBOX_METADATA_ZIP_URL)

    urls.extend(
        [
            "https://gamesdb.launchbox-app.com/metadata.zip",
            "https://gamesdb.launchbox-app.com/Metadata.zip",
            "https://gamesdb.launchbox-app.com/downloads/metadata.zip",
            "https://gamesdb.launchbox-app.com/downloads/Metadata.zip",
            "https://gamesdb.launchbox-app.com",
            "https://gamesdb.launchbox-app.com/downloads",
        ]
    )

    deduped: List[str] = []
    for url in urls:
        if url and url not in deduped:
            deduped.append(url)
    return deduped


def try_download_launchbox_metadata_zip() -> Tuple[Optional[bytes], Optional[str]]:
    for candidate_url in launchbox_metadata_candidate_urls():
        try:
            response = requests.get(candidate_url, timeout=30, headers=DEFAULT_HTTP_HEADERS)
        except requests.RequestException:
            continue

        if not response.ok:
            continue

        content_type = (response.headers.get("content-type") or "").lower()
        content = response.content

        if candidate_url.lower().endswith(".zip") or "application/zip" in content_type or content[:2] == b"PK":
            return content, candidate_url

        if "html" not in content_type:
            continue

        try:
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception:
            continue

        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")
            label = (anchor.get_text(" ", strip=True) or "").lower()
            href_lower = href.lower()
            if ".zip" not in href_lower:
                continue
            if "metadata" not in href_lower and "metadata" not in label and "games" not in label:
                continue
            resolved = urljoin(candidate_url, href)
            try:
                zip_response = requests.get(resolved, timeout=45, headers=DEFAULT_HTTP_HEADERS)
            except requests.RequestException:
                continue
            if zip_response.ok and zip_response.content[:2] == b"PK":
                return zip_response.content, resolved

    return None, None


def parse_launchbox_metadata_zip_entries(zip_content: bytes) -> List[dict]:
    entries: List[dict] = []

    def first_text(node: ET.Element, tags: List[str]) -> Optional[str]:
        for tag in tags:
            direct = node.find(tag)
            if direct is not None and direct.text:
                value = direct.text.strip()
                if value:
                    return value
            nested = node.find(f".//{tag}")
            if nested is not None and nested.text:
                value = nested.text.strip()
                if value:
                    return value
        return None

    def split_multi(value: Optional[str]) -> List[str]:
        if not value:
            return []
        parts = re.split(r"[;,|]", value)
        return [part.strip() for part in parts if part.strip()]

    with zipfile.ZipFile(io.BytesIO(zip_content)) as archive:
        for name in archive.namelist():
            if not name.lower().endswith(".xml"):
                continue
            try:
                payload = archive.read(name)
                root = ET.fromstring(payload)
            except Exception:
                continue

            game_nodes = root.findall(".//Game")
            if root.tag.lower() == "game":
                game_nodes = [root]

            for game_node in game_nodes:
                title = first_text(game_node, ["Title", "Name", "GameTitle"])
                platform = first_text(game_node, ["Platform", "PlatformName", "Console"])
                if not title:
                    continue

                release_date = normalize_release_date(
                    first_text(game_node, ["ReleaseDate", "ReleaseDateUtc", "ReleaseDateUTC", "Release", "Year"])
                )
                year_released = parse_optional_int(first_text(game_node, ["ReleaseYear", "Year"]))
                if year_released is None and release_date:
                    year_released = parse_optional_int(release_date[:4])

                entries.append(
                    {
                        "title": title,
                        "platform": platform,
                        "release_date": release_date,
                        "year_released": year_released,
                        "rating": first_text(game_node, ["ESRB", "Rating"]),
                        "players": first_text(game_node, ["MaxPlayers", "Players"]),
                        "cooperative": first_text(game_node, ["Cooperative", "Co-op", "CoOp"]),
                        "publishers": split_multi(first_text(game_node, ["Publishers", "Publisher"])),
                        "gameGenres": split_multi(first_text(game_node, ["Genres", "Genre"])),
                        "notes": first_text(game_node, ["Overview", "Description", "Summary"]),
                        "coverImage": None,
                        "spineImage": None,
                        "discImage": None,
                        "metadata_source": "launchbox-metadata-zip",
                    }
                )

    return entries


def refresh_launchbox_metadata_cache(force_refresh: bool = False) -> None:
    global _launchbox_metadata_cache
    global _launchbox_metadata_last_refresh_at
    global _launchbox_metadata_source_url
    global _launchbox_metadata_last_error

    now = time.monotonic()
    if not force_refresh and (now - _launchbox_metadata_last_refresh_at) < LAUNCHBOX_METADATA_REFRESH_SECONDS:
        return

    _launchbox_metadata_last_refresh_at = now
    _launchbox_metadata_last_error = None
    _launchbox_metadata_source_url = None

    try:
        zip_content, source_url = try_download_launchbox_metadata_zip()
        if not zip_content:
            _launchbox_metadata_last_error = "metadata zip not discoverable"
            return
        parsed_entries = parse_launchbox_metadata_zip_entries(zip_content)
        if not parsed_entries:
            _launchbox_metadata_last_error = "metadata zip parsed but no game entries found"
            return
        _launchbox_metadata_cache = parsed_entries
        _launchbox_metadata_source_url = source_url
    except Exception as exc:
        _launchbox_metadata_last_error = str(exc)


def find_launchbox_metadata_match(title: str, platform: str) -> Optional[dict]:
    refresh_launchbox_metadata_cache()
    if not _launchbox_metadata_cache:
        return None

    target_title = normalize_launchbox_key(title)
    target_title_loose = normalize_title_for_match(title)
    target_tokens = set(title_tokens(title))
    target_platform = normalize_launchbox_key(platform)

    best_entry = None
    best_score = -1

    for entry in _launchbox_metadata_cache:
        candidate_title = str(entry.get("title") or "")
        candidate_platform = str(entry.get("platform") or "")
        candidate_title_key = normalize_launchbox_key(candidate_title)
        candidate_title_loose = normalize_title_for_match(candidate_title)
        candidate_tokens = set(title_tokens(candidate_title))
        candidate_platform_key = normalize_launchbox_key(candidate_platform)

        score = 0
        if candidate_title_key and candidate_title_key == target_title:
            score += 140
        elif candidate_title_key and target_title and (target_title in candidate_title_key or candidate_title_key in target_title):
            score += 90

        if target_tokens and candidate_tokens:
            overlap = len(target_tokens.intersection(candidate_tokens))
            union = len(target_tokens.union(candidate_tokens))
            if union:
                score += int((overlap / union) * 80)

        if target_title_loose and candidate_title_loose:
            similarity = SequenceMatcher(None, target_title_loose, candidate_title_loose).ratio()
            score += int(similarity * 50)

        if target_platform and candidate_platform_key and (target_platform in candidate_platform_key or candidate_platform_key in target_platform):
            score += 35

        if score > best_score:
            best_score = score
            best_entry = entry

    if not best_entry or best_score < 70:
        return None
    return dict(best_entry)


def libretro_repo_candidates(platform: str) -> List[str]:
    normalized = normalize_title_for_match(platform)
    if normalized in LIBRETRO_PLATFORM_REPO_ALIASES:
        return LIBRETRO_PLATFORM_REPO_ALIASES[normalized]
    for key, repos in LIBRETRO_PLATFORM_REPO_ALIASES.items():
        if key in normalized or normalized in key:
            return repos
    return []


def libretro_title_candidates(title: str) -> List[str]:
    base = (title or "").strip()
    if not base:
        return []

    candidates = [
        base,
        re.sub(r"\s+", " ", base),
        base.replace(":", " -"),
        re.sub(r"\s*\([^)]*\)", "", base).strip(),
        re.sub(r"\s*\[[^\]]*\]", "", base).strip(),
    ]

    deduped: List[str] = []
    for candidate in candidates:
        c = candidate.strip()
        if c and c not in deduped:
            deduped.append(c)
    return deduped


def response_to_data_uri(response: requests.Response) -> Optional[str]:
    if not response.ok:
        return None
    content_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[0].strip() or "image/jpeg"
    if not content_type.startswith("image/"):
        return None
    encoded = base64.b64encode(response.content).decode("utf-8")
    return f"data:{content_type};base64,{encoded}"


def fetch_libretro_cover_image(title: str, platform: str) -> Optional[str]:
    if not ENABLE_LIBRETRO_BOXART:
        return None

    repos = libretro_repo_candidates(platform)
    if not repos:
        return None

    for repo in repos:
        repo_path = quote(repo, safe="")
        for candidate_title in libretro_title_candidates(title):
            encoded_title = quote(candidate_title, safe="")
            for ext in ["png", "jpg", "jpeg"]:
                image_url = (
                    f"https://raw.githubusercontent.com/libretro-thumbnails/{repo_path}/master/"
                    f"Named_Boxarts/{encoded_title}.{ext}"
                )
                try:
                    response = requests.get(image_url, timeout=15, headers=DEFAULT_HTTP_HEADERS)
                except requests.RequestException:
                    continue
                image_data_uri = response_to_data_uri(response)
                if image_data_uri:
                    return image_data_uri
    return None


def fetch_igdb_cover_options(title: str, platform: str, limit: int = 8) -> List[str]:
    if not ENABLE_IGDB_FALLBACK:
        return []

    platform_ids = igdb_platform_ids_for(platform)
    where_clause = "where version_parent = null"
    if platform_ids:
        where_clause += f" & platforms = ({','.join(str(platform_id) for platform_id in platform_ids)})"
    sanitized_title = title.replace("\\", " ").replace('"', "")
    query = (
        "fields name,platforms.name,cover.url; "
        f"search \"{sanitized_title}\"; "
        f"{where_clause}; limit 15;"
    )

    try:
        candidates = igdb_post("games", query)
    except Exception:
        return []

    if not candidates:
        return []

    ranked = sorted(
        candidates,
        key=lambda entry: score_igdb_candidate(
            str(entry.get("name") or ""),
            title,
            ", ".join(str(platform_entry.get("name") or "") for platform_entry in (entry.get("platforms") or []) if isinstance(platform_entry, dict)),
            platform,
        ),
        reverse=True,
    )

    options: List[str] = []
    for candidate in ranked[:10]:
        cover = candidate.get("cover")
        if not isinstance(cover, dict):
            continue
        cover_url = igdb_cover_url(str(cover.get("url") or ""))
        image_data = safe_fetch_image_data_uri(cover_url)
        if image_data and image_data not in options:
            options.append(image_data)
            if len(options) >= limit:
                break
    return options


def resolve_cover_image_with_priority(title: str, platform: str, launchbox_cover_image: Optional[str]) -> Tuple[Optional[str], str]:
    if launchbox_cover_image:
        return launchbox_cover_image, "launchbox"

    igdb_cover_options = fetch_igdb_cover_options(title, platform, limit=1)
    if igdb_cover_options:
        return igdb_cover_options[0], "igdb"

    libretro_cover = fetch_libretro_cover_image(title, platform)
    if libretro_cover:
        return libretro_cover, "libretro"

    return None, "none"


def fetch_igdb_game_data(title: str, platform: str) -> Optional[dict]:
    if not ENABLE_IGDB_FALLBACK:
        return None

    platform_ids = igdb_platform_ids_for(platform)
    where_clause = "where version_parent = null"
    if platform_ids:
        where_clause += f" & platforms = ({','.join(str(platform_id) for platform_id in platform_ids)})"
    sanitized_title = title.replace("\\", " ").replace('"', "")
    query = (
        "fields name,summary,first_release_date,genres.name,involved_companies.publisher,involved_companies.company.name,"
        "cover.url,age_ratings.category,age_ratings.rating,multiplayer_modes.onlinemax,multiplayer_modes.offlinemax,multiplayer_modes.campaigncoop,multiplayer_modes.onlinecoop,multiplayer_modes.offlinecoop,platforms.name; "
        f"search \"{sanitized_title}\"; "
        f"{where_clause}; limit 12;"
    )

    try:
        results = igdb_post("games", query)
    except Exception:
        return None

    if not results:
        return None

    ranked = sorted(
        results,
        key=lambda entry: score_igdb_candidate(
            str(entry.get("name") or ""),
            title,
            ", ".join(str(platform_entry.get("name") or "") for platform_entry in (entry.get("platforms") or []) if isinstance(platform_entry, dict)),
            platform,
        ),
        reverse=True,
    )
    best = ranked[0]

    best_score = score_igdb_candidate(
        str(best.get("name") or ""),
        title,
        ", ".join(str(platform_entry.get("name") or "") for platform_entry in (best.get("platforms") or []) if isinstance(platform_entry, dict)),
        platform,
    )
    if best_score < 70:
        return None

    release_date = None
    year_released = None
    first_release_date = best.get("first_release_date")
    if isinstance(first_release_date, (int, float)):
        try:
            release_ts = int(first_release_date)
            release_struct = time.gmtime(release_ts)
            release_date = time.strftime("%Y-%m-%d", release_struct)
            year_released = release_struct.tm_year
        except Exception:
            release_date = None
            year_released = None

    publishers: List[str] = []
    involved_companies = best.get("involved_companies") or []
    if isinstance(involved_companies, list):
        for entry in involved_companies:
            if not isinstance(entry, dict):
                continue
            company = entry.get("company")
            if not isinstance(company, dict):
                continue
            company_name = str(company.get("name") or "").strip()
            if not company_name:
                continue
            if entry.get("publisher"):
                publishers.append(company_name)
        if not publishers:
            for entry in involved_companies:
                if not isinstance(entry, dict):
                    continue
                company = entry.get("company")
                if not isinstance(company, dict):
                    continue
                company_name = str(company.get("name") or "").strip()
                if company_name and company_name not in publishers:
                    publishers.append(company_name)

    game_genres = [
        str(genre_entry.get("name") or "").strip()
        for genre_entry in (best.get("genres") or [])
        if isinstance(genre_entry, dict) and str(genre_entry.get("name") or "").strip()
    ]

    players = None
    cooperative = None
    multiplayer_modes = best.get("multiplayer_modes") or []
    if isinstance(multiplayer_modes, list):
        max_players = 0
        has_coop = False
        for mode_entry in multiplayer_modes:
            if not isinstance(mode_entry, dict):
                continue
            for key in ["onlinemax", "offlinemax"]:
                candidate_players = mode_entry.get(key)
                if isinstance(candidate_players, int):
                    max_players = max(max_players, candidate_players)
            if bool(mode_entry.get("campaigncoop")) or bool(mode_entry.get("onlinecoop")) or bool(mode_entry.get("offlinecoop")):
                has_coop = True
        if max_players > 0:
            players = max_players
        cooperative = "Yes" if has_coop else "No"

    cover_url = None
    cover_entry = best.get("cover")
    if isinstance(cover_entry, dict):
        cover_url = igdb_cover_url(str(cover_entry.get("url") or ""))

    cover_image = safe_fetch_image_data_uri(cover_url)

    return {
        "title": str(best.get("name") or title),
        "platform": platform,
        "release_date": release_date,
        "year_released": year_released,
        "rating": map_igdb_esrb_rating(best.get("age_ratings") or []),
        "players": players,
        "cooperative": cooperative,
        "publishers": publishers,
        "gameGenres": game_genres,
        "notes": str(best.get("summary") or "").strip() or None,
        "coverImage": cover_image,
        "spineImage": None,
        "discImage": None,
        "data_source": "igdb",
        "is_partial_fallback": True,
        "completeness": {
            "metadata": True,
            "cover": bool(cover_image),
            "disc": False,
            "spine": False,
            "cart": False,
        },
    }


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
    price_data_json: Optional[str] = None
    price_last_fetched_at: Optional[str] = None


class WishlistPriceFetchRequest(SQLModel):
    title: str
    category: str
    platform: Optional[str] = None
    artist: Optional[str] = None


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
    launchbox_url: Optional[str] = None


class LaunchboxGameArtOptionsRequest(SQLModel):
    title: str
    platform: str
    art_type: str


class DeezerMusicDataRequest(SQLModel):
    title: str
    artist: str


class DiscogsMusicArtOptionsRequest(SQLModel):
    title: str
    artist: str


class FetchToolItemRequest(SQLModel):
    mode: str = "all"  # art | details | all
    force: bool = False


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


def ensure_price_columns() -> None:
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(mediaitem)")).fetchall()
        column_names = {column[1] for column in columns}
        if "price_data_json" not in column_names:
            connection.execute(text("ALTER TABLE mediaitem ADD COLUMN price_data_json VARCHAR"))
        if "price_last_fetched_at" not in column_names:
            connection.execute(text("ALTER TABLE mediaitem ADD COLUMN price_last_fetched_at VARCHAR"))


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


def launchbox_detail_payload(title: str, platform: str, launchbox_url: Optional[str] = None) -> dict:
    if launchbox_url:
        return fetch_launchbox_game_data_from_url(launchbox_url, platform, title)

    errors: List[str] = []

    try:
        return fetch_launchbox_game_data(title, platform)
    except Exception as exc:
        errors.append(str(exc))

    metadata_match = find_launchbox_metadata_match(title, platform)
    if metadata_match:
        metadata_match["title"] = metadata_match.get("title") or title
        metadata_match["platform"] = metadata_match.get("platform") or platform
        metadata_match["coverImage"] = None
        metadata_match["spineImage"] = None
        metadata_match["discImage"] = None
        metadata_match["metadata_source"] = metadata_match.get("metadata_source") or "launchbox-metadata-zip"
        return metadata_match

    if errors:
        raise HTTPException(status_code=502, detail=f"LaunchBox detail lookup failed: {errors[-1]}")
    raise HTTPException(status_code=502, detail="LaunchBox detail lookup failed.")


def apply_cover_priority(title: str, platform: str, payload: dict) -> dict:
    launchbox_cover = payload.get("coverImage")
    selected_cover, selected_source = resolve_cover_image_with_priority(title, platform, launchbox_cover)
    payload["coverImage"] = selected_cover
    payload["cover_source"] = selected_source
    return payload


def fill_missing_primary_art(payload: dict) -> dict:
    # Disc/cart and spine artwork should only be set from explicit matches.
    # Do not infer them from cover art.
    return payload


def launchbox_completeness_from_payload(payload: dict, platform: str) -> dict:
    is_cartridge_platform = is_cartridge_platform_name(platform)
    has_disc = bool(payload.get("discImage"))
    has_cart = has_disc if is_cartridge_platform else False
    return {
        "metadata": True,
        "cover": bool(payload.get("coverImage")),
        "disc": has_disc,
        "spine": bool(payload.get("spineImage")),
        "cart": has_cart,
    }


def launchbox_unavailable_resources(completeness: Optional[dict], platform: str) -> List[str]:
    if not isinstance(completeness, dict):
        return []

    missing: List[str] = []
    if not bool(completeness.get("cover")):
        missing.append("cover")

    is_cartridge_platform = is_cartridge_platform_name(platform)
    if is_cartridge_platform:
        if not (bool(completeness.get("cart")) or bool(completeness.get("disc"))):
            missing.append("cart")
    elif not bool(completeness.get("disc")):
        missing.append("disc")

    if not bool(completeness.get("spine")):
        missing.append("spine")
    return missing


def launchbox_unavailable_status_message(resources: List[str], platform: str) -> str:
    if not resources:
        return ""
    labels: List[str] = []
    for resource in resources:
        if resource == "cover":
            labels.append("Box Art")
        elif resource == "disc":
            labels.append("Disc Art")
        elif resource == "cart":
            labels.append("Cart Art")
        elif resource == "spine":
            labels.append("Spine Art")

    if not labels:
        return ""
    return (
        "LaunchBox did not have "
        + ", ".join(labels)
        + f" for {platform}. Any missing fields were left unchanged."
    )


def fetch_game_data_with_fallback(title: str, platform: str) -> dict:
    try:
        payload = launchbox_detail_payload(title, platform)
        lb_completeness = launchbox_completeness_from_payload(payload, platform)
        payload["launchbox_completeness"] = lb_completeness
        payload = apply_cover_priority(title, platform, payload)
        payload = fill_missing_primary_art(payload)
        payload["data_source"] = "launchbox"
        payload["is_partial_fallback"] = False
        payload["completeness"] = {
            "metadata": True,
            "cover": bool(payload.get("coverImage")),
            "disc": bool(payload.get("discImage")),
            "spine": bool(payload.get("spineImage")),
            "cart": False,
        }
        unavailable_resources = launchbox_unavailable_resources(lb_completeness, platform)
        payload["launchbox_unavailable_resources"] = unavailable_resources
        payload["launchbox_status"] = launchbox_unavailable_status_message(unavailable_resources, platform)
        return payload
    except Exception as exc:
        igdb_payload = fetch_igdb_game_data(title, platform)
        if igdb_payload:
            igdb_payload = apply_cover_priority(title, platform, igdb_payload)
            igdb_payload = fill_missing_primary_art(igdb_payload)
            igdb_payload["launchbox_completeness"] = {
                "metadata": False,
                "cover": False,
                "disc": False,
                "spine": False,
                "cart": False,
            }
            igdb_payload["launchbox_unavailable_resources"] = []
            igdb_payload["launchbox_status"] = ""
            return igdb_payload

        if ENABLE_KEYLESS_METADATA_FALLBACK:
            try:
                metadata_payload = fetch_wikidata_game_data(title, platform)
                if metadata_payload:
                    metadata_payload = apply_cover_priority(title, platform, metadata_payload)
                    metadata_payload = fill_missing_primary_art(metadata_payload)
                    metadata_payload["launchbox_completeness"] = {
                        "metadata": False,
                        "cover": False,
                        "disc": False,
                        "spine": False,
                        "cart": False,
                    }
                    metadata_payload["launchbox_unavailable_resources"] = []
                    metadata_payload["launchbox_status"] = ""
                    return metadata_payload
            except Exception:
                pass

        raise HTTPException(
            status_code=502,
            detail=(
                "Could not fetch game data. LaunchBox is unavailable and no approved "
                "fallback source (IGDB/Wikidata) returned a match."
            ),
        ) from exc


def fetch_game_art_options_with_fallback(title: str, platform: str, art_type: str) -> dict:
    if art_type not in {"cover", "disc", "spine", "cart"}:
        raise HTTPException(status_code=400, detail="Invalid art_type. Use cover, disc, spine, or cart.")

    def append_unique(target: List[str], entries: List[str]) -> int:
        added = 0
        for entry in entries:
            if isinstance(entry, str) and entry and entry not in target:
                target.append(entry)
                added += 1
        return added

    options: List[str] = []
    source_counts: Dict[str, int] = {}
    status_notes: List[str] = []

    try:
        launchbox_payload = fetch_launchbox_game_art_options(title, platform, art_type)
        launchbox_list = launchbox_payload.get("options", []) if isinstance(launchbox_payload, dict) else []
        source_counts["launchbox"] = append_unique(options, launchbox_list)
    except Exception:
        source_counts["launchbox"] = 0
        status_notes.append(f"LaunchBox has no {art_type} art for this match.")

    if art_type == "cover":
        source_counts["igdb"] = append_unique(options, fetch_igdb_cover_options(title, platform, limit=8))

        libretro_cover = fetch_libretro_cover_image(title, platform)
        source_counts["libretro"] = append_unique(options, [libretro_cover] if libretro_cover else [])

    if ENABLE_MOBYGAMES_SCRAPE_FALLBACK:
        try:
            moby_payload = fetch_mobygames_game_art_options(title, platform, art_type)
            moby_list = moby_payload.get("options", []) if isinstance(moby_payload, dict) else []
            source_counts["mobygames"] = append_unique(options, moby_list)
        except Exception:
            source_counts["mobygames"] = 0
    else:
        source_counts["mobygames"] = 0

    if not options:
        status_notes.append("No approved fallback source returned images for this category.")

    is_cartridge_platform = is_cartridge_platform_name(platform)
    if art_type == "cover":
        art_label = "Box Art"
    elif art_type == "spine":
        art_label = "Spine Art"
    elif art_type == "cart" or (art_type == "disc" and is_cartridge_platform):
        art_label = "Cart Art"
    else:
        art_label = "Disc Art"

    status_message = ""
    if status_notes:
        status_message = f"{art_label} status: " + " ".join(status_notes)

    return {
        "title": title,
        "platform": platform,
        "artType": art_type,
        "options": options,
        "data_source": "launchbox-with-fallbacks",
        "source_breakdown": source_counts,
        "status_message": status_message,
    }


def apply_fetched_game_data_to_item(item: MediaItem, fetched: dict) -> None:
    source = (fetched.get("data_source") or "").lower()
    is_launchbox_source = source == "launchbox"

    item.cover_image = fetched.get("coverImage") or item.cover_image
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


def is_blank_text(value: Optional[str]) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def set_optional_text(current_value: Optional[str], incoming_value: Optional[str], force: bool) -> Tuple[Optional[str], bool]:
    if not isinstance(incoming_value, str) or not incoming_value.strip():
        return current_value, False
    if force or is_blank_text(current_value):
        next_value = incoming_value.strip()
        return next_value, next_value != (current_value or "").strip()
    return current_value, False


def set_optional_int(current_value: Optional[int], incoming_value: Optional[int], force: bool) -> Tuple[Optional[int], bool]:
    if incoming_value is None:
        return current_value, False
    if force or current_value is None:
        return incoming_value, incoming_value != current_value
    return current_value, False


def process_fetch_tool_game_item(item: MediaItem, mode: str, force: bool) -> dict:
    if item.category != "Games":
        raise HTTPException(status_code=400, detail="Item is not a game")
    if not item.platform:
        raise HTTPException(status_code=400, detail="Game item must have a platform")

    fetched = fetch_game_data_with_fallback(item.title, item.platform)
    changed = False

    if mode in {"art", "all"}:
        for field_name, payload_key in (("cover_image", "coverImage"), ("disc_image", "discImage"), ("spine_image", "spineImage")):
            incoming = fetched.get(payload_key)
            if isinstance(incoming, str) and incoming.strip() and (force or is_blank_text(getattr(item, field_name))):
                if getattr(item, field_name) != incoming:
                    setattr(item, field_name, incoming)
                    changed = True

    if mode in {"details", "all"}:
        publishers = [entry.strip() for entry in fetched.get("publishers", []) if isinstance(entry, str) and entry.strip()]
        game_genres = [entry.strip() for entry in fetched.get("gameGenres", []) if isinstance(entry, str) and entry.strip()]

        item.notes, did_change = set_optional_text(item.notes, fetched.get("notes"), force)
        changed = changed or did_change

        item.publisher, did_change = set_optional_text(item.publisher, ", ".join(publishers) if publishers else None, force)
        changed = changed or did_change

        if game_genres:
            next_genres = ", ".join(game_genres)
            if force or is_blank_text(item.genres):
                if item.genres != next_genres:
                    item.genres = next_genres
                    changed = True
            if force or is_blank_text(item.genre):
                if item.genre != game_genres[0]:
                    item.genre = game_genres[0]
                    changed = True

        incoming_release_date = normalize_release_date(fetched.get("release_date"))
        item.release_date, did_change = set_optional_text(item.release_date, incoming_release_date, force)
        changed = changed or did_change

        incoming_year = parse_optional_int(fetched.get("year_released"))
        item.year_released, did_change = set_optional_int(item.year_released, incoming_year, force)
        changed = changed or did_change

        incoming_rating = normalize_esrb_rating(fetched.get("rating"))
        item.rating, did_change = set_optional_text(item.rating, incoming_rating, force)
        changed = changed or did_change

        item.cooperative, did_change = set_optional_text(item.cooperative, fetched.get("cooperative"), force)
        changed = changed or did_change

        incoming_players = parse_optional_int(fetched.get("players"))
        item.players, did_change = set_optional_int(item.players, incoming_players, force)
        changed = changed or did_change

    return {
        "id": item.id,
        "title": item.title,
        "category": item.category,
        "mode": mode,
        "changed": changed,
        "data_source": fetched.get("data_source", "launchbox"),
        "status_note": fetched.get("launchbox_status", ""),
    }


def process_fetch_tool_music_item(item: MediaItem, mode: str, force: bool) -> dict:
    if item.category != "Music":
        raise HTTPException(status_code=400, detail="Item is not music")
    if not item.artist or not item.artist.strip():
        raise HTTPException(status_code=400, detail="Music item must have an artist")

    fetched = fetch_music_album_data(item.title, item.artist)
    changed = False

    if mode in {"art", "all"}:
        incoming_cover = fetched.get("coverImage")
        if isinstance(incoming_cover, str) and incoming_cover.strip() and (force or is_blank_text(item.cover_image)):
            if item.cover_image != incoming_cover:
                item.cover_image = incoming_cover
                changed = True

    if mode in {"details", "all"}:
        item.genre, did_change = set_optional_text(item.genre, fetched.get("genre"), force)
        changed = changed or did_change

        incoming_release_date = normalize_release_date(fetched.get("release_date"))
        item.release_date, did_change = set_optional_text(item.release_date, incoming_release_date, force)
        changed = changed or did_change

        incoming_year = parse_optional_int(fetched.get("year_released"))
        item.year_released, did_change = set_optional_int(item.year_released, incoming_year, force)
        changed = changed or did_change

    return {
        "id": item.id,
        "title": item.title,
        "category": item.category,
        "mode": mode,
        "changed": changed,
        "data_source": "deezer",
        "status_note": "",
    }


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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def is_price_refresh_due(last_fetched_at: Optional[str]) -> bool:
    last_fetch = parse_iso_datetime(last_fetched_at)
    if not last_fetch:
        return True
    return (utc_now() - last_fetch) >= timedelta(days=PRICE_REFRESH_DUE_DAYS)


def pricing_throttle() -> None:
    global _pricing_last_request_at
    with _pricing_request_lock:
        elapsed = time.monotonic() - _pricing_last_request_at
        if elapsed < PRICE_MIN_REQUEST_INTERVAL:
            time.sleep(PRICE_MIN_REQUEST_INTERVAL - elapsed)
        _pricing_last_request_at = time.monotonic()


def pricing_headers(extra: Optional[dict] = None) -> dict:
    headers = {
        "User-Agent": PRICE_USER_AGENT,
        "Accept": "text/html,application/json,*/*",
    }
    if DISCOGS_USER_TOKEN:
        headers["Authorization"] = f"Discogs token={DISCOGS_USER_TOKEN}"
    if extra:
        headers.update(extra)
    return headers


def pricing_get(url: str, params: Optional[dict] = None, timeout: int = 25) -> requests.Response:
    pricing_throttle()
    response = requests.get(url, params=params, headers=pricing_headers(), timeout=timeout)
    response.raise_for_status()
    return response


def parse_money(value: str) -> Optional[float]:
    if not value:
        return None
    match = re.search(r"\$\s*([0-9]+(?:\.[0-9]+)?)", value)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def parse_first_money_after_label(text: str, label: str) -> Optional[float]:
    pattern = rf"{re.escape(label)}\s*\$\s*([0-9]+(?:\.[0-9]+)?)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def average(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def compute_sales_window_metrics(sales_rows: List[Tuple[datetime, float]]) -> dict:
    today = utc_now()
    last_window_start = today - timedelta(days=365)
    prev_window_start = today - timedelta(days=730)

    last_values = [price for sold_at, price in sales_rows if last_window_start <= sold_at <= today]
    prev_values = [price for sold_at, price in sales_rows if prev_window_start <= sold_at < last_window_start]

    avg_last = average(last_values)
    avg_prev = average(prev_values)

    change_percent = None
    if avg_last is not None and avg_prev and avg_prev > 0:
        change_percent = ((avg_last - avg_prev) / avg_prev) * 100.0

    sold_range = None
    if last_values:
        sold_range = {"min": min(last_values), "max": max(last_values)}

    return {
        "avg_last": avg_last,
        "avg_prev": avg_prev,
        "change_percent": change_percent,
        "sold_range": sold_range,
    }


def score_pricecharting_candidate(candidate_title: str, candidate_platform: str, title: str, platform: str) -> int:
    score = 0
    score += score_mobygames_candidate(candidate_title, candidate_platform, title, platform)
    if "pal" in normalize_title_for_match(candidate_platform):
        score -= 18
    if "jp" in normalize_title_for_match(candidate_platform):
        score -= 12
    return score


def pricecharting_slugify(value: str) -> str:
    normalized = normalize_title_for_match(value)
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return re.sub(r"-{2,}", "-", normalized)


def find_pricecharting_product_match(title: str, platform: str) -> Optional[dict]:
    search_url = "https://www.pricecharting.com/search-products"
    try:
        response = pricing_get(search_url, params={"type": "prices", "q": f"{title} {platform}"})
    except Exception:
        return None

    candidates: List[Tuple[int, dict]] = []

    try:
        payload = response.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        products = payload.get("products")
        if isinstance(products, list):
            for product in products:
                if not isinstance(product, dict):
                    continue
                product_name = product.get("productName")
                console_name = product.get("consoleName")
                if not isinstance(product_name, str) or not isinstance(console_name, str):
                    continue

                score = score_pricecharting_candidate(product_name, console_name, title, platform)
                if score < 50:
                    continue

                console_slug = pricecharting_slugify(console_name)
                product_slug = pricecharting_slugify(product_name)
                if not console_slug or not product_slug:
                    continue

                candidates.append((score, {
                    "url": f"https://www.pricecharting.com/game/{console_slug}/{product_slug}",
                    "loose": parse_money(product.get("price1") or ""),
                    "complete": parse_money(product.get("price3") or ""),
                    "new": parse_money(product.get("price2") or ""),
                }))

    if not candidates:
        return None

    if not candidates:
        return None

    candidates.sort(key=lambda entry: entry[0], reverse=True)
    return candidates[0][1]


def find_pricecharting_product_url(title: str, platform: str) -> Optional[str]:
    match = find_pricecharting_product_match(title, platform)
    return match.get("url") if match else None


def fetch_pricecharting_price_data(title: str, platform: str) -> Optional[dict]:
    match = find_pricecharting_product_match(title, platform)
    if not match:
        return None

    loose_price = match.get("loose") if isinstance(match.get("loose"), (float, int)) else None
    cib_price = match.get("complete") if isinstance(match.get("complete"), (float, int)) else None
    new_price = match.get("new") if isinstance(match.get("new"), (float, int)) else None

    sold_prices = [price for price in [loose_price, cib_price, new_price] if isinstance(price, (float, int))]
    sold_range = None
    if sold_prices:
        sold_range = {"min": min(float(price) for price in sold_prices), "max": max(float(price) for price in sold_prices)}

    average_change_percent = None
    if len(sold_prices) >= 2:
        lowest_price = min(float(price) for price in sold_prices)
        highest_price = max(float(price) for price in sold_prices)
        if lowest_price > 0:
            average_change_percent = ((highest_price - lowest_price) / lowest_price) * 100.0

    # Per-condition sold ranges
    sold_range_by_condition = {}
    if loose_price is not None:
        sold_range_by_condition["loose"] = {"min": loose_price, "max": loose_price}
    if cib_price is not None:
        sold_range_by_condition["cib"] = {"min": cib_price, "max": cib_price}
    if new_price is not None:
        sold_range_by_condition["new"] = {"min": new_price, "max": new_price}

    return {
        "kind": "game",
        "source": "pricecharting",
        "source_url": match.get("url"),
        "average": {
            "loose": {"value": loose_price, "url": f"{match.get('url')}?condition=Loose" if match.get("url") else None},
            "cib": {"value": cib_price, "url": f"{match.get('url')}?condition=Complete" if match.get("url") else None},
            "new": {"value": new_price, "url": f"{match.get('url')}?condition=New" if match.get("url") else None},
        },
        "average_change_percent": average_change_percent,
        "sold_range": sold_range,
        "sold_range_by_condition": sold_range_by_condition,
    }


def score_discogs_release(result: dict, artist: str, album: str) -> int:
    score = score_music_match(result, artist, album)
    community = result.get("community") if isinstance(result, dict) else {}
    if isinstance(community, dict):
        score += int(min(40, (community.get("have") or 0) / 800))
    year = parse_optional_int(result.get("year"))
    if year:
        score += 4
    return score


def discogs_release_is_limited(result: dict) -> bool:
    formats = result.get("formats") if isinstance(result, dict) else None
    haystack_parts: List[str] = []

    if isinstance(formats, list):
        for fmt in formats:
            if not isinstance(fmt, dict):
                continue
            name = fmt.get("name")
            text = fmt.get("text")
            descriptions = fmt.get("descriptions") if isinstance(fmt.get("descriptions"), list) else []
            if isinstance(name, str):
                haystack_parts.append(name)
            if isinstance(text, str):
                haystack_parts.append(text)
            for desc in descriptions:
                if isinstance(desc, str):
                    haystack_parts.append(desc)

    for candidate in result.get("format", []) if isinstance(result.get("format"), list) else []:
        if isinstance(candidate, str):
            haystack_parts.append(candidate)

    haystack = normalize_title_for_match(" ".join(haystack_parts))
    limited_terms = [
        "limited edition",
        "numbered",
        "record store day",
        "color",
        "coloured",
        "splatter",
        "picture disc",
        "box set",
    ]
    return any(term in haystack for term in limited_terms)


def discogs_release_url(result: dict) -> Optional[str]:
    uri = result.get("uri") if isinstance(result, dict) else None
    if isinstance(uri, str) and uri.strip():
        if uri.startswith("http"):
            return uri
        return urljoin("https://www.discogs.com", uri)

    release_id = result.get("id") if isinstance(result, dict) else None
    if isinstance(release_id, int):
        return f"https://www.discogs.com/release/{release_id}"
    return None


def fetch_discogs_price_data(album: str, artist: str) -> Optional[dict]:
    search_url = "https://api.discogs.com/database/search"
    try:
        response = pricing_get(
            search_url,
            params={
                "q": f"{album} {artist}",
                "type": "release",
                "format": "Vinyl",
                "per_page": 25,
                "page": 1,
            },
        )
        payload = response.json() if response.content else {}
    except Exception:
        return None

    results = payload.get("results") if isinstance(payload, dict) else []
    if not isinstance(results, list) or not results:
        return None

    ranked = sorted(
        [entry for entry in results if isinstance(entry, dict)],
        key=lambda entry: score_discogs_release(entry, artist, album),
        reverse=True,
    )

    standard_prices: List[float] = []
    limited_prices: List[float] = []
    all_prices: List[float] = []
    standard_url = None
    limited_url = None

    for release in ranked[:12]:
        release_id = release.get("id")
        if not isinstance(release_id, int):
            continue
        try:
            stats_response = pricing_get(f"https://api.discogs.com/marketplace/stats/{release_id}")
            stats_payload = stats_response.json() if stats_response.content else {}
        except Exception:
            continue

        lowest_price = ((stats_payload or {}).get("lowest_price") or {}).get("value")
        if not isinstance(lowest_price, (float, int)):
            continue

        price_value = float(lowest_price)
        if price_value <= 0:
            continue

        is_limited = discogs_release_is_limited(release)
        link = discogs_release_url(release)

        if is_limited:
            limited_prices.append(price_value)
            if not limited_url and link:
                limited_url = f"{link}#marketplace"
        else:
            standard_prices.append(price_value)
            if not standard_url and link:
                standard_url = f"{link}#marketplace"

        all_prices.append(price_value)

    standard_average = average(standard_prices)
    limited_average = average(limited_prices)

    sold_range = None
    if all_prices:
        sold_range = {"min": min(all_prices), "max": max(all_prices)}

    average_change_percent = None
    if standard_average is not None and limited_average is not None and standard_average > 0:
        average_change_percent = ((limited_average - standard_average) / standard_average) * 100.0

    # Per-edition sold ranges
    sold_range_by_condition = {}
    if standard_prices:
        sold_range_by_condition["standard"] = {"min": min(standard_prices), "max": max(standard_prices)}
    if limited_prices:
        sold_range_by_condition["limited"] = {"min": min(limited_prices), "max": max(limited_prices)}

    return {
        "kind": "music",
        "source": "discogs",
        "source_url": standard_url or limited_url,
        "average": {
            "standard": {"value": standard_average, "url": standard_url},
            "limited": {"value": limited_average, "url": limited_url},
        },
        "average_change_percent": average_change_percent,
        "sold_range": sold_range,
        "sold_range_by_condition": sold_range_by_condition,
    }


def fetch_discogs_music_art_option_urls(album: str, artist: str) -> List[str]:
    search_url = "https://api.discogs.com/database/search"
    results = []
    try:
        response = pricing_get(
            search_url,
            params={
                "release_title": album,
                "artist": artist,
                "q": f"{album} {artist}",
                "type": "release",
                "per_page": 25,
                "page": 1,
            },
        )
        payload = response.json() if response.content else {}
        parsed_results = payload.get("results") if isinstance(payload, dict) else []
        if isinstance(parsed_results, list):
            results = parsed_results
    except Exception:
        # Discogs API can be unavailable/unauthenticated in some environments.
        # Fall through to a web search fallback instead of hard-failing.
        results = []

    options: List[str] = []
    seen_canonical = set()
    for entry in results:
        if not isinstance(entry, dict):
            continue
        for key in ("cover_image", "thumb"):
            image_url = entry.get(key)
            if not isinstance(image_url, str):
                continue
            image_url = image_url.strip()
            if not image_url:
                continue
            parsed = urlparse(image_url)
            canonical = f"{parsed.netloc.lower()}{parsed.path}"
            if canonical in seen_canonical:
                continue
            seen_canonical.add(canonical)
            options.append(image_url)
        if len(options) >= 12:
            break

    if options:
        return options

    # Fallback: scrape Discogs public search results for release thumbnails.
    search_query = f"{artist} {album}".strip()
    search_page_url = f"https://www.discogs.com/search/?type=all&q={quote(search_query)}"
    try:
        if cloudscraper is not None:
            scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
            response = scraper.get(search_page_url, timeout=20, headers=pricing_headers())
        else:
            response = requests.get(search_page_url, timeout=20, headers=pricing_headers())
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not query Discogs art options: {exc}") from exc

    for image in soup.select("img"):
        image_url = (image.get("data-src") or image.get("src") or "").strip()
        if not image_url:
            continue
        if image_url.startswith("//"):
            image_url = f"https:{image_url}"
        if "discogs" not in image_url.lower():
            continue
        parsed = urlparse(image_url)
        canonical = f"{parsed.netloc.lower()}{parsed.path}"
        if not canonical or canonical in seen_canonical:
            continue
        seen_canonical.add(canonical)
        options.append(image_url)
        if len(options) >= 12:
            break

    if not options:
        raise HTTPException(status_code=404, detail=f'Could not find art options for "{album}" by {artist} on Discogs.')

    return options


def fetch_deezer_music_art_option_urls(album: str, artist: str) -> List[str]:
    def deezer_canonical_art_key(image_url: str) -> str:
        parsed = urlparse(image_url)
        host = parsed.netloc.lower()
        path = parsed.path

        # Deezer CDN URLs are often the same cover hash with different size suffixes.
        # Canonicalize to host + cover hash so size variants collapse to one image.
        if host.endswith("dzcdn.net"):
            match = re.search(r"/images/cover/([^/]+)/", path)
            if match:
                return f"{host}/images/cover/{match.group(1).lower()}"

        if host == "api.deezer.com":
            match = re.search(r"/album/(\d+)/image", path)
            if match:
                return f"{host}/album/{match.group(1)}"

        return f"{host}{path}"

    url = f"https://api.deezer.com/search/album?q={quote(artist + ' ' + album)}&limit=40"
    try:
        response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        items = response.json().get("data", [])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not query Deezer art options: {exc}") from exc

    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=404, detail=f'Could not find art options for "{album}" by {artist} on Deezer.')

    ranked = sorted(
        [entry for entry in items if isinstance(entry, dict)],
        key=lambda entry: score_music_match(entry, artist, album),
        reverse=True,
    )

    options: List[str] = []
    seen_album_ids = set()
    seen_canonical = set()
    for entry in ranked[:20]:
        album_id = entry.get("id")
        if album_id is not None:
            album_key = str(album_id)
            if album_key in seen_album_ids:
                continue
            seen_album_ids.add(album_key)

        best_image_url = None
        for key in ("cover_xl", "cover_big", "cover_medium", "cover", "cover_small"):
            image_url = entry.get(key)
            if isinstance(image_url, str) and image_url.strip():
                best_image_url = image_url.strip()
                break

        if best_image_url:
            canonical = deezer_canonical_art_key(best_image_url)
            if canonical and canonical not in seen_canonical:
                seen_canonical.add(canonical)
                options.append(best_image_url)

        if len(options) >= 16:
            break

    if not options:
        raise HTTPException(status_code=404, detail=f'Could not find art options for "{album}" by {artist} on Deezer.')

    return options


def fetch_price_data_for_item(item: MediaItem) -> Optional[dict]:
    if item.category == "Games":
        platform = (item.platform or "").strip()
        if not platform:
            return None
        return fetch_pricecharting_price_data(item.title, platform)
    if item.category == "Music":
        artist = (item.artist or "").strip()
        if not artist:
            return None
        return fetch_discogs_price_data(item.title, artist)
    return None


def apply_price_data_to_item(item: MediaItem, price_data: Optional[dict]) -> None:
    if not price_data:
        return
    item.price_data_json = json.dumps(price_data, separators=(",", ":"))
    item.price_last_fetched_at = utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_and_store_price_data_for_item(item: MediaItem, force: bool = False) -> bool:
    if item.category not in {"Games", "Music"}:
        return False
    if not force and not is_price_refresh_due(item.price_last_fetched_at):
        return False

    fetched = fetch_price_data_for_item(item)
    if not fetched:
        return False

    apply_price_data_to_item(item, fetched)
    return True


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


def choose_launchbox_candidate(candidates: list, title: str, platform: str) -> dict:
    """Select the best matching candidate from LaunchBox search results.

    Raises HTTPException 404 if no candidate meets the confidence threshold.
    Raises HTTPException 409 if multiple candidates are too close to disambiguate.
    Returns the best matching candidate dict.
    """
    target_title = normalize_launchbox_key(title)
    target_title_loose = normalize_title_for_match(title)
    target_tokens = set(title_tokens(title))
    target_platform = normalize_launchbox_key(platform)

    def score(candidate: dict) -> int:
        candidate_title = normalize_launchbox_key(candidate["title"])
        candidate_title_loose = normalize_title_for_match(candidate["title"])
        candidate_tokens = set(title_tokens(candidate["title"]))
        candidate_platform = normalize_launchbox_key(candidate["platform"])
        candidate_score = 0

        if candidate_title and candidate_title == target_title:
            candidate_score += 140
        elif candidate_title and target_title and (target_title in candidate_title or candidate_title in target_title):
            candidate_score += 90

        if target_tokens and candidate_tokens:
            overlap = len(target_tokens.intersection(candidate_tokens))
            union = len(target_tokens.union(candidate_tokens))
            if union:
                candidate_score += int((overlap / union) * 80)

        if target_title_loose and candidate_title_loose:
            similarity = SequenceMatcher(None, target_title_loose, candidate_title_loose).ratio()
            candidate_score += int(similarity * 50)

        if target_platform and candidate_platform and (target_platform in candidate_platform or candidate_platform in target_platform):
            candidate_score += 35
        if candidate["title"].strip().lower() == title.strip().lower():
            candidate_score += 10
        return candidate_score

    def is_exact_title_and_platform(candidate: dict) -> bool:
        candidate_title_loose = normalize_title_for_match(candidate.get("title", ""))
        candidate_platform_key = normalize_launchbox_key(candidate.get("platform", ""))
        return (
            bool(candidate_title_loose)
            and candidate_title_loose == target_title_loose
            and bool(candidate_platform_key)
            and (candidate_platform_key in target_platform or target_platform in candidate_platform_key)
        )

    sorted_candidates = sorted(candidates, key=score, reverse=True)
    best_match = sorted_candidates[0]
    best_score = score(best_match)

    # 55 is the minimum meaningful score: a platform-only match tops out at ~45,
    # so a score ≥ 55 requires at least some title relevance.
    if best_score < 55:
        raise HTTPException(status_code=404, detail=f'LaunchBox could not find "{title}" for {platform}.')

    if len(sorted_candidates) > 1:
        second_score = score(sorted_candidates[1])
        best_is_exact = is_exact_title_and_platform(best_match)
        second_is_exact = is_exact_title_and_platform(sorted_candidates[1])

        # If a single candidate has exact title+platform alignment, trust it.
        if best_is_exact and not second_is_exact:
            return best_match

        # A gap < 30 points between the top two candidates means neither stands out
        # clearly enough to auto-select; surface a 409 so the caller can disambiguate.
        if second_score >= 55 and (best_score - second_score) < 30:
            raise HTTPException(
                status_code=409,
                detail=f'LaunchBox found multiple close matches for "{title}". Please be more specific.',
            )

    return best_match


def resolve_launchbox_game_detail(title: str, platform: str) -> Tuple[str, BeautifulSoup, str, str]:
    search_url = f"https://gamesdb.launchbox-app.com/games/results?search={quote(title.strip().lower())}"
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

    best_match = choose_launchbox_candidate(candidates, title, platform)

    detail_url = urljoin("https://gamesdb.launchbox-app.com", best_match["href"])
    detail_response = requests.get(detail_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    detail_response.raise_for_status()
    detail_soup = BeautifulSoup(detail_response.text, "html.parser")
    resolved_platform = first_text_from_definition(detail_soup, "Platform") or best_match["platform"] or platform
    resolved_title = detail_soup.find("h1").get_text(" ", strip=True) if detail_soup.find("h1") else best_match["title"]
    return detail_url, detail_soup, resolved_platform, resolved_title


def normalize_launchbox_detail_url(raw_url: str) -> str:
    candidate = (raw_url or "").strip()
    if not candidate:
        raise HTTPException(status_code=400, detail="LaunchBox URL is required.")

    parsed = urlparse(candidate)
    if not parsed.scheme and not parsed.netloc:
        parsed = urlparse(f"https://{candidate}")

    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="LaunchBox URL must use http or https.")

    host = (parsed.netloc or "").lower()
    if host not in {"gamesdb.launchbox-app.com", "www.gamesdb.launchbox-app.com"}:
        raise HTTPException(status_code=400, detail="URL must point to gamesdb.launchbox-app.com.")

    path = (parsed.path or "").rstrip("/")
    if not path.startswith("/games/details/"):
        raise HTTPException(status_code=400, detail="LaunchBox URL must be a game details page.")

    return f"https://gamesdb.launchbox-app.com{path}"


def parse_launchbox_game_data(detail_url: str, detail_soup: BeautifulSoup, resolved_platform: str, resolved_title: str) -> dict:

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

    cover_image = safe_fetch_image_data_uri(urljoin(detail_url, cover_section_url)) if cover_section_url else None
    disc_image = safe_fetch_image_data_uri(urljoin(detail_url, disc_section_url)) if disc_section_url else None
    spine_image = safe_fetch_image_data_uri(urljoin(detail_url, spine_section_url)) if spine_section_url else None

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


def fetch_launchbox_game_data_from_url(launchbox_url: str, fallback_platform: str, fallback_title: str) -> dict:
    detail_url = normalize_launchbox_detail_url(launchbox_url)
    detail_response = requests.get(detail_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    detail_response.raise_for_status()
    detail_soup = BeautifulSoup(detail_response.text, "html.parser")

    resolved_platform = first_text_from_definition(detail_soup, "Platform") or fallback_platform
    resolved_title = detail_soup.find("h1").get_text(" ", strip=True) if detail_soup.find("h1") else fallback_title
    return parse_launchbox_game_data(detail_url, detail_soup, resolved_platform, resolved_title)


def fetch_launchbox_game_data(title: str, platform: str) -> dict:
    detail_url, detail_soup, resolved_platform, resolved_title = resolve_launchbox_game_detail(title, platform)
    return parse_launchbox_game_data(detail_url, detail_soup, resolved_platform, resolved_title)


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


def refresh_due_price_data(limit: int = PRICE_REFRESH_BATCH_SIZE, force: bool = False) -> int:
    updated_count = 0
    with Session(engine) as session:
        items = session.exec(
            select(MediaItem)
            .where((MediaItem.category == "Games") | (MediaItem.category == "Music"))
            .order_by(MediaItem.price_last_fetched_at)
        ).all()

        for item in items:
            if updated_count >= limit:
                break
            if item.category == "Games" and not (item.platform or "").strip():
                continue
            if item.category == "Music" and not (item.artist or "").strip():
                continue

            if not force and not is_price_refresh_due(item.price_last_fetched_at):
                continue

            try:
                if fetch_and_store_price_data_for_item(item, force=True):
                    session.add(item)
                    session.commit()
                    updated_count += 1
            except Exception as exc:
                logger.warning("Price refresh failed for item %s: %s", item.id, exc)
                session.rollback()

    return updated_count


def pricing_refresh_scheduler_loop() -> None:
    while True:
        try:
            refresh_due_price_data()
        except Exception as exc:
            logger.warning("Scheduled monthly price refresh cycle failed: %s", exc)
        time.sleep(PRICE_REFRESH_INTERVAL_SECONDS)


def start_pricing_refresh_scheduler() -> None:
    global _pricing_scheduler_started
    if _pricing_scheduler_started or not ENABLE_PRICE_AUTO_REFRESH:
        return
    _pricing_scheduler_started = True
    thread = threading.Thread(target=pricing_refresh_scheduler_loop, daemon=True, name="pricing-refresh-scheduler")
    thread.start()


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
    ensure_price_columns()
    ensure_system_case_type_column()
    ensure_system_appearance_preset_column()
    ensure_system_is_cartridge_inferred_column()
    ensure_system_display_order_column()
    ensure_systems()
    ensure_console_test_games()
    start_pricing_refresh_scheduler()

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
        try:
            fetch_and_store_price_data_for_item(item, force=True)
        except Exception as exc:
            logger.warning("Initial price fetch failed for new item '%s': %s", item.title, exc)
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
    launchbox_url = (payload.launchbox_url or "").strip()
    if not title or not platform:
        raise HTTPException(status_code=400, detail="Game title and platform are required.")

    cached_item: Optional[MediaItem] = None
    if not launchbox_url:
        with Session(engine) as session:
            cached_item = find_cached_game_item(session, title, platform, payload.item_id)
            if cached_item and cached_item.cover_image and cached_item.disc_image and cached_item.spine_image:
                data = media_item_to_game_data(cached_item)
                data["data_source"] = "cache"
                return data

    if launchbox_url:
        fetched = fetch_launchbox_game_data_from_url(launchbox_url, platform, title)
        lb_completeness = launchbox_completeness_from_payload(fetched, platform)
        fetched["launchbox_completeness"] = lb_completeness
        unavailable_resources = launchbox_unavailable_resources(lb_completeness, platform)
        fetched["launchbox_unavailable_resources"] = unavailable_resources
        fetched["launchbox_status"] = launchbox_unavailable_status_message(unavailable_resources, platform)
        fetched = apply_cover_priority(title, platform, fetched)
        fetched["data_source"] = "launchbox"
    else:
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
            data["launchbox_completeness"] = fetched.get("launchbox_completeness")
            data["launchbox_unavailable_resources"] = fetched.get("launchbox_unavailable_resources", [])
            data["launchbox_status"] = fetched.get("launchbox_status", "")
            return data

    fetched["launchbox_completeness"] = fetched.get("launchbox_completeness")
    fetched["launchbox_unavailable_resources"] = fetched.get("launchbox_unavailable_resources", [])
    fetched["launchbox_status"] = fetched.get("launchbox_status", "")
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
        data["launchbox_completeness"] = fetched.get("launchbox_completeness")
        data["launchbox_unavailable_resources"] = fetched.get("launchbox_unavailable_resources", [])
        data["launchbox_status"] = fetched.get("launchbox_status", "")
        return data


@app.api_route("/api/pricing/fetch/{item_id}", methods=["GET", "POST"], response_model=MediaItem)
def fetch_item_price_data(item_id: int, authorization: Optional[str] = Header(default=None)) -> MediaItem:
    require_admin(authorization)
    with Session(engine) as session:
        item = session.get(MediaItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Media item not found")
        if item.category not in {"Games", "Music"}:
            raise HTTPException(status_code=400, detail="Price data is only available for game and music items")

        try:
            fetched = fetch_and_store_price_data_for_item(item, force=True)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Could not fetch price data: {exc}") from exc

        if not fetched:
            raise HTTPException(status_code=404, detail="No pricing data match was found for this item")

        session.add(item)
        session.commit()
        session.refresh(item)
        return item


@app.post("/api/pricing/fetch-wishlist", response_model=MediaItem)
def fetch_wishlist_item_price_data(
    request: WishlistPriceFetchRequest,
    authorization: Optional[str] = Header(default=None),
) -> MediaItem:
    require_admin(authorization)

    title = request.title.strip()
    category = request.category.strip()
    platform = (request.platform or "").strip() or None
    artist = (request.artist or "").strip() or None

    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    if category not in {"Games", "Music"}:
        raise HTTPException(status_code=400, detail="Price data is only available for game and music items")
    if category == "Games" and not platform:
        raise HTTPException(status_code=400, detail="Platform is required to fetch game price data")
    if category == "Music" and not artist:
        raise HTTPException(status_code=400, detail="Artist is required to fetch music price data")

    item = MediaItem(title=title, category=category, platform=platform, artist=artist, genre="")
    try:
        fetched = fetch_price_data_for_item(item)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch price data: {exc}") from exc

    if not fetched:
        raise HTTPException(status_code=404, detail="No pricing data match was found for this item")

    apply_price_data_to_item(item, fetched)
    return item


@app.post("/api/pricing/refresh-monthly")
def refresh_monthly_price_data(authorization: Optional[str] = Header(default=None)) -> dict:
    require_admin(authorization)
    refreshed = refresh_due_price_data(limit=max(PRICE_REFRESH_BATCH_SIZE, 20), force=False)
    return {"refreshed": refreshed}


@app.api_route("/api/fetch-tools/game/{item_id}", methods=["GET", "POST"])
def fetch_tools_game_item(
    item_id: int,
    payload: Optional[FetchToolItemRequest] = Body(default=None),
    mode: Optional[str] = Query(default=None),
    force: Optional[bool] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
) -> dict:
    require_admin(authorization)
    resolved_mode = ((payload.mode if payload else None) or mode or "all").strip().lower()
    if resolved_mode not in {"art", "details", "all"}:
        raise HTTPException(status_code=400, detail="Invalid mode. Use art, details, or all")
    resolved_force = payload.force if payload is not None else bool(force)

    with Session(engine) as session:
        item = session.get(MediaItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Media item not found")
        if item.category != "Games":
            raise HTTPException(status_code=400, detail="Fetch tool endpoint expects a game item")

        try:
            result = process_fetch_tool_game_item(item, resolved_mode, bool(resolved_force))
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Could not fetch game data: {exc}") from exc

        if result.get("changed"):
            session.add(item)
            session.commit()
            session.refresh(item)

        return result


@app.api_route("/api/fetch-tools/music/{item_id}", methods=["GET", "POST"])
def fetch_tools_music_item(
    item_id: int,
    payload: Optional[FetchToolItemRequest] = Body(default=None),
    mode: Optional[str] = Query(default=None),
    force: Optional[bool] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
) -> dict:
    require_admin(authorization)
    resolved_mode = ((payload.mode if payload else None) or mode or "all").strip().lower()
    if resolved_mode not in {"art", "details", "all"}:
        raise HTTPException(status_code=400, detail="Invalid mode. Use art, details, or all")
    resolved_force = payload.force if payload is not None else bool(force)

    with Session(engine) as session:
        item = session.get(MediaItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Media item not found")
        if item.category != "Music":
            raise HTTPException(status_code=400, detail="Fetch tool endpoint expects a music item")

        try:
            result = process_fetch_tool_music_item(item, resolved_mode, bool(resolved_force))
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Could not fetch music data: {exc}") from exc

        if result.get("changed"):
            session.add(item)
            session.commit()
            session.refresh(item)

        return result


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


@app.post("/api/discogs/music-art-options")
def fetch_music_art_options(payload: DiscogsMusicArtOptionsRequest, authorization: Optional[str] = Header(default=None)) -> dict:
    require_admin(authorization)

    title = payload.title.strip()
    artist = payload.artist.strip()
    if not title or not artist:
        raise HTTPException(status_code=400, detail="Album title and artist are required.")

    discogs_options: List[str] = []
    deezer_options: List[str] = []
    discogs_error = ""
    deezer_error = ""

    try:
        discogs_options = fetch_discogs_music_art_option_urls(title, artist)
    except HTTPException as exc:
        discogs_error = str(exc.detail)
    except Exception as exc:
        discogs_error = f"Discogs error: {exc}"

    try:
        deezer_options = fetch_deezer_music_art_option_urls(title, artist)
    except HTTPException as exc:
        deezer_error = str(exc.detail)
    except Exception as exc:
        deezer_error = f"Deezer error: {exc}"

    merged: List[str] = []
    for option in discogs_options + deezer_options:
        if option and option not in merged:
            merged.append(option)
        if len(merged) >= 24:
            break

    if not merged:
        detail_bits = [bit for bit in (discogs_error, deezer_error) if bit]
        detail = " | ".join(detail_bits) if detail_bits else f'Could not find art options for "{title}" by {artist}.'
        raise HTTPException(status_code=404, detail=detail)

    source_labels = []
    if discogs_options:
        source_labels.append(f"Discogs ({len(discogs_options)})")
    if deezer_options:
        source_labels.append(f"Deezer ({len(deezer_options)})")
    source_summary = ", ".join(source_labels) if source_labels else "available sources"

    return {
        "kind": "music",
        "source": "discogs+deezer",
        "status_message": f"Found {len(merged)} art options from {source_summary}.",
        "options_by_source": {
            "discogs": discogs_options,
            "deezer": deezer_options,
        },
        "options": merged,
    }


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
    """Bulk-create game entries with LaunchBox -> IGDB -> Libretro fallback for game data/art."""
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
            results.append(
                {
                    "line": line,
                    "status": "success",
                    "id": item.id,
                    "title": item.title,
                    "unavailable_resources": fetched.get("launchbox_unavailable_resources", []),
                    "status_note": fetched.get("launchbox_status", ""),
                }
            )

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
