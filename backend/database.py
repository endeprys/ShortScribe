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


async def get_session() -> AsyncSession:
    """Dependency: предоставляет асинхронную сессию БД."""
    async with async_session() as session:
        yield session
