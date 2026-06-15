from pathlib import Path
from sqlmodel import Session, select, func
from main import MediaItem, engine, create_db_and_tables

if __name__ == "__main__":
    create_db_and_tables()
    with Session(engine) as session:
        record_count = session.exec(select(func.count()).select_from(MediaItem)).one()
        if record_count > 0:
            print("Database already seeded.")
        else:
            sample_items = [
                MediaItem(
                    title="Shadow of the Colossus",
                    category="Games",
                    platform="PlayStation 2",
                    genre="Action-Adventure",
                    year_released=2005,
                    players=1,
                    publisher="Sony Computer Entertainment",
                    format="Disc",
                    region="NTSC",
                    tags="classic,ps2",
                ),
                MediaItem(
                    title="The Last of Us",
                    category="Games",
                    platform="PlayStation 3",
                    genre="Action-Adventure",
                    year_released=2013,
                    players=1,
                    publisher="Sony Computer Entertainment",
                    format="Disc",
                    region="NTSC",
                    tags="ps3,survival",
                ),
                MediaItem(
                    title="Dark Souls II",
                    category="Games",
                    platform="PlayStation 4",
                    genre="RPG",
                    year_released=2014,
                    players=1,
                    publisher="Bandai Namco",
                    format="Disc",
                    region="NTSC",
                    tags="ps4,rpg",
                ),
                MediaItem(
                    title="Abbey Road",
                    category="Music",
                    artist="The Beatles",
                    genre="Rock",
                    year_released=1969,
                    format="Vinyl",
                    tags="classic,vintage",
                ),
                MediaItem(
                    title="Random Access Memories",
                    category="Music",
                    artist="Daft Punk",
                    genre="Electronic",
                    year_released=2013,
                    format="Vinyl",
                    tags="electronic",
                ),
            ]
            session.add_all(sample_items)
            session.commit()
            print("Seeded sample media items.")
