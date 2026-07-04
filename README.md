# 🎬 ShortScribe

**Automatic vertical Shorts and clip creation with AI subtitles.**

ShortScribe is a local desktop web app that turns long horizontal videos into vertical Shorts/clips with subtitles, banner overlays, and optional publishing to YouTube Shorts and VK Clips. Everything runs locally on your PC — no paid APIs required.

---

## ✨ Features

- 🎤 **Speech recognition** — Whisper (`faster-whisper`) with Russian language support
- ✂️ **Auto clipping** — heuristic or AI-powered fragment selection (20–55 sec)
- 🤖 **AI clip selection** — Ollama finds logically complete, interesting segments
- 👁 **Overlay preview** — preview and drag subtitles/banners before processing
- 📝 **Subtitles** — auto word-wrap, stroke, customizable font/size/color
- 🖼️ **Banners** — PNG overlay with transparency (top/center/bottom or free position)
- 🤖 **AI titles** — generate titles and descriptions via Ollama (qwen2.5)
- 📤 **Publishing** — YouTube Shorts + VK Clips (via API)
- 🔄 **Auto-update** — check for new versions on GitHub, `git pull` from the UI
- 🖥️ **Web UI** — dark theme, drag & drop, progress bar, preview

---

## 🛠 Requirements

| Component | Purpose |
|-----------|---------|
| **Python 3.11+** | Backend (FastAPI) |
| **FFmpeg** | Video processing |
| **Ollama** | AI clip selection & title generation (qwen2.5:7b) |
| **Git** (optional) | Auto-update |

---

## 🚀 Quick start

```bash
# 1. Clone
git clone https://github.com/username/ShortScribe.git
cd ShortScribe

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Ollama (if not already installed)
#    https://ollama.com/download
ollama serve              # run in a separate terminal
ollama pull qwen2.5:7b    # model for AI clip selection & titles

# 4. Run
python run.py
#    Open http://127.0.0.1:8080
```

On first launch, the app checks Ollama and reports if additional models are needed.

---

## 🦙 Ollama setup

The app checks Ollama on startup. If Ollama is not running or models are missing, you will see a warning in the console and in the UI (Settings → Ollama).

**Install the model:**
```bash
ollama pull qwen2.5:7b
```

Without Ollama, everything works except AI clip selection and title generation (you can cut clips manually and enter titles yourself).

---

## ⚙️ Configuration

Main settings in `backend/config.py`:

```python
WHISPER_MODEL = "small"        # tiny/base/small/medium/large
TARGET_WIDTH = 1080            # vertical video width
TARGET_HEIGHT = 1920           # vertical video height
SUBTITLE_FONT_SIZE = 52        # subtitle size
SHORTS_MIN_DURATION = 20       # min Shorts duration (sec)
SHORTS_MAX_DURATION = 55       # max Shorts duration
```

YouTube/VK tokens — in the UI (Settings tab).

Clip selection mode (manual / auto / AI), overlay settings, and buffer — in the UI before analysis.

---

## 🔄 Auto-update

1. **Settings → Update** → “Check for updates”
2. If a new version is available — click “Update now” (`git pull`)
3. Restart the app after updating

Works only if the project was cloned via `git clone`.

---

## 📁 Project structure

```
ShortScribe/
├── backend/            # FastAPI server
│   ├── main.py         # entry point, routes
│   ├── config.py       # settings
│   ├── database.py     # SQLite + async SQLAlchemy
│   ├── models.py       # ORM models
│   ├── routers/        # API endpoints
│   └── services/       # video, whisper, youtube, vk, ollama, updater
├── frontend/           # SPA (Vanilla JS + Tailwind CSS)
├── run.py              # launch: python run.py
├── requirements.txt
└── .gitignore
```

---

## 📄 License

MIT — use freely, keep the copyright notice.

---
---

# 🇷🇺 Русская версия

**Автоматическая нарезка вертикальных Shorts и Клипов с ИИ-субтитрами.**

ShortScribe — это локальное десктопное веб-приложение, которое превращает длинные горизонтальные видео в вертикальные Shorts/Клипы с субтитрами, баннерами и автоматической публикацией в YouTube Shorts и VK Клипы. Всё работает локально на вашем ПК, без платных API.

