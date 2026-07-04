"""
Whisper-транскрибация через faster-whisper (локально, без Ollama):
распознавание речи, точные таймкоды сегментов,
авто-рекомендация клипов для Shorts.
"""
import json
import os
import tempfile
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from backend.config import (
    WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE,
    SHORTS_MIN_DURATION, SHORTS_MAX_DURATION,
)


@dataclass
class TranscriptionSegment:
    start: float
    end: float
    text: str
    is_complete_sentence: bool = False
    suggested_shorts: bool = False


@dataclass
class TranscriptionResult:
    full_text: str = ""
    segments: list[TranscriptionSegment] = field(default_factory=list)
    suggested_clips: list[dict] = field(default_factory=list)


def transcribe_audio(
    video_path: str,
    model_name: Optional[str] = None,
    generate_suggestions: bool = True,
    _progress_callback: Optional[callable] = None,
) -> dict:
    """
    Извлекает аудиодорожку из видео и распознаёт речь через faster-whisper.
    Даёт точные таймкоды для каждого сегмента + VAD-фильтр тишины.

    Args:
        video_path: путь к исходному видеофайлу.
        model_name: tiny/base/small/medium/large. По умолчанию из конфига.
        _progress_callback: callable(pct: int, message: str) для обновления прогресса.

    Returns:
        dict с ключами: full_text, segments (list of dict), suggested_clips.
    """
    if not model_name:
        model_name = WHISPER_MODEL

    if _progress_callback:
        _progress_callback(5, "Извлекаю аудиодорожку...")

    audio_path = _extract_audio(video_path)

    try:
        if _progress_callback:
            _progress_callback(10, f"Загружаю модель {model_name}...")

        from faster_whisper import WhisperModel

        model = WhisperModel(
            model_name,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )

        if _progress_callback:
            _progress_callback(20, "Распознаю речь (это может занять несколько минут)...")

        segments_raw, info = model.transcribe(
            audio_path,
            language="ru",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        if _progress_callback:
            _progress_callback(70, "Обрабатываю сегменты...")

        segments: list[TranscriptionSegment] = []
        full_text_parts: list[str] = []

        for seg in segments_raw:
            text = seg.text.strip()
            if not text:
                continue

            is_complete = text.endswith((".", "!", "?", "…"))

            segments.append(TranscriptionSegment(
                start=round(seg.start, 2),
                end=round(seg.end, 2),
                text=text,
                is_complete_sentence=is_complete,
            ))
            full_text_parts.append(text)

        full_text = " ".join(full_text_parts)

        if _progress_callback:
            _progress_callback(85, "Ищу рекомендованные клипы..." if generate_suggestions else "Завершаю транскрипцию...")

        suggested = _suggest_shorts(segments) if generate_suggestions else []

        if _progress_callback:
            _progress_callback(95, "Сохраняю результаты...")

        result = TranscriptionResult(
            full_text=full_text,
            segments=segments,
            suggested_clips=suggested,
        )

        return {
            "full_text": result.full_text,
            "segments": [{"start": s.start, "end": s.end, "text": s.text, "is_complete_sentence": s.is_complete_sentence, "suggested_shorts": s.suggested_shorts} for s in result.segments],
            "suggested_clips": result.suggested_clips,
        }

    finally:
        _safe_remove(audio_path)


def _extract_audio(video_path: str) -> str:
    """Извлекает аудиодорожку в 16kHz mono WAV (формат для Whisper)."""
    from moviepy import VideoFileClip

    fd, audio_path = tempfile.mkstemp(suffix=".wav", prefix="whisper_audio_")
    os.close(fd)

    video = VideoFileClip(video_path)
    try:
        if video.audio is None:
            raise RuntimeError("Видео не содержит аудиодорожки")

        video.audio.write_audiofile(
            audio_path,
            fps=16000,
            codec="pcm_s16le",
            logger=None,
        )
    finally:
        video.close()

    return audio_path


def _suggest_shorts(
    segments: list[TranscriptionSegment],
    min_dur: float = SHORTS_MIN_DURATION,
    max_dur: float = SHORTS_MAX_DURATION,
) -> list[dict]:
    """
    Генерирует клипы с шагом ~10 сек (перекрытие), чтобы покрыть всё видео.
    Каждый клип: от start_time набирает сегменты до min_dur (30с),
    завершаясь на точке, но не превышая max_dur (55с).

    Возвращает список клипов, отсортированных по start_time, без дубликатов.
    """
    if not segments:
        return []

    total_duration = segments[-1].end
    step = 10.0  # шаг между началами клипов (сек)
    seen_starts = set()
    suggested = []

    cursor = 0.0
    while cursor < total_duration - min_dur:
        # Найти первый сегмент, начинающийся >= cursor
        start_idx = None
        for idx, seg in enumerate(segments):
            if seg.end > cursor and (start_idx is None or segments[start_idx].start > seg.start):
                if seg.start >= cursor:
                    start_idx = idx
                    break
                elif start_idx is None:
                    start_idx = idx

        if start_idx is None:
            cursor += step
            continue

        window_segments = []
        window_dur = 0.0
        found = False

        for j in range(start_idx, len(segments)):
            seg = segments[j]
            window_segments.append(seg)
            window_dur = seg.end - window_segments[0].start

            if window_dur >= min_dur and seg.is_complete_sentence:
                if window_dur <= max_dur:
                    found = True
                    break
                else:
                    # Перебор — ищем точку внутри окна
                    for k in range(len(window_segments) - 1, 0, -1):
                        sub_dur = window_segments[k].end - window_segments[0].start
                        if min_dur <= sub_dur <= max_dur and window_segments[k].is_complete_sentence:
                            found = True
                            # обрезаем window_segments до k
                            window_segments = window_segments[:k + 1]
                            window_dur = sub_dur
                            break
                    break

            if window_dur > max_dur:
                break

        if not found or window_dur < min_dur:
            cursor += step
            continue

        start_t = window_segments[0].start
        end_t = window_segments[-1].end
        dur = round(end_t - start_t, 1)

        # Дубликаты по start_time
        key = round(start_t, 1)
        if key in seen_starts:
            cursor += step
            continue
        seen_starts.add(key)

        if dur < min_dur or dur > max_dur:
            cursor += step
            continue

        suggested.append({
            "start_time": start_t,
            "end_time": end_t,
            "text_snippet": " ".join(s.text for s in window_segments),
            "duration": dur,
        })
        for s in window_segments:
            s.suggested_shorts = True

        cursor += step

    return suggested


def _safe_remove(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
