"""
Менеджер фоновых задач с отслеживанием прогресса.
Позволяет запускать транскрибацию и видеопроцессинг в потоках,
не блокируя event loop FastAPI.
"""
import threading
import time
import uuid
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional


@dataclass
class TaskInfo:
    id: str
    type: str  # "transcribe" | "process" | "publish"
    project_id: str
    status: str = "pending"  # pending | running | done | error
    progress: int = 0        # 0-100
    message: str = ""
    result: Optional[dict] = None
    error: Optional[str] = None
    started_at: float = 0.0
    finished_at: float = 0.0


class TaskManager:
    """Синглтон — хранит статусы задач в памяти."""

    _instance: Optional["TaskManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "TaskManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._executor = ThreadPoolExecutor(max_workers=2)
                    obj._tasks: dict[str, TaskInfo] = {}
                    obj._lock = threading.Lock()
                    cls._instance = obj
        return cls._instance

    def submit(
        self,
        task_type: str,
        project_id: str,
        fn: Callable[..., dict],
        *args, **kwargs,
    ) -> str:
        """Запускает задачу в потоке. Возвращает task_id."""
        task_id = uuid.uuid4().hex[:10]

        task = TaskInfo(
            id=task_id,
            type=task_type,
            project_id=project_id,
            status="pending",
            message="В очереди...",
        )

        with self._lock:
            self._tasks[task_id] = task

        self._executor.submit(self._run, task, fn, *args, **kwargs)
        return task_id

    def _run(self, task: TaskInfo, fn: Callable, *args, **kwargs):
        """Выполняет задачу в потоке, обновляя прогресс."""
        try:
            with self._lock:
                task.status = "running"
                task.started_at = time.time()
                task.message = "Запущено..."
                task.progress = 0

            # Передаём callback для обновления прогресса
            def progress_cb(pct: int, msg: str = ""):
                with self._lock:
                    task.progress = pct
                    if msg:
                        task.message = msg

            kwargs["_progress_callback"] = progress_cb
            result = fn(*args, **kwargs)

            with self._lock:
                task.status = "done"
                task.progress = 100
                task.message = "Готово"
                task.result = result
                task.finished_at = time.time()

        except Exception as e:
            with self._lock:
                task.status = "error"
                task.error = str(e)
                task.message = f"Ошибка: {e}"
                task.finished_at = time.time()

    def get(self, task_id: str) -> Optional[TaskInfo]:
        with self._lock:
            return self._tasks.get(task_id)

    def list_by_project(self, project_id: str) -> list[TaskInfo]:
        with self._lock:
            return [t for t in self._tasks.values() if t.project_id == project_id]

    def cleanup_old(self, max_age_seconds: float = 3600):
        """Удаляет старые задачи."""
        now = time.time()
        with self._lock:
            stale = [
                tid for tid, t in self._tasks.items()
                if t.status in ("done", "error") and t.finished_at > 0
                and (now - t.finished_at) > max_age_seconds
            ]
            for tid in stale:
                del self._tasks[tid]


# Глобальный синглтон
task_manager = TaskManager()