---

## ✨ Возможности

- 🎤 **Распознавание речи** — Whisper (`faster-whisper`) на русском языке
- ✂️ **Авто-нарезка** — эвристика или ИИ-подбор фрагментов (20–55 сек)
- 🤖 **ИИ-нарезка** — Ollama находит логически завершённые интересные фрагменты
- 👁 **Предпросмотр оверлеев** — настройка и перетаскивание субтитров/баннера до обработки
- 📝 **Субтитры** — авто-перенос, обводка, настройка шрифта/размера/цвета
- 🖼️ **Баннеры** — наложение PNG с прозрачностью (верх/центр/низ или свободная позиция)
- 🤖 **AI-названия** — генерация заголовков и описаний через Ollama (qwen2.5)
- 📤 **Публикация** — YouTube Shorts + VK Клипы (через API)
- 🔄 **Автообновление** — проверка новых версий на GitHub, `git pull` по кнопке
- 🖥️ **Web UI** — тёмная тема, Drag & Drop, прогресс-бар, предпросмотр

---

## 🛠 Требования

| Компонент | Назначение |
|-----------|-----------|
| **Python 3.11+** | Backend (FastAPI) |
| **FFmpeg** | Обработка видео |
| **Ollama** | ИИ-нарезка и генерация названий (qwen2.5:7b) |
| **Git** (опционально) | Автообновление |

---

## 🚀 Быстрый старт

```bash
# 1. Клонировать
git clone https://github.com/username/ShortScribe.git
cd ShortScribe

# 2. Установить зависимости
pip install -r requirements.txt

# 3. Установить Ollama (если ещё нет)
#    https://ollama.com/download
ollama serve              # запустить в отдельном терминале
ollama pull qwen2.5:7b    # модель для ИИ-нарезки и генерации названий

# 4. Запустить
python run.py
#    Открыть http://127.0.0.1:8080
```

При первом запуске приложение проверит Ollama и сообщит, если нужны дополнительные модели.

---

## 🦙 Подключение Ollama

Приложение автоматически проверяет Ollama при старте. Если Ollama не запущен или не хватает моделей — вы увидите предупреждение в консоли и в UI (вкладка Настройки → Ollama).

**Установка модели:**
```bash
ollama pull qwen2.5:7b
```

Без Ollama работает всё, кроме ИИ-нарезки и генерации названий (можно нарезать вручную и вводить названия сами).

---

## ⚙️ Конфигурация

Основные настройки в `backend/config.py`:

```python
WHISPER_MODEL = "small"        # tiny/base/small/medium/large
TARGET_WIDTH = 1080            # ширина вертикального видео
TARGET_HEIGHT = 1920           # высота
SUBTITLE_FONT_SIZE = 52        # размер субтитров
SHORTS_MIN_DURATION = 20       # мин. длительность Shorts (сек)
SHORTS_MAX_DURATION = 55       # макс. длительность
```

Токены YouTube/VK — в UI (вкладка Настройки).

Режим нарезки (вручную / авто / ИИ), настройки оверлеев и буфер — в UI перед анализом.

---

## 🔄 Автообновление

1. Вкладка **Настройки → Обновление** → «Проверить обновления»
2. При наличии новой версии — кнопка «Обновить сейчас» (делает `git pull`)
3. После обновления — перезапустить приложение

Работает только если проект склонирован через `git clone`.

---

## 📁 Структура

```
ShortScribe/
├── backend/            # FastAPI сервер
│   ├── main.py         # точка входа, роуты
│   ├── config.py       # настройки
│   ├── database.py     # SQLite + async SQLAlchemy
│   ├── models.py       # ORM модели
│   ├── routers/        # API эндпоинты
│   └── services/       # видео, whisper, youtube, vk, ollama, updater
├── frontend/           # SPA (Vanilla JS + Tailwind CSS)
├── run.py              # запуск: python run.py
├── requirements.txt
└── .gitignore
```

---

## 📄 Лицензия

MIT — делайте что хотите, только сохраняйте копирайт.
