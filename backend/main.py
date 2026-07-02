"""
Главный FastAPI-сервер. Собирает все роутеры, статику, CORS.
"""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.routers import projects, processing, publishing
from backend.services.task_manager import task_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл: создание таблиц, проверка Ollama, автообновление."""
    await init_db()

    # Проверка Ollama (без блокировки старта)
    import asyncio as _aio
    _aio.create_task(_startup_checks())

    yield


async def _startup_checks():
    """Фоновые проверки при старте."""
    from backend.services.ollama_check import check_ollama, auto_pull_models
    status = check_ollama()
    if not status["running"]:
        print(f"[ShortScribe] ⚠ {status['error']}")
    elif status["missing_models"]:
        print(f"[ShortScribe] ⚠ Не хватает моделей Ollama: {status['missing_models']}")
        print("[ShortScribe] Запустите авто-установку: ollama pull qwen2.5:7b")

    # Проверка обновлений
    from backend.services.updater import check_update as _cu
    update = _cu()
    if update["update_available"]:
        print(f"[ShortScribe] 🔔 Доступна новая версия: {update['latest']} (текущая: {update['current']})")
        print(f"[ShortScribe] Скачайте: {update['url']}")


app = FastAPI(
    title="ShortScribe",
    description="Автоматическая нарезка Shorts и Клипов с Whisper + MoviePy + Ollama",
    version=APP_VERSION,
    lifespan=lifespan,
)

# CORS (для локальной разработки)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Роутеры API
app.include_router(projects.router)
app.include_router(processing.router)
app.include_router(publishing.router)

# Монтируем статику на префиксы (не на корень — иначе перехватывает API)
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/css", StaticFiles(directory=str(frontend_dir / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(frontend_dir / "js")), name="js")

# Отдача обработанных видео
output_dir = Path(__file__).resolve().parent / "output"
if output_dir.exists():
    app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")

# Корневой путь — index.html
from fastapi.responses import FileResponse

@app.get("/")
async def root():
    index_path = frontend_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Shorts Clipper API"}


@app.get("/api/health")
async def health():
    """Проверка работоспособности."""
    from backend.config import APP_VERSION
    return {"status": "ok", "version": APP_VERSION}


@app.get("/api/check-update")
async def check_update():
    """Проверить наличие обновлений на GitHub."""
    from backend.services.updater import check_update as _check
    return _check()


@app.post("/api/do-update")
async def do_update():
    """Выполнить обновление (git pull)."""
    from backend.services.updater import do_update as _do
    return _do()


@app.get("/api/ollama-status")
async def ollama_status():
    """Проверить статус Ollama."""
    from backend.services.ollama_check import check_ollama
    return check_ollama()


@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Статус фоновой задачи (транскрибация, обработка, публикация)."""
    task = task_manager.get(task_id)
    if not task:
        return {"error": "Задача не найдена"}
    return {
        "task_id": task.id,
        "type": task.type,
        "project_id": task.project_id,
        "status": task.status,
        "progress": task.progress,
        "message": task.message,
        "result": task.result,
        "error": task.error,
    }
