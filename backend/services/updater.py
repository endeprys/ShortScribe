"""
Автообновление: проверка новых версий на GitHub и бесшовное обновление через git pull.
"""
import httpx
import subprocess
import sys
import os
from pathlib import Path
from backend.config import APP_VERSION

# ⚠ Замените на свой репозиторий перед пушем:
GITHUB_REPO = "username/ShortScribe"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES = f"https://github.com/{GITHUB_REPO}/releases"


def check_update() -> dict:
    """
    Проверяет наличие новой версии на GitHub.
    Возвращает: {"update_available": bool, "latest": str, "current": str, "url": str, "notes": str}
    """
    result = {
        "update_available": False,
        "latest": APP_VERSION,
        "current": APP_VERSION,
        "url": "",
        "notes": "",
    }

    try:
        resp = httpx.get(GITHUB_API, timeout=10.0, headers={"Accept": "application/vnd.github+json"})
        if resp.status_code != 200:
            return result

        data = resp.json()
        latest = data.get("tag_name", "").lstrip("v")
        if not latest:
            return result

        result["latest"] = latest
        result["url"] = data.get("html_url", GITHUB_RELEASES)
        result["notes"] = data.get("body", "")[:500]

        if _version_newer(latest, APP_VERSION):
            result["update_available"] = True

    except Exception:
        pass

    return result


def do_update() -> dict:
    """
    Выполняет git pull для обновления. Требует git и настроенный remote.
    Возвращает: {"ok": bool, "message": str}
    """
    try:
        # Проверяем, что мы в git-репозитории
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return {"ok": False, "message": "Не git-репозиторий. Обновление возможно только через git clone."}

        # Pull
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            capture_output=True, text=True, timeout=30,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
        )
        if result.returncode == 0:
            return {"ok": True, "message": "Обновление выполнено. Перезапустите приложение."}
        else:
            return {"ok": False, "message": f"Ошибка git pull: {result.stderr.strip()}"}

    except FileNotFoundError:
        return {"ok": False, "message": "Git не найден. Установите git: https://git-scm.com"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


def _version_newer(latest: str, current: str) -> bool:
    """Сравнивает семантические версии. Возвращает True если latest > current."""
    try:
        def parse(v):
            return tuple(int(x) for x in v.split("."))
        return parse(latest) > parse(current)
    except Exception:
        return latest != current
