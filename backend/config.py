"""
Централизованные настройки приложения ShortScribe.
"""
import os
from pathlib import Path

# Версия приложения (для автообновления)
APP_VERSION = "1.0.0"

# Корень проекта
BASE_DIR = Path(__file__).resolve().parent.parent

# Папка для загруженных файлов
UPLOADS_DIR = BASE_DIR / "backend" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Папка для результатов обработки
OUTPUT_DIR = BASE_DIR / "backend" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Путь к базе данных SQLite
DATABASE_URL = f"sqlite+aiosqlite:///{BASE_DIR / 'backend' / 'shorts.db'}"

# Настройки видео
TARGET_WIDTH = 1080          # ширина вертикального видео
TARGET_HEIGHT = 1920         # высота вертикального видео (9:16)
TARGET_FPS = 30              # частота кадров

# Настройки баннера
BANNER_MAX_WIDTH_RATIO = 0.9  # баннер занимает не более 90% ширины
BANNER_OPACITY = 0.85         # прозрачность баннера (1.0 = непрозрачный)

# Позиции баннера
BANNER_POSITIONS = {
    "top": "top",
    "center": "center",
    "bottom": "bottom",
}

# Настройки субтитров
# Шрифт: путь к .ttf или имя системного шрифта (Arial, Impact)
SUBTITLE_FONT = "C:/Windows/Fonts/arial.ttf"   # Arial на Windows
SUBTITLE_FONT_SIZE = 52           # крупный шрифт для 1080×1920
SUBTITLE_COLOR = "white"          # цвет текста
SUBTITLE_STROKE_COLOR = "black"   # цвет обводки
SUBTITLE_STROKE_WIDTH = 3         # толщина обводки (px)
# Позиция: moviepy выставляет по координатам, см. _render_subtitles

# Настройки Whisper (faster-whisper, локально)
WHISPER_MODEL = "small"          # tiny, base, small, medium, large
WHISPER_DEVICE = "cpu"           # cpu или cuda
WHISPER_COMPUTE_TYPE = "int8"    # float16, int8 (int8 — быстрее на CPU)

# Длительность рекомендуемого Shorts (секунды)
SHORTS_MIN_DURATION = 20
SHORTS_MAX_DURATION = 55

# YouTube API
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_CATEGORY_ID = "22"  # People & Blogs

# VK API
VK_API_VERSION = "5.199"

# Допустимые форматы файлов
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm"}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_UPLOAD_SIZE_MB = 2048  # 2 GB
