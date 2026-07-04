"""
SQLAlchemy ORM модели: Project, VideoSource, Clip.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base


def gen_uuid() -> str:
    return uuid.uuid4().hex[:12]


class Project(Base):
    """
    Проект — контейнер для одного исходного видео и его клипов.
    """
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_uuid)
    title: Mapped[str] = mapped_column(String(256), default="Без названия")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    video_source: Mapped["VideoSource | None"] = relationship(
        "VideoSource", back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    clips: Mapped[list["Clip"]] = relationship(
        "Clip", back_populates="project", cascade="all, delete-orphan"
    )


class VideoSource(Base):
    """
    Исходное видео, загруженное в проект.
    """
    __tablename__ = "video_sources"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(12), ForeignKey("projects.id"), unique=True)
    filename: Mapped[str] = mapped_column(String(512))          # оригинальное имя
    filepath: Mapped[str] = mapped_column(String(1024))          # путь на диске
    file_size: Mapped[int | None] = mapped_column(Integer)       # байт
    duration: Mapped[float | None] = mapped_column(Float)        # длительность в секундах
    width: Mapped[int | None] = mapped_column(Integer)           # исходная ширина
    height: Mapped[int | None] = mapped_column(Integer)          # исходная высота
    fps: Mapped[float | None] = mapped_column(Float)             # кадров в секунду
    banner_path: Mapped[str | None] = mapped_column(String(1024))  # путь к баннеру
    banner_position: Mapped[str] = mapped_column(String(16), default="bottom")
    banner_x: Mapped[float | None] = mapped_column(Float)          # X на холсте 1080×1920
    banner_y: Mapped[float | None] = mapped_column(Float)          # Y на холсте 1080×1920
    banner_scale: Mapped[float] = mapped_column(Float, default=0.9)
    banner_opacity: Mapped[float] = mapped_column(Float, default=0.85)

    # Настройки субтитров (координаты — холст 1080×1920)
    subtitles_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    subtitle_font: Mapped[str] = mapped_column(String(64), default="Arial")
    subtitle_font_size: Mapped[int] = mapped_column(Integer, default=52)
    subtitle_color: Mapped[str] = mapped_column(String(32), default="white")
    subtitle_stroke_color: Mapped[str] = mapped_column(String(32), default="black")
    subtitle_stroke_width: Mapped[int] = mapped_column(Integer, default=3)
    subtitle_x: Mapped[float | None] = mapped_column(Float)        # левый край текстового блока
    subtitle_y: Mapped[float | None] = mapped_column(Float)          # верхний край текстового блока

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Транскрипция (JSON-строка с таймкодами)
    transcription: Mapped[str | None] = mapped_column(Text)

    project: Mapped["Project"] = relationship("Project", back_populates="video_source")


class Clip(Base):
    """
    Нарезанный клип (Shorts).
    """
    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(12), ForeignKey("projects.id"))

    # Временной диапазон в исходном видео
    start_time: Mapped[float] = mapped_column(Float)    # секунды
    end_time: Mapped[float] = mapped_column(Float)      # секунды

    # Метаданные
    title: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    text_snippet: Mapped[str] = mapped_column(Text, default="")  # фрагмент транскрипции

    # Файлы
    output_path: Mapped[str | None] = mapped_column(String(1024))
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024))

    # Статусы
    is_suggested: Mapped[bool] = mapped_column(Boolean, default=False)   # ИИ-рекомендация
    include_banner: Mapped[bool] = mapped_column(Boolean, default=True)

    # Статус обработки: pending, processing, done, error
    status: Mapped[str] = mapped_column(String(32), default="pending")

    # Статусы публикации
    yt_status: Mapped[str | None] = mapped_column(String(32))  # published, error
    yt_url: Mapped[str | None] = mapped_column(String(1024))
    vk_status: Mapped[str | None] = mapped_column(String(32))
    vk_url: Mapped[str | None] = mapped_column(String(1024))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)

    project: Mapped["Project"] = relationship("Project", back_populates="clips")


class Settings(Base):
    """
    Хранилище токенов API (одна запись — синглтон).
    """
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    vk_access_token: Mapped[str | None] = mapped_column(Text)
    youtube_client_secret: Mapped[str | None] = mapped_column(Text)  # JSON-строка
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
