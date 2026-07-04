"""
ИИ-подбор клипов через Ollama: анализ полной транскрипции и поиск
логически завершённых интересных фрагментов для Shorts.
"""
import json
import httpx

from backend.config import (
    SHORTS_MIN_DURATION,
    SHORTS_MAX_DURATION,
    DEFAULT_CLIP_BUFFER_SECONDS,
)
from backend.services.metadata_generator import DEFAULT_MODEL, OLLAMA_BASE


def find_clips_with_ai(
    segments: list[dict],
    full_text: str,
    video_duration: float,
    buffer_seconds: float = DEFAULT_CLIP_BUFFER_SECONDS,
    model: str = DEFAULT_MODEL,
    _progress_callback=None,
) -> dict:
    """
    Анализирует транскрипцию через Ollama и возвращает рекомендованные клипы.

    Returns:
        {
            "clips": [{"start_time", "end_time", "text_snippet", "title", "reason", "duration"}],
            "error": str | None,
            "fallback_used": bool,
        }
    """
    if not segments:
        return {"clips": [], "error": "Нет сегментов транскрипции", "fallback_used": False}

    if _progress_callback:
        _progress_callback(88, "ИИ анализирует текст и ищет интересные фрагменты...")

    prompt = _build_prompt(segments, full_text, video_duration)

    try:
        with httpx.Client(timeout=300.0) as client:
            resp = client.post(
                f"{OLLAMA_BASE}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.4, "num_predict": 2000},
                },
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()

        ai_clips = _parse_ai_response(raw)
        clips = _clips_from_ai_segments(
            ai_clips, segments, video_duration, buffer_seconds
        )

        if _progress_callback:
            _progress_callback(94, f"ИИ нашёл {len(clips)} фрагментов")

        return {"clips": clips, "error": None, "fallback_used": False}

    except httpx.ConnectError:
        return {
            "clips": [],
            "error": "Ollama недоступен. Запустите: ollama serve",
            "fallback_used": False,
        }
    except Exception as e:
        return {"clips": [], "error": str(e), "fallback_used": False}


def apply_clip_buffer(
    start_time: float,
    end_time: float,
    video_duration: float,
    buffer_seconds: float,
) -> tuple[float, float]:
    """Добавляет буфер до/после клипа и ограничивает диапазон видео."""
    start = max(0.0, start_time - buffer_seconds)
    end = min(video_duration, end_time + buffer_seconds) if video_duration else end_time + buffer_seconds
    return round(start, 2), round(end, 2)


def _build_prompt(segments: list[dict], full_text: str, video_duration: float) -> str:
    """Формирует промпт для Ollama с нумерованными сегментами."""
    lines = []
    for i, seg in enumerate(segments):
        t0 = _fmt_time(seg["start"])
        t1 = _fmt_time(seg["end"])
        lines.append(f"[{i}] {t0}–{t1}: {seg['text']}")

    segments_block = "\n".join(lines[:200])  # ограничиваем контекст
    if len(segments) > 200:
        segments_block += f"\n... ещё {len(segments) - 200} сегментов"

    return f"""Ты — редактор YouTube Shorts. Проанализируй транскрипцию видео ({_fmt_time(video_duration)}).
Найди 3–8 самых интересных фрагментов для коротких вертикальных роликов.

Требования к каждому фрагменту:
- Длительность от {SHORTS_MIN_DURATION} до {SHORTS_MAX_DURATION} секунд (по таймкодам сегментов)
- Логически завершённая мысль (история, совет, шутка, инсайт — не обрыв на полуслове)
- Начало должно быть понятным без предыдущего контекста
- Конец — на естественной паузе или завершении мысли
- Фрагменты не должны сильно пересекаться

СЕГМЕНТЫ ТРАНСКРИПЦИИ (индекс | время | текст):
{segments_block}

ПОЛНЫЙ ТЕКСТ (сокращённо):
{full_text[:3000]}

Ответь ТОЛЬКО JSON без markdown:
{{"clips": [
  {{"start_segment_index": 0, "end_segment_index": 5, "title": "Краткое название", "reason": "Почему интересно"}},
  ...
]}}

Используй start_segment_index и end_segment_index — номера сегментов из списка выше (включительно)."""


def _parse_ai_response(raw: str) -> list[dict]:
    """Извлекает список клипов из ответа модели."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("ИИ не вернул JSON")

    data = json.loads(raw[start:end + 1])
    clips = data.get("clips", [])
    if not isinstance(clips, list):
        raise ValueError("Неверный формат ответа ИИ")
    return clips


def _clips_from_ai_segments(
    ai_clips: list[dict],
    segments: list[dict],
    video_duration: float,
    buffer_seconds: float,
) -> list[dict]:
    """Преобразует ответ ИИ в клипы с таймкодами и буфером."""
    result = []
    last_end = -1.0

    for item in ai_clips:
        try:
            start_idx = int(item.get("start_segment_index", item.get("start_idx", -1)))
            end_idx = int(item.get("end_segment_index", item.get("end_idx", -1)))
        except (TypeError, ValueError):
            continue

        if start_idx < 0 or end_idx < start_idx or end_idx >= len(segments):
            continue

        raw_start = segments[start_idx]["start"]
        raw_end = segments[end_idx]["end"]
        start_time, end_time = apply_clip_buffer(
            raw_start, raw_end, video_duration, buffer_seconds
        )

        duration = end_time - start_time
        if duration < SHORTS_MIN_DURATION - buffer_seconds:
            continue
        if duration > SHORTS_MAX_DURATION + buffer_seconds * 2:
            continue
        if start_time < last_end - 5:
            continue  # сильное пересечение с предыдущим

        text_snippet = " ".join(
            segments[i]["text"] for i in range(start_idx, end_idx + 1)
        ).strip()

        title = str(item.get("title", "")).strip()[:100]
        if not title:
            title = f"Shorts ({_fmt_time(start_time)})"

        result.append({
            "start_time": start_time,
            "end_time": end_time,
            "text_snippet": text_snippet,
            "title": title,
            "reason": str(item.get("reason", "")).strip(),
            "duration": round(duration, 1),
        })
        last_end = end_time

    return result


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"
