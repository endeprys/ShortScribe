"""
Проверка и авто-настройка Ollama при старте приложения.
"""
import httpx
import subprocess
import sys
import os
from backend.config import WHISPER_MODEL

OLLAMA_URL = "http://127.0.0.1:11434"
REQUIRED_MODELS = [
    WHISPER_MODEL,         # faster-whisper (не через Ollama, но для справки)
    "qwen2.5:7b",          # для генерации названий
]


def check_ollama() -> dict:
    """
    Проверяет доступность Ollama и наличие нужных моделей.
    Возвращает: {"ok": bool, "running": bool, "missing_models": [...], "error": str}
    """
    result = {"ok": False, "running": False, "missing_models": [], "error": ""}

    # 1. Проверяем, запущен ли Ollama
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        if resp.status_code != 200:
            result["error"] = f"Ollama отвечает с кодом {resp.status_code}"
            return result
    except httpx.ConnectError:
        result["error"] = ("Ollama не запущен.\n\n"
                          "Установите Ollama: https://ollama.com/download\n"
                          "Затем запустите: ollama serve")
        return result
    except Exception as e:
        result["error"] = f"Ошибка подключения к Ollama: {e}"
        return result

    result["running"] = True

    # 2. Проверяем наличие нужных моделей
    try:
        data = resp.json()
        installed = {m["name"].split(":")[0] for m in data.get("models", [])}

        for model in REQUIRED_MODELS:
            base = model.split(":")[0]
            if base not in installed:
                result["missing_models"].append(model)
    except Exception:
        pass

    result["ok"] = len(result["missing_models"]) == 0
    return result


def auto_pull_models() -> bool:
    """
    Автоматически скачивает недостающие модели Ollama.
    Возвращает True если все модели установлены.
    """
    status = check_ollama()
    if not status["running"]:
        print(f"[ShortScribe] {status['error']}")
        return False

    for model in status["missing_models"]:
        print(f"[ShortScribe] Устанавливаю модель Ollama: {model}...")
        try:
            subprocess.run(
                ["ollama", "pull", model],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"[ShortScribe] Модель {model} установлена.")
        except subprocess.CalledProcessError:
            print(f"[ShortScribe] ⚠ Не удалось установить {model}. Установите вручную: ollama pull {model}")
            return False

    return True
