"""
Видеопроцессор: кроп 9:16, наложение баннера, (будущее) субтитры.
Использует MoviePy для точной покадровой обработки.
"""
import os
from pathlib import Path
from moviepy import VideoFileClip, ImageClip, CompositeVideoClip, TextClip

from backend.config import (
    TARGET_WIDTH, TARGET_HEIGHT, TARGET_FPS,
    BANNER_MAX_WIDTH_RATIO, BANNER_OPACITY, OUTPUT_DIR,
    SUBTITLE_FONT, SUBTITLE_FONT_SIZE, SUBTITLE_COLOR,
    SUBTITLE_STROKE_COLOR, SUBTITLE_STROKE_WIDTH,
)


def process_clip(
    input_path: str,
    output_dir: str,
    start_time: float,
    end_time: float,
    banner_path: str | None = None,
    banner_position: str = "bottom",
    clip_id: str = "",
    subtitles_segments: list | None = None,
    _progress_callback: object = None,
) -> str:
    """
    Основная функция обработки клипа:
    1. Вырезает фрагмент из исходного видео (start_time → end_time).
    2. Кропирует до вертикального формата 9:16 (по центру).
    3. При наличии баннера — накладывает его поверх.
    4. При наличии субтитров — рендерит их с авто-переносом на вертикальном видео.
    5. Сохраняет результат в output_dir.

    subtitles_segments: list[dict] — сегменты транскрипции:
        {"start": 0.0, "end": 3.5, "text": "Привет мир."}
        start/end — абсолютные таймкоды в исходном видео.
    """
    cb = _progress_callback

    out_dir = OUTPUT_DIR / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    output_filename = f"{clip_id or 'clip'}.mp4"
    output_path = str(out_dir / output_filename)

    # Загружаем исходное видео (только нужный фрагмент)
    if cb: cb(10, "Загружаю фрагмент видео...")
    video = VideoFileClip(input_path).subclipped(start_time, end_time)

    try:
        # Шаг 1: Кроп 9:16 по центру
        if cb: cb(25, "Кропирую в 9:16...")
        cropped = _crop_to_vertical(video)

        # Шаг 2: Наложение баннера
        if banner_path and os.path.exists(banner_path):
            if cb: cb(40, "Накладываю баннер...")
            cropped = _overlay_banner(cropped, banner_path, banner_position)

        # Шаг 3: Субтитры
        if subtitles_segments:
            if cb: cb(55, "Рендерю субтитры...")
            cropped = _render_subtitles(cropped, subtitles_segments, start_time)

        # Шаг 4: Экспорт
        if cb: cb(70, "Экспортирую видео...")
        cropped.write_videofile(
            output_path,
            fps=TARGET_FPS,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            bitrate="5000k",
            threads=4,
            logger=None,
        )

        if cb: cb(100, "Готово")
        return output_path

    finally:
        video.close()
        if 'cropped' in dir():
            cropped.close()


def _crop_to_vertical(video: VideoFileClip) -> VideoFileClip:
    """
    Кропирует горизонтальное видео в вертикальное 9:16 (1080×1920).
    Вырезает центральную часть кадра.
    """
    src_w, src_h = video.size

    # Целевые размеры
    target_w = TARGET_WIDTH   # 1080
    target_h = TARGET_HEIGHT  # 1920

    # Если видео уже вертикальное — ресайзим без кропа
    if src_h >= src_w:
        # Просто масштабируем до целевой ширины
        return video.resized(width=target_w)

    # Горизонтальное видео: считаем целевую область кропа
    # Соотношение сторон целевого окна: 9/16 = 0.5625
    target_aspect = target_w / target_h  # 0.5625

    # Сколько пикселей исходного кадра войдёт в окно по ширине:
    crop_w = int(src_h * target_aspect)

    if crop_w > src_w:
        # Видео слишком узкое — берём всю ширину и обрезаем высоту
        crop_h = int(src_w / target_aspect)
        x_center = src_w // 2
        y_center = src_h // 2
        x1, x2 = 0, src_w
        y1 = y_center - crop_h // 2
        y2 = y_center + crop_h // 2
    else:
        # Стандартный случай: кропаем ширину по центру
        x_center = src_w // 2
        x1 = x_center - crop_w // 2
        x2 = x_center + crop_w // 2
        y1, y2 = 0, src_h

    # Вырезаем и масштабируем до целевого разрешения
    cropped = video.cropped(x1=x1, y1=y1, x2=x2, y2=y2)
    return cropped.resized((target_w, target_h))


