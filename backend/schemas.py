"""
Pydantic-схемы для валидации запросов и форматирования ответов API.
"""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


# ── Project ──

class ProjectCreate(BaseModel):
    title: str = "Без названия"


class ProjectResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    video_source: Optional["VideoSourceResponse"] = None
    clips_count: int = 0

    model_config = {"from_attributes": True}


# ── Video Source ──

class VideoSourceResponse(BaseModel):
    id: str
    filename: str
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    banner_path: Optional[str] = None
    banner_position: str = "bottom"
    has_transcription: bool = False

    model_config = {"from_attributes": True}


class BannerUpdate(BaseModel):
    position: str = "bottom"  # top, center, bottom


# ── Clip ──

class ClipCreate(BaseModel):
    """Создание клипа вручную или из ИИ-рекомендации."""
    start_time: float = Field(ge=0, description="Начало фрагмента в секундах")
    end_time: float = Field(gt=0, description="Конец фрагмента в секундах")
    title: str = ""
    description: str = ""
    text_snippet: str = ""
    include_banner: bool = True
    is_suggested: bool = False


class ClipResponse(BaseModel):
    id: str
    project_id: str
    start_time: float
    end_time: float
    title: str
    description: str
    text_snippet: str
    output_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    include_banner: bool
    is_suggested: bool
    status: str
    yt_status: Optional[str] = None
    yt_url: Optional[str] = None
    vk_status: Optional[str] = None
    vk_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ClipUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    include_banner: Optional[bool] = None


# ── Transcription ──

class TranscriptionSegment(BaseModel):
    start: float
    end: float
    text: str
    is_complete_sentence: bool = False
    suggested_shorts: bool = False


class TranscriptionResponse(BaseModel):
    project_id: str
    full_text: str
    segments: list[TranscriptionSegment]


# ── Processing ──

class ProcessingRequest(BaseModel):
    clip_ids: list[str]  # какие клипы обработать


class ProcessingStatusResponse(BaseModel):
    clip_id: str
    status: str
    output_path: Optional[str] = None
    error: Optional[str] = None


# ── Publishing ──

class PublishRequest(BaseModel):
    clip_ids: list[str]
    platforms: list[str] = ["youtube", "vk"]  # одна или обе платформы
    privacy: str = "private"                  # public, private, unlisted


class PublishStatusResponse(BaseModel):
    clip_id: str
    platform: str
    status: str
    url: Optional[str] = None
    error: Optional[str] = None


# ── Auth Tokens ──

class TokensUpdate(BaseModel):
    vk_access_token: Optional[str] = None
    youtube_client_secret_json: Optional[str] = None  # содержимое client_secret.json


class SaveClipRequest(BaseModel):
    target_dir: str


# ── Rebuild Pydantic forward refs ──
ProjectResponse.model_rebuild()
