"""
Асинхронный движок SQLite и фабрика сессий.
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from backend.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""
    pass


async def init_db():
    """Создать все таблицы (вызывается при старте приложения)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_video_source_columns)


def _migrate_video_source_columns(conn):
    """Добавляет новые колонки в video_sources (SQLite без Alembic)."""
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if "video_sources" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("video_sources")}
    migrations = [
        ("banner_x", "REAL"),
        ("banner_y", "REAL"),
        ("banner_scale", "REAL DEFAULT 0.9"),
        ("banner_opacity", "REAL DEFAULT 0.85"),
        ("subtitles_enabled", "BOOLEAN DEFAULT 1"),
        ("subtitle_font", "VARCHAR(64) DEFAULT 'Arial'"),
        ("subtitle_font_size", "INTEGER DEFAULT 52"),
        ("subtitle_color", "VARCHAR(32) DEFAULT 'white'"),
        ("subtitle_stroke_color", "VARCHAR(32) DEFAULT 'black'"),
        ("subtitle_stroke_width", "INTEGER DEFAULT 3"),
        ("subtitle_x", "REAL"),
        ("subtitle_y", "REAL"),
    ]
    for col_name, col_type in migrations:
        if col_name not in existing:
            conn.execute(text(f"ALTER TABLE video_sources ADD COLUMN {col_name} {col_type}"))


async def get_session() -> AsyncSession:
    """Dependency: предоставляет асинхронную сессию БД."""
    async with async_session() as session:
        yield session