def _overlay_banner(
    video: VideoFileClip,
    banner_path: str,
    position: str = "bottom",
) -> CompositeVideoClip:
    """
    Накладывает PNG-баннер на видео с заданной позицией.
    Баннер масштабируется под ширину видео.
    """
    # Загружаем баннер
    banner = ImageClip(banner_path)

    # Масштабируем: ширина = 90% от ширины видео
    banner_max_w = int(video.w * BANNER_MAX_WIDTH_RATIO)
    banner_resized = banner.resized(width=banner_max_w)

    # Устанавливаем прозрачность (если баннер не альфа-канал)
    # MoviePy сам обрабатывает PNG с альфа-каналом; opacity для общей прозрачности
    if not _has_alpha(banner_path):
        banner_resized = banner_resized.with_opacity(BANNER_OPACITY)

    # Длительность баннера = длительности видео
    banner_resized = banner_resized.with_duration(video.duration)

    # Позиционирование
    pos_y = _calc_banner_y(video.h, banner_resized.h, position)
    pos_x = (video.w - banner_resized.w) // 2  # по центру горизонтали

    banner_resized = banner_resized.with_position((pos_x, pos_y))

    # Композиция: баннер поверх видео
    return CompositeVideoClip([video, banner_resized])


def _calc_banner_y(video_h: int, banner_h: int, position: str) -> int:
    """Вычисляет Y-координату баннера в зависимости от позиции."""
    margin = 20  # отступ от края
    if position == "top":
        return margin
    elif position == "center":
        return (video_h - banner_h) // 2
    else:  # bottom
        return video_h - banner_h - margin


def _has_alpha(image_path: str) -> bool:
    """Проверяет, есть ли у PNG альфа-канал."""
    try:
        from PIL import Image
        img = Image.open(image_path)
        return img.mode in ("RGBA", "LA", "PA")
    except Exception:
        return False


def _render_subtitles(
    video: VideoFileClip,
    segments: list,
    clip_start: float,
) -> CompositeVideoClip:
    """
    Рендерит субтитры поверх вертикального видео (1080×1920).

    - Авто-перенос длинных строк через TextClip(method='caption', size=(max_w, None))
    - Крупный шрифт с обводкой (stroke)
    - Позиция: нижняя треть экрана, центр по горизонтали
    - segments: [{"start": abs_time, "end": abs_time, "text": "..."}, ...]

    start/end в segments — абсолютные таймкоды. Вычитаем clip_start
    чтобы получить время относительно начала клипа.
    """
    # Целевое видео уже вертикальное: 1080×1920
    vid_w, vid_h = video.w, video.h

    # Максимальная ширина текста: 90% от ширины видео = 972px
    max_text_width = int(vid_w * 0.88)

    text_clips = []

    for seg in segments:
        seg_start = seg["start"] - clip_start
        seg_end = seg["end"] - clip_start

        # Пропускаем сегменты вне диапазона клипа
        if seg_end <= 0 or seg_start >= video.duration:
            continue

        # Обрезаем края
        seg_start = max(0, seg_start)
        seg_end = min(video.duration, seg_end)
        duration = seg_end - seg_start
        if duration <= 0:
            continue

        text = seg.get("text", "").strip()
        if not text:
            continue

        # Создаём текстовый клип с авто-переносом
        # method='caption' — сам разбивает на строки по ширине size
        try:
            txt = TextClip(
                text=text,
                font=SUBTITLE_FONT,
                font_size=SUBTITLE_FONT_SIZE,
                color=SUBTITLE_COLOR,
                stroke_color=SUBTITLE_STROKE_COLOR,
                stroke_width=SUBTITLE_STROKE_WIDTH,
                size=(max_text_width, None),   # авто-высота
                method="caption",               # авто-перенос
            )
        except TypeError:
            # Fallback: некоторые версии moviepy не поддерживают stroke
            txt = TextClip(
                text=text,
                font=SUBTITLE_FONT,
                font_size=SUBTITLE_FONT_SIZE,
                color=SUBTITLE_COLOR,
                size=(max_text_width, None),
                method="caption",
            )

        # Позиционируем: центр по X, от низа с отступом
        # Вычисляем Y так, чтобы текст НИКОГДА не выходил за экран
        txt_x = (vid_w - txt.w) // 2
        bottom_margin = 60  # отступ от нижнего края
        txt_y = vid_h - txt.h - bottom_margin
        txt_y = max(0, txt_y)  # защита от отрицательных значений
        txt = txt.with_position((txt_x, txt_y))
        txt = txt.with_start(seg_start)
        txt = txt.with_duration(duration)

        text_clips.append(txt)

    if not text_clips:
        return video

    return CompositeVideoClip([video] + text_clips)
