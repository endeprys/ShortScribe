"""
Роутер обработки: создание клипов, запуск видеопроцессинга, получение статуса.
"""
import json
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_session
from backend.models import Project, VideoSource, Clip
from backend.schemas import (
    ClipCreate, ClipResponse, ClipUpdate,
    ProcessingRequest, ProcessingStatusResponse, SaveClipRequest,
)

router = APIRouter(prefix="/api/projects", tags=["processing"])


# ── Clip CRUD ──

@router.post("/{project_id}/clips", response_model=ClipResponse)
async def create_clip(
    project_id: str,
    data: ClipCreate,
    session: AsyncSession = Depends(get_session),
):
    """Создать клип (вручную или из ИИ-рекомендации)."""
    project = await _get_project(project_id, session)
    vs = await _get_video_source(project_id, session)

    if data.end_time <= data.start_time:
        raise HTTPException(400, "end_time должен быть больше start_time")
    if data.end_time > (vs.duration or 0):
        raise HTTPException(400, f"end_time превышает длительность видео ({vs.duration:.1f}с)")

    clip = Clip(
        project_id=project_id,
        start_time=data.start_time,
        end_time=data.end_time,
        title=data.title,
        description=data.description,
        text_snippet=data.text_snippet,
        include_banner=data.include_banner,
        is_suggested=data.is_suggested,
    )
    session.add(clip)
    await session.commit()
    await session.refresh(clip)
    return _clip_to_response(clip)


@router.get("/{project_id}/clips", response_model=list[ClipResponse])
async def list_clips(project_id: str, session: AsyncSession = Depends(get_session)):
    """Список всех клипов проекта."""
    await _get_project(project_id, session)
    result = await session.execute(
        select(Clip).where(Clip.project_id == project_id).order_by(Clip.start_time)
    )
    return [_clip_to_response(c) for c in result.scalars().all()]


@router.get("/{project_id}/clips/{clip_id}", response_model=ClipResponse)
async def get_clip(
    project_id: str, clip_id: str, session: AsyncSession = Depends(get_session)
):
    """Получить информацию о клипе."""
    clip = await _get_clip(project_id, clip_id, session)
    return _clip_to_response(clip)


