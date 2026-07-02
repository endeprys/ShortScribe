"""
VK API — загрузка видео в Клипы (VK Clips).
Требует Access Token с правами video, wall, offline.
"""
import os
from typing import Optional
from dataclasses import dataclass

import httpx

from backend.config import VK_API_VERSION


VK_API_URL = "https://api.vk.com/method/"


@dataclass
class PublishResult:
    success: bool
    video_id: Optional[int] = None
    url: Optional[str] = None
    error: Optional[str] = None


def upload_clip(
    video_path: str,
    title: str,
    description: str,
    access_token: str,
    is_private: bool = False,
) -> PublishResult:
    """
    Загружает вертикальное видео в VK Клипы.

    Алгоритм:
    1. video.save — получить URL для загрузки.
    2. Загрузить файл на полученный URL.
    3. Опубликовать на стене (wall.post с attachment).

    Args:
        video_path: путь к готовому MP4.
        title: название клипа.
        description: описание.
        access_token: VK Access Token.
        is_private: True — загрузить приватно.

    Returns:
        PublishResult с video_id (owner_id_video_id) и url.
    """
    try:
        # Шаг 1: Получаем URL для загрузки
        save_resp = _vk_call(
            "video.save",
            access_token,
            name=title[:255],
            description=description[:2048],
            is_private=1 if is_private else 0,
        )

        if "error" in save_resp:
            return PublishResult(
                success=False,
                error=f"VK video.save: {save_resp['error'].get('error_msg', 'неизвестная ошибка')}",
            )

        upload_url = save_resp["response"].get("upload_url")
        if not upload_url:
            return PublishResult(success=False, error="VK не вернул upload_url")

        # Шаг 2: Загружаем файл
        with open(video_path, "rb") as f:
            files = {"video_file": (os.path.basename(video_path), f, "video/mp4")}
            with httpx.Client(timeout=600.0) as client:
                upload_resp = client.post(upload_url, files=files)
                upload_resp.raise_for_status()
                upload_data = upload_resp.json()

        if "error" in upload_data:
            return PublishResult(
                success=False,
                error=f"VK upload: {upload_data['error'].get('error_msg', 'ошибка загрузки')}",
            )

        # Шаг 3: Получаем owner_id и video_id
        owner_id = upload_data.get("owner_id", save_resp["response"].get("owner_id"))
        video_id = upload_data.get("video_id", save_resp["response"].get("video_id"))

        if not video_id:
            return PublishResult(success=False, error="VK не вернул video_id после загрузки")

        full_id = f"{owner_id}_{video_id}"
        url = f"https://vk.com/clip{full_id}"

        # Шаг 4: Публикуем на стене (если не приватно)
        if not is_private:
            _vk_call(
                "wall.post",
                access_token,
                message=f"{title}\n\n{description}",
                attachments=f"video{full_id}",
            )

        return PublishResult(success=True, video_id=full_id, url=url)

    except Exception as e:
        return PublishResult(success=False, error=str(e))


def _vk_call(method: str, access_token: str, **params) -> dict:
    """Вызов метода VK API."""
    all_params = {
        "v": VK_API_VERSION,
        "access_token": access_token,
        **params,
    }

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(f"{VK_API_URL}{method}", data=all_params)
        resp.raise_for_status()
        return resp.json()
