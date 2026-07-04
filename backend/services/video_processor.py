"""
Видеопроцессор: кроп 9:16, наложение баннера, субтитры.
Использует MoviePy для точной покадровой обработки.
"""
import os
from pathlib import Path
from moviepy import VideoFileClip, ImageClip, CompositeVideoClip, TextClip

from backend.config import (
    TARGET_WIDTH, TARGET_HEIGHT, TARGET_FPS,
    BANNER_MAX_WIDTH_RATIO, BANNER_OPACITY, OUTPUT_DIR,
    SUBTITLE_FONT_SIZE, SUBTITLE_COLOR,
    SUBTITLE_STROKE_COLOR, SUBTITLE_STROKE_WIDTH,
    resolve_subtitle_font,
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
    banner_x: float | None = None,
    banner_y: float | None = None,
    banner_scale: float | None = None,
    banner_opacity: float | None = None,
    subtitles_enabled: bool = True,
    subtitle_font: str = "Arial",
    subtitle_font_size: int | None = None,
    subtitle_color: str | None = None,
    subtitle_stroke_color: str | None = None,
    subtitle_stroke_width: int | None = None,
    subtitle_x: float | None = None,
    subtitle_y: float | None = None,
    _progress_callback: object = None,
) -> str:
    """
    Основная функция обработки клипа:
    1. Вырезает фрагмент из исходного видео (start_time → end_time).
    2. Кропирует до вертикального формата 9:16 (по центру).
    3. При наличии баннера — накладывает его поверх.
    4. При наличии субтитров — рендерит их с авто-переносом на вертикальном видео.
    5. Сохраняет результат в output_dir.
    """
    cb = _progress_callback

    out_dir = OUTPUT_DIR / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    output_filename = f"{clip_id or 'clip'}.mp4"
    output_path = str(out_dir / output_filename)

    if cb:
        cb(10, "Загружаю фрагмент видео...")
    video = VideoFileClip(input_path).subclipped(start_time, end_time)

    try:
        if cb:
            cb(25, "Кропирую в 9:16...")
        cropped = _crop_to_vertical(video)

        if banner_path and os.path.exists(banner_path):
            if cb:
                cb(40, "Накладываю баннер...")
            cropped = _overlay_banner(
                cropped,
                banner_path,
                banner_position,
                x=banner_x,
                y=banner_y,
                scale=banner_scale,
                opacity=banner_opacity,
            )

        if subtitles_enabled and subtitles_segments:
            if cb:
                cb(55, "Рендерю субтитры...")
            cropped = _render_subtitles(
                cropped,
                subtitles_segments,
                start_time,
                font=subtitle_font,
                font_size=subtitle_font_size or SUBTITLE_FONT_SIZE,
                color=subtitle_color or SUBTITLE_COLOR,
                stroke_color=subtitle_stroke_color or SUBTITLE_STROKE_COLOR,
                stroke_width=subtitle_stroke_width if subtitle_stroke_width is not None else SUBTITLE_STROKE_WIDTH,
                pos_x=subtitle_x,
                pos_y=subtitle_y,
            )

        if cb:
            cb(70, "Экспортирую видео...")
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

        if cb:
            cb(100, "Готово")
        return output_path

    finally:
        video.close()
        if 'cropped' in dir():
            cropped.close()


def _crop_to_vertical(video: VideoFileClip) -> VideoFileClip:
    """Кропирует горизонтальное видео в вертикальное 9:16 (1080×1920)."""
    src_w, src_h = video.size
    target_w = TARGET_WIDTH
    target_h = TARGET_HEIGHT

    if src_h >= src_w:
        return video.resized(width=target_w)

    target_aspect = target_w / target_h
    crop_w = int(src_h * target_aspect)

    if crop_w > src_w:
        crop_h = int(src_w / target_aspect)
        x_center = src_w // 2
        y_center = src_h // 2
        x1, x2 = 0, src_w
        y1 = y_center - crop_h // 2
        y2 = y_center + crop_h // 2
    else:
        x_center = src_w // 2
        x1 = x_center - crop_w // 2
        x2 = x_center + crop_w // 2
        y1, y2 = 0, src_h

    cropped = video.cropped(x1=x1, y1=y1, x2=x2, y2=y2)
    return cropped.resized((target_w, target_h))


def _overlay_banner(
    video: VideoFileClip,
    banner_path: str,
    position: str = "bottom",
    x: float | None = None,
    y: float | None = None,
    scale: float | None = None,
    opacity: float | None = None,
) -> CompositeVideoClip:
    """Накладывает PNG-баннер на видео."""
    banner = ImageClip(banner_path)

    scale_ratio = scale if scale is not None else BANNER_MAX_WIDTH_RATIO
    banner_max_w = int(video.w * scale_ratio)
    banner_resized = banner.resized(width=banner_max_w)

    opacity_val = opacity if opacity is not None else BANNER_OPACITY
    if not _has_alpha(banner_path):
        banner_resized = banner_resized.with_opacity(opacity_val)

    banner_resized = banner_resized.with_duration(video.duration)

    if x is not None and y is not None:
        pos_x, pos_y = int(x), int(y)
    else:
        pos_y = _calc_banner_y(video.h, banner_resized.h, position)
        pos_x = (video.w - banner_resized.w) // 2

    banner_resized = banner_resized.with_position((pos_x, pos_y))
    return CompositeVideoClip([video, banner_resized])


def _calc_banner_y(video_h: int, banner_h: int, position: str) -> int:
    """Вычисляет Y-координату баннера в зависимости от позиции."""
    margin = 20
    if position == "top":
        return margin
    elif position == "center":
        return (video_h - banner_h) // 2
    else:
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
    font: str = "Arial",
    font_size: int = SUBTITLE_FONT_SIZE,
    color: str = SUBTITLE_COLOR,
    stroke_color: str = SUBTITLE_STROKE_COLOR,
    stroke_width: int = SUBTITLE_STROKE_WIDTH,
    pos_x: float | None = None,
    pos_y: float | None = None,
) -> CompositeVideoClip:
    """Рендерит субтитры поверх вертикального видео (1080×1920)."""
    vid_w, vid_h = video.w, video.h
    max_text_width = int(vid_w * 0.88)
    font_path = resolve_subtitle_font(font)

    text_clips = []

    for seg in segments:
        seg_start = seg["start"] - clip_start
        seg_end = seg["end"] - clip_start

        if seg_end <= 0 or seg_start >= video.duration:
            continue

        seg_start = max(0, seg_start)
        seg_end = min(video.duration, seg_end)
        duration = seg_end - seg_start
        if duration <= 0:
            continue

        text = seg.get("text", "").strip()
        if not text:
            continue

        try:
            txt = TextClip(
                text=text,
                font=font_path,
                font_size=font_size,
                color=color,
                stroke_color=stroke_color,
                stroke_width=stroke_width,
                size=(max_text_width, None),
                method="caption",
            )
        except TypeError:
            txt = TextClip(
                text=text,
                font=font_path,
                font_size=font_size,
                color=color,
                size=(max_text_width, None),
                method="caption",
            )

        if pos_x is not None and pos_y is not None:
            txt_x = int(pos_x)
            txt_y = int(pos_y)
        else:
            txt_x = (vid_w - txt.w) // 2
            bottom_margin = 60
            txt_y = max(0, vid_h - txt.h - bottom_margin)

        txt = txt.with_position((txt_x, txt_y))
        txt = txt.with_start(seg_start)
        txt = txt.with_duration(duration)
        text_clips.append(txt)

    if not text_clips:
        return video

    return CompositeVideoClip([video] + text_clips)
