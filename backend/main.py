from pathlib import Path
from typing import Dict, Iterator, List, Optional
import secrets

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import text
from sqlmodel import Field, Session, SQLModel, create_engine, select

DATABASE_PATH = Path(__file__).parent / "media.db"
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
    release_date: Optional[str] = None
    year_released: Optional[int] = None
    players: Optional[int] = None
    artist: Optional[str] = None
    publisher: Optional[str] = None
    format: Optional[str] = None
    region: Optional[str] = None
    cover_image: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None


class AdminLoginRequest(SQLModel):
    password: str

engine = create_engine(f"sqlite:///{DATABASE_PATH}", echo=False, connect_args={"check_same_thread": False})

def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def ensure_release_date_column() -> None:
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(mediaitem)")).fetchall()
        has_release_date = any(column[1] == "release_date" for column in columns)
        if not has_release_date:
            connection.execute(text("ALTER TABLE mediaitem ADD COLUMN release_date VARCHAR"))


def require_admin(authorization: Optional[str]) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin authorization required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token or token not in admin_tokens:
        raise HTTPException(status_code=401, detail="Invalid admin token")

@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()
    ensure_release_date_column()

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
        years = session.exec(
            select(MediaItem.year_released).distinct().order_by(MediaItem.year_released)
        ).all()
        return {
            "categories": categories,
            "platforms": platforms,
            "genres": genres,
            "years": sorted([year for year in years if year is not None]),
        }


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
