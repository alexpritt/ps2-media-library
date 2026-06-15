from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlmodel import Field, Session, SQLModel, create_engine, select

DATABASE_PATH = Path(__file__).parent / "media.db"
FRONTEND_BUILD_DIR = Path(__file__).parent.parent / "frontend" / "build"
SUGGESTIONS_DIR = Path(__file__).parent.parent / "frontend" / "suggestions"

app = FastAPI(title="PS2 Media Library API")

class MediaItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    category: str
    platform: Optional[str] = None
    genre: str
    year_released: Optional[int] = None
    players: Optional[int] = None
    artist: Optional[str] = None
    publisher: Optional[str] = None
    format: Optional[str] = None
    region: Optional[str] = None
    cover_image: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None

engine = create_engine(f"sqlite:///{DATABASE_PATH}", echo=False, connect_args={"check_same_thread": False})

def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)

@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()

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

@app.post("/api/media", response_model=MediaItem)
def create_media_item(item: MediaItem) -> MediaItem:
    with Session(engine) as session:
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

@app.put("/api/media/{item_id}", response_model=MediaItem)
def update_media_item(item_id: int, updated: MediaItem) -> MediaItem:
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
def delete_media_item(item_id: int) -> dict:
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