@router.patch("/{project_id}/clips/{clip_id}", response_model=ClipResponse)
async def update_clip(
    project_id: str,
    clip_id: str,
    data: ClipUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Обновить метаданные клипа."""
    clip = await _get_clip(project_id, clip_id, session)
    if data.title is not None:
        clip.title = data.title
    if data.description is not None:
        clip.description = data.description
    if data.include_banner is not None:
        clip.include_banner = data.include_banner
    await session.commit()
    await session.refresh(clip)
    return _clip_to_response(clip)


@router.delete("/{project_id}/clips/{clip_id}")
async def delete_clip(
    project_id: str, clip_id: str, session: AsyncSession = Depends(get_session)
):
    """Удалить клип."""
    clip = await _get_clip(project_id, clip_id, session)
    # Удаляем файлы
    from backend.routers.projects import _safe_remove
    _safe_remove(clip.output_path)
    _safe_remove(clip.thumbnail_path)
    await session.delete(clip)
    await session.commit()
    return {"ok": True}


@router.post("/{project_id}/clips/{clip_id}/generate-metadata")
async def generate_metadata(
    project_id: str,
    clip_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Генерирует название и описание для клипа через Ollama (qwen2.5:7b).
    Использует текст транскрипции (text_snippet) клипа.
    """
    clip = await _get_clip(project_id, clip_id, session)
    if not clip.text_snippet:
        raise HTTPException(400, "У клипа нет текста транскрипции. Сначала выполните распознавание речи.")

    from backend.services.metadata_generator import generate_metadata as _gen

    result = _gen(clip.text_snippet)

    if result.get("error"):
        raise HTTPException(503, f"Ollama ошибка: {result['error']}")

    clip.title = result["title"]
    clip.description = result["description"]
    await session.commit()

    return {"ok": True, "title": result["title"], "description": result["description"]}


@router.post("/{project_id}/clips/{clip_id}/save")
async def save_clip_to_folder(
    project_id: str,
    clip_id: str,
    data: SaveClipRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Копирует готовый клип в указанную папку.
    Body: {"target_dir": "C:\\Users\\...\\Desktop\\Shorts"}
    """
    import shutil
    clip = await _get_clip(project_id, clip_id, session)
    if not clip.output_path:
        raise HTTPException(400, "Клип ещё не обработан")
    if not os.path.exists(clip.output_path):
        raise HTTPException(404, "Файл клипа не найден на диске")

    os.makedirs(data.target_dir, exist_ok=True)
    dest_name = f"{clip.title or 'clip'}_{clip.id}.mp4"
    dest_path = os.path.join(data.target_dir, dest_name)
    shutil.copy2(clip.output_path, dest_path)

    return {"ok": True, "saved_path": dest_path}


# ── Transcription ──

@router.post("/{project_id}/transcribe")
async def start_transcription(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Запустить распознавание речи через faster-whisper в фоновом потоке.
    Режим нарезки берётся из настроек VideoSource (manual / heuristic / ai).
    Возвращает task_id для отслеживания прогресса через GET /api/tasks/{task_id}.
    """
    await _get_project(project_id, session)
    vs = await _get_video_source(project_id, session)

    clip_mode = vs.clip_selection_mode or "heuristic"
    clip_buffer = vs.clip_buffer_seconds if vs.clip_buffer_seconds is not None else 2.0
    ai_duration_mode = vs.ai_clip_duration_mode or "auto"
    ai_min_dur = vs.ai_clip_min_seconds if vs.ai_clip_min_seconds is not None else 20.0
    ai_max_dur = vs.ai_clip_max_seconds if vs.ai_clip_max_seconds is not None else 55.0
    video_duration = vs.duration or 0.0

    from backend.services.task_manager import task_manager
    from backend.services.transcriber import transcribe_audio as _transcribe

    def _run_transcribe_and_save(
        video_path: str,
        pid: str,
        mode: str,
        buffer_sec: float,
        duration: float,
        ai_dur_mode: str,
        ai_min: float,
        ai_max: float,
        _progress_callback=None,
    ):
        """Выполняется в фоновом потоке: транскрибация + нарезка + сохранение в БД."""
        use_heuristic = mode == "heuristic"
        result = _transcribe(
            video_path,
            generate_suggestions=use_heuristic,
            _progress_callback=_progress_callback,
        )

        suggested_clips = []
        ai_error = None

        if mode == "ai":
            from backend.services.clip_selector import find_clips_with_ai
            from backend.services.transcriber import _suggest_shorts, TranscriptionSegment

            ai_result = find_clips_with_ai(
                segments=result["segments"],
                full_text=result["full_text"],
                video_duration=duration,
                buffer_seconds=buffer_sec,
                duration_mode=ai_dur_mode,
                min_duration=ai_min,
                max_duration=ai_max,
                _progress_callback=_progress_callback,
            )
            if ai_result["clips"]:
                suggested_clips = ai_result["clips"]
            else:
                ai_error = ai_result.get("error")
                if _progress_callback:
                    _progress_callback(92, "ИИ не нашёл клипы, использую авто-нарезку...")
                segs = [
                    TranscriptionSegment(
                        start=s["start"], end=s["end"], text=s["text"],
                        is_complete_sentence=s.get("is_complete_sentence", False),
                    )
                    for s in result["segments"]
                ]
                suggested_clips = _suggest_shorts(segs)
        elif mode == "heuristic":
            suggested_clips = result.get("suggested_clips", [])
        # mode == "manual" → suggested_clips остаётся пустым

        import json
        from backend.database import async_session
        from backend.models import VideoSource, Clip
        from backend.services.async_utils import run_async_in_thread
        from sqlalchemy import select, delete, and_

        async def _save():
            async with async_session() as s:
                r = await s.execute(select(VideoSource).where(VideoSource.project_id == pid))
                vs_db = r.scalar_one_or_none()
                if not vs_db:
                    return

                vs_db.transcription = json.dumps({
                    "full_text": result["full_text"],
                    "segments": result["segments"],
                }, ensure_ascii=False)

                # Удаляем старые авто/ИИ-клипы перед созданием новых
                await s.execute(
                    delete(Clip).where(
                        and_(
                            Clip.project_id == pid,
                            Clip.is_suggested.is_(True),
                        )
                    )
                )

                for sug in suggested_clips:
                    title = sug.get("title") or f"Shorts ({_fmt_time_short(sug['start_time'])})"
                    clip = Clip(
                        project_id=pid,
                        start_time=sug["start_time"],
                        end_time=sug["end_time"],
                        text_snippet=sug.get("text_snippet", ""),
                        title=title,
                        is_suggested=True,
                        include_banner=vs_db.banner_path is not None,
                    )
                    s.add(clip)
                await s.commit()

        run_async_in_thread(_save())

        result["suggested_clips"] = suggested_clips
        result["clip_selection_mode"] = mode
        if ai_error:
            result["ai_error"] = ai_error
        return result

    task_id = task_manager.submit(
        "transcribe",
        project_id,
        _run_transcribe_and_save,
        vs.filepath,
        project_id,
        clip_mode,
        clip_buffer,
        video_duration,
        ai_duration_mode,
        ai_min_dur,
        ai_max_dur,
    )

    mode_labels = {
        "manual": "только транскрипт",
        "heuristic": "авто-нарезка",
        "ai": "ИИ-нарезка",
    }

    return {
        "ok": True,
        "task_id": task_id,
        "clip_selection_mode": clip_mode,
        "message": (
            f"Транскрибация запущена ({mode_labels.get(clip_mode, clip_mode)}). "
            "Отслеживайте прогресс через /api/tasks/{task_id}."
        ),
    }


@router.get("/{project_id}/transcription")
async def get_transcription(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Получить сохранённую транскрипцию проекта."""
    import json
    from sqlalchemy import select as sa_select

    await _get_project(project_id, session)

    # Проверяем наличие видео
    result = await session.execute(
        sa_select(VideoSource).where(VideoSource.project_id == project_id)
    )
    vs = result.scalar_one_or_none()
    if not vs:
        raise HTTPException(400, "Видео не загружено в проект")

    if not vs.transcription:
        raise HTTPException(404, "Транскрибация ещё не выполнена")

    data = json.loads(vs.transcription)
    return {
        "project_id": project_id,
        "full_text": data.get("full_text", ""),
        "segments": data.get("segments", []),
    }


# ── Processing ──

@router.post("/{project_id}/process")
async def process_clips(
    project_id: str,
    data: ProcessingRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Запустить обработку выбранных клипов в фоновом потоке.
    Возвращает task_id для отслеживания прогресса.
    """
    await _get_project(project_id, session)
    vs = await _get_video_source(project_id, session)

    from backend.services.task_manager import task_manager
    from backend.services.video_processor import process_clip as _process_clip

    async def _mark_pending():
        for clip_id in data.clip_ids:
            clip = await _get_clip(project_id, clip_id, session)
            clip.status = "pending"
        await session.commit()

    await _mark_pending()

    # Собираем информацию о клипах для фоновой задачи
    clips_spec = []
    for clip_id in data.clip_ids:
        clip = await _get_clip(project_id, clip_id, session)
        clips_spec.append({
            "clip_id": clip.id,
            "start_time": clip.start_time,
            "end_time": clip.end_time,
            "include_banner": clip.include_banner,
        })

    def _run_process(video_path: str, banner_path: str | None, vs_settings: dict,
                     pid: str, specs: list, _progress_callback=None):
        """Выполняется в фоне: обработка всех клипов."""
        import json
        from datetime import datetime
        from backend.database import async_session
        from backend.models import Clip, VideoSource
        from backend.services.async_utils import run_async_in_thread
        from sqlalchemy import select

        transcription_segments = None

        async def _load_transcription():
            nonlocal transcription_segments
            async with async_session() as s:
                r = await s.execute(select(VideoSource).where(VideoSource.project_id == pid))
                vs_db = r.scalar_one_or_none()
                if vs_db and vs_db.transcription:
                    data = json.loads(vs_db.transcription)
                    transcription_segments = data.get("segments", [])

        run_async_in_thread(_load_transcription())

        results = []
        total = len(specs)

        for i, spec in enumerate(specs):
            if _progress_callback:
                base_pct = int(i / total * 100) if total > 0 else 0
                _progress_callback(base_pct, f"Клип {i+1}/{total}...")

            try:
                clip_subtitles = None
                if vs_settings.get("subtitles_enabled", True) and transcription_segments:
                    clip_subtitles = [
                        seg for seg in transcription_segments
                        if seg["end"] > spec["start_time"] and seg["start"] < spec["end_time"]
                    ]

                output_path = _process_clip(
                    input_path=video_path,
                    output_dir=pid,
                    start_time=spec["start_time"],
                    end_time=spec["end_time"],
                    banner_path=banner_path if spec["include_banner"] else None,
                    banner_position=vs_settings.get("banner_position", "bottom"),
                    clip_id=spec["clip_id"],
                    subtitles_segments=clip_subtitles,
                    banner_x=vs_settings.get("banner_x"),
                    banner_y=vs_settings.get("banner_y"),
                    banner_scale=vs_settings.get("banner_scale"),
                    banner_opacity=vs_settings.get("banner_opacity"),
                    subtitles_enabled=vs_settings.get("subtitles_enabled", True),
                    subtitle_font=vs_settings.get("subtitle_font", "Arial"),
                    subtitle_font_size=vs_settings.get("subtitle_font_size"),
                    subtitle_color=vs_settings.get("subtitle_color"),
                    subtitle_stroke_color=vs_settings.get("subtitle_stroke_color"),
                    subtitle_stroke_width=vs_settings.get("subtitle_stroke_width"),
                    subtitle_x=vs_settings.get("subtitle_x"),
                    subtitle_y=vs_settings.get("subtitle_y"),
                )

                # Сохраняем в БД
                async def _save_done():
                    async with async_session() as s:
                        r = await s.execute(
                            select(Clip).where(Clip.id == spec["clip_id"])
                        )
                        c = r.scalar_one_or_none()
                        if c:
                            c.output_path = output_path
                            c.status = "done"
                            c.processed_at = datetime.utcnow()
                            await s.commit()

                run_async_in_thread(_save_done())

                results.append({
                    "clip_id": spec["clip_id"],
                    "status": "done",
                    "output_path": output_path,
                })
            except Exception as e:
                async def _save_error():
                    async with async_session() as s:
                        r = await s.execute(
                            select(Clip).where(Clip.id == spec["clip_id"])
                        )
                        c = r.scalar_one_or_none()
                        if c:
                            c.status = "error"
                            await s.commit()

                run_async_in_thread(_save_error())

                results.append({
                    "clip_id": spec["clip_id"],
                    "status": "error",
                    "error": str(e),
                })

        if _progress_callback:
            _progress_callback(100, f"Готово: {total} клипов")

        return {"results": results}

    vs_settings = {
        "banner_position": vs.banner_position or "bottom",
        "banner_x": vs.banner_x,
        "banner_y": vs.banner_y,
        "banner_scale": vs.banner_scale if vs.banner_scale is not None else 0.9,
        "banner_opacity": vs.banner_opacity if vs.banner_opacity is not None else 0.85,
        "subtitles_enabled": vs.subtitles_enabled if vs.subtitles_enabled is not None else True,
        "subtitle_font": vs.subtitle_font or "Arial",
        "subtitle_font_size": vs.subtitle_font_size or 52,
        "subtitle_color": vs.subtitle_color or "white",
        "subtitle_stroke_color": vs.subtitle_stroke_color or "black",
        "subtitle_stroke_width": vs.subtitle_stroke_width or 3,
        "subtitle_x": vs.subtitle_x,
        "subtitle_y": vs.subtitle_y,
    }

    task_id = task_manager.submit(
        "process",
        project_id,
        _run_process,
        vs.filepath,
        vs.banner_path,
        vs_settings,
        project_id,
        clips_spec,
    )

    return {
        "ok": True,
        "task_id": task_id,
        "message": f"Обработка {len(clips_spec)} клипов запущена в фоне.",
    }


# ── Helpers ──

async def _get_project(project_id: str, session: AsyncSession) -> Project:
    result = await session.execute(select(Project).where(Project.id == project_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Проект не найден")
    return p


async def _get_video_source(project_id: str, session: AsyncSession) -> VideoSource:
    result = await session.execute(
        select(VideoSource).where(VideoSource.project_id == project_id)
    )
    vs = result.scalar_one_or_none()
    if not vs:
        raise HTTPException(400, "Видео не загружено в проект")
    return vs


async def _get_clip(project_id: str, clip_id: str, session: AsyncSession) -> Clip:
    result = await session.execute(
        select(Clip).where(Clip.project_id == project_id, Clip.id == clip_id)
    )
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(404, "Клип не найден")
    return clip


def _fmt_time_short(seconds: float) -> str:
    """Форматирует секунды в MM:SS."""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _clip_to_response(c: Clip) -> ClipResponse:
    return ClipResponse(
        id=c.id,
        project_id=c.project_id,
        start_time=c.start_time,
        end_time=c.end_time,
        title=c.title,
        description=c.description,
        text_snippet=c.text_snippet,
        output_path=c.output_path,
        thumbnail_path=c.thumbnail_path,
        include_banner=c.include_banner,
        is_suggested=c.is_suggested,
        status=c.status,
        yt_status=c.yt_status,
        yt_url=c.yt_url,
        vk_status=c.vk_status,
        vk_url=c.vk_url,
        created_at=c.created_at,
    )
