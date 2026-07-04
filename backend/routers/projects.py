"""
Роутер для управления проектами: создание, загрузка видео, баннера.
"""
import os
import uuid
import aiofiles
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from backend.database import get_session
from backend.models import Project, VideoSource, Clip
from backend.schemas import (
    ProjectCreate, ProjectResponse, VideoSourceResponse, BannerUpdate,
    SubtitleSettingsUpdate, OverlaySettingsUpdate, ClipSettingsUpdate,
)
from backend.config import (
    UPLOADS_DIR, ALLOWED_VIDEO_EXTENSIONS, ALLOWED_IMAGE_EXTENSIONS,
    MAX_UPLOAD_SIZE_MB, SUBTITLE_FONTS, CLIP_SELECTION_MODES,
    AI_CLIP_DURATION_MODES, AI_CLIP_ABS_MIN_SECONDS, AI_CLIP_ABS_MAX_SECONDS,
    SHORTS_MIN_DURATION, SHORTS_MAX_DURATION,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("/", response_model=ProjectResponse)
async def create_project(
    data: ProjectCreate,
    session: AsyncSession = Depends(get_session),
):
    """Создать новый проект."""
    project = Project(title=data.title)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return _project_to_response(project)


@router.get("/", response_model=list[ProjectResponse])
async def list_projects(session: AsyncSession = Depends(get_session)):
    """Список всех проектов."""
    result = await session.execute(
        select(Project)
        .options(selectinload(Project.video_source), selectinload(Project.clips))
        .order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()

    responses = []
    for p in projects:
        r = _project_to_response(p)
        r.clips_count = len(p.clips) if p.clips else 0
        responses.append(r)
    return responses


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, session: AsyncSession = Depends(get_session)):
    """Получить проект по ID."""
    project = await _get_project_or_404(project_id, session)
    count_result = await session.execute(
        select(func.count(Clip.id)).where(Clip.project_id == project_id)
    )
    r = _project_to_response(project)
    r.clips_count = count_result.scalar() or 0
    return r


@router.post("/{project_id}/upload-video", response_model=VideoSourceResponse)
async def upload_video(
    project_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    """Загрузить исходное видео в проект."""
    project = await _get_project_or_404(project_id, session)

    # Проверка расширения
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(400, f"Недопустимый формат. Разрешены: {ALLOWED_VIDEO_EXTENSIONS}")

    # Сохранение файла
    safe_name = f"{uuid.uuid4().hex}{ext}"
    file_path = UPLOADS_DIR / safe_name

    # Проверка размера (читаем чанками)
    total_size = 0
    async with aiofiles.open(file_path, "wb") as f:
        while chunk := await file.read(8 * 1024 * 1024):  # 8 MB chunks
            total_size += len(chunk)
            if total_size > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                await f.close()
                os.remove(file_path)
                raise HTTPException(413, f"Файл слишком большой. Максимум: {MAX_UPLOAD_SIZE_MB} MB")
            await f.write(chunk)

    # Получаем метаданные видео через moviepy
    from moviepy import VideoFileClip
    try:
        clip_info = VideoFileClip(str(file_path))
        duration = clip_info.duration
        width, height = clip_info.size
        fps = clip_info.fps
        clip_info.close()
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(400, f"Не удалось прочитать видео: {e}")

    # Удаляем старый VideoSource, если был
    existing = await session.execute(
        select(VideoSource).where(VideoSource.project_id == project_id)
    )
    old = existing.scalar_one_or_none()
    if old:
        _safe_remove(old.filepath)
        _safe_remove(old.banner_path)
        await session.delete(old)

    video_source = VideoSource(
        project_id=project_id,
        filename=file.filename,
        filepath=str(file_path),
        file_size=total_size,
        duration=duration,
        width=width,
        height=height,
        fps=fps,
    )
    session.add(video_source)
    await session.commit()
    await session.refresh(video_source)
    return _video_source_to_response(video_source)


@router.post("/{project_id}/upload-banner", response_model=VideoSourceResponse)
async def upload_banner(
    project_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    """Загрузить баннер для проекта."""
    project = await _get_project_or_404(project_id, session)

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(400, f"Недопустимый формат изображения. Разрешены: {ALLOWED_IMAGE_EXTENSIONS}")

    video_source = await session.execute(
        select(VideoSource).where(VideoSource.project_id == project_id)
    )
    vs = video_source.scalar_one_or_none()
    if not vs:
        raise HTTPException(400, "Сначала загрузите видео")

    safe_name = f"banner_{uuid.uuid4().hex}{ext}"
    file_path = UPLOADS_DIR / safe_name

    async with aiofiles.open(file_path, "wb") as f:
        while chunk := await file.read(8 * 1024 * 1024):
            await f.write(chunk)

    # Удаляем старый баннер
    _safe_remove(vs.banner_path)
    vs.banner_path = str(file_path)
    await session.commit()
    await session.refresh(vs)
    return _video_source_to_response(vs)


@router.patch("/{project_id}/banner-settings", response_model=VideoSourceResponse)
async def update_banner_settings(
    project_id: str,
    data: BannerUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Обновить настройки баннера (позиция, координаты, масштаб, прозрачность)."""
    vs = await _get_video_source_or_404(project_id, session)
    fields_set = data.model_fields_set
    if data.position is not None:
        if data.position not in ("top", "center", "bottom"):
            raise HTTPException(400, "position должен быть: top, center, bottom")
        vs.banner_position = data.position
    if "x" in fields_set:
        vs.banner_x = data.x
    if "y" in fields_set:
        vs.banner_y = data.y
    if data.scale is not None:
        vs.banner_scale = data.scale
    if data.opacity is not None:
        vs.banner_opacity = data.opacity
    await session.commit()
    await session.refresh(vs)
    return _video_source_to_response(vs)


@router.patch("/{project_id}/subtitle-settings", response_model=VideoSourceResponse)
async def update_subtitle_settings(
    project_id: str,
    data: SubtitleSettingsUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Обновить настройки субтитров."""
    vs = await _get_video_source_or_404(project_id, session)
    fields_set = data.model_fields_set
    if data.enabled is not None:
        vs.subtitles_enabled = data.enabled
    if data.font is not None:
        if data.font not in SUBTITLE_FONTS:
            raise HTTPException(400, f"Шрифт должен быть одним из: {SUBTITLE_FONTS}")
        vs.subtitle_font = data.font
    if data.font_size is not None:
        vs.subtitle_font_size = data.font_size
    if data.color is not None:
        vs.subtitle_color = data.color
    if data.stroke_color is not None:
        vs.subtitle_stroke_color = data.stroke_color
    if data.stroke_width is not None:
        vs.subtitle_stroke_width = data.stroke_width
    if "x" in fields_set:
        vs.subtitle_x = data.x
    if "y" in fields_set:
        vs.subtitle_y = data.y
    await session.commit()
    await session.refresh(vs)
    return _video_source_to_response(vs)


@router.patch("/{project_id}/overlay-settings", response_model=VideoSourceResponse)
async def update_overlay_settings(
    project_id: str,
    data: OverlaySettingsUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Обновить настройки баннера и субтитров одним запросом."""
    vs = await _get_video_source_or_404(project_id, session)
    if data.banner:
        b = data.banner
        fields_set = b.model_fields_set
        if b.position is not None:
            if b.position not in ("top", "center", "bottom"):
                raise HTTPException(400, "position должен быть: top, center, bottom")
            vs.banner_position = b.position
        if "x" in fields_set:
            vs.banner_x = b.x
        if "y" in fields_set:
            vs.banner_y = b.y
        if b.scale is not None:
            vs.banner_scale = b.scale
        if b.opacity is not None:
            vs.banner_opacity = b.opacity
    if data.subtitles:
        s = data.subtitles
        fields_set = s.model_fields_set
        if s.enabled is not None:
            vs.subtitles_enabled = s.enabled
        if s.font is not None:
            if s.font not in SUBTITLE_FONTS:
                raise HTTPException(400, f"Шрифт должен быть одним из: {SUBTITLE_FONTS}")
            vs.subtitle_font = s.font
        if s.font_size is not None:
            vs.subtitle_font_size = s.font_size
        if s.color is not None:
            vs.subtitle_color = s.color
        if s.stroke_color is not None:
            vs.subtitle_stroke_color = s.stroke_color
        if s.stroke_width is not None:
            vs.subtitle_stroke_width = s.stroke_width
        if "x" in fields_set:
            vs.subtitle_x = s.x
        if "y" in fields_set:
            vs.subtitle_y = s.y
    await session.commit()
    await session.refresh(vs)
    return _video_source_to_response(vs)


@router.patch("/{project_id}/clip-settings", response_model=VideoSourceResponse)
async def update_clip_settings(
    project_id: str,
    data: ClipSettingsUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Обновить режим нарезки клипов (ручной / авто / ИИ)."""
    vs = await _get_video_source_or_404(project_id, session)
    if data.clip_selection_mode is not None:
        if data.clip_selection_mode not in CLIP_SELECTION_MODES:
            raise HTTPException(
                400,
                f"clip_selection_mode должен быть: {', '.join(CLIP_SELECTION_MODES)}",
            )
        vs.clip_selection_mode = data.clip_selection_mode
    if data.clip_buffer_seconds is not None:
        vs.clip_buffer_seconds = data.clip_buffer_seconds
    if data.ai_clip_duration_mode is not None:
        if data.ai_clip_duration_mode not in AI_CLIP_DURATION_MODES:
            raise HTTPException(
                400,
                f"ai_clip_duration_mode должен быть: {', '.join(AI_CLIP_DURATION_MODES)}",
            )
        vs.ai_clip_duration_mode = data.ai_clip_duration_mode
    if data.ai_clip_min_seconds is not None:
        vs.ai_clip_min_seconds = data.ai_clip_min_seconds
    if data.ai_clip_max_seconds is not None:
        vs.ai_clip_max_seconds = data.ai_clip_max_seconds

    # Валидация диапазона длительности
    lo = vs.ai_clip_min_seconds or SHORTS_MIN_DURATION
    hi = vs.ai_clip_max_seconds or SHORTS_MAX_DURATION
    if lo < AI_CLIP_ABS_MIN_SECONDS or hi > AI_CLIP_ABS_MAX_SECONDS:
        raise HTTPException(
            400,
            f"Длительность клипа: от {AI_CLIP_ABS_MIN_SECONDS} до {AI_CLIP_ABS_MAX_SECONDS} сек",
        )
    if lo > hi:
        raise HTTPException(400, "ai_clip_min_seconds не может быть больше ai_clip_max_seconds")

    await session.commit()
    await session.refresh(vs)
    return _video_source_to_response(vs)


@router.get("/overlay-fonts")
async def list_overlay_fonts():
    """Список доступных шрифтов для субтитров."""
    return {"fonts": SUBTITLE_FONTS}


@router.delete("/{project_id}")
async def delete_project(project_id: str, session: AsyncSession = Depends(get_session)):
    """Удалить проект и все связанные файлы."""
    project = await _get_project_or_404(project_id, session)

    # Удаляем файлы
    if project.video_source:
        _safe_remove(project.video_source.filepath)
        _safe_remove(project.video_source.banner_path)
    for clip in project.clips:
        _safe_remove(clip.output_path)
        _safe_remove(clip.thumbnail_path)

    await session.delete(project)
    await session.commit()
    return {"ok": True}


# ── Helpers ──

async def _get_project_or_404(project_id: str, session: AsyncSession) -> Project:
    result = await session.execute(
        select(Project)
        .options(selectinload(Project.video_source), selectinload(Project.clips))
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Проект не найден")
    return project


async def _get_video_source_or_404(project_id: str, session: AsyncSession) -> VideoSource:
    result = await session.execute(
        select(VideoSource).where(VideoSource.project_id == project_id)
    )
    vs = result.scalar_one_or_none()
    if not vs:
        raise HTTPException(404, "Видео не загружено в проект")
    return vs


def _safe_remove(path: str | None):
    """Безопасное удаление файла."""
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _project_to_response(p: Project) -> ProjectResponse:
    vs_resp = None
    # Безопасная проверка без ленивой загрузки relationship
    vs = p.__dict__.get("video_source")
    if vs is not None:
        vs_resp = _video_source_to_response(vs)
    return ProjectResponse(
        id=p.id,
        title=p.title,
        created_at=p.created_at,
        updated_at=p.updated_at,
        video_source=vs_resp,
        clips_count=0,
    )


def _video_source_to_response(vs: VideoSource) -> VideoSourceResponse:
    source_url = None
    banner_url = None
    if vs.filepath:
        fname = Path(vs.filepath).name
        source_url = f"/uploads/{fname}"
    if vs.banner_path:
        banner_url = f"/uploads/{Path(vs.banner_path).name}"

    return VideoSourceResponse(
        id=vs.id,
        filename=vs.filename,
        duration=vs.duration,
        width=vs.width,
        height=vs.height,
        fps=vs.fps,
        banner_path=vs.banner_path,
        banner_position=vs.banner_position or "bottom",
        banner_x=vs.banner_x,
        banner_y=vs.banner_y,
        banner_scale=vs.banner_scale if vs.banner_scale is not None else 0.9,
        banner_opacity=vs.banner_opacity if vs.banner_opacity is not None else 0.85,
        subtitles_enabled=vs.subtitles_enabled if vs.subtitles_enabled is not None else True,
        subtitle_font=vs.subtitle_font or "Arial",
        subtitle_font_size=vs.subtitle_font_size or 52,
        subtitle_color=vs.subtitle_color or "white",
        subtitle_stroke_color=vs.subtitle_stroke_color or "black",
        subtitle_stroke_width=vs.subtitle_stroke_width or 3,
        subtitle_x=vs.subtitle_x,
        subtitle_y=vs.subtitle_y,
        has_transcription=vs.transcription is not None,
        source_video_url=source_url,
        banner_url=banner_url,
        clip_selection_mode=vs.clip_selection_mode or "heuristic",
        clip_buffer_seconds=vs.clip_buffer_seconds if vs.clip_buffer_seconds is not None else 2.0,
        ai_clip_duration_mode=vs.ai_clip_duration_mode or "auto",
        ai_clip_min_seconds=vs.ai_clip_min_seconds if vs.ai_clip_min_seconds is not None else 20.0,
        ai_clip_max_seconds=vs.ai_clip_max_seconds if vs.ai_clip_max_seconds is not None else 55.0,
    )
