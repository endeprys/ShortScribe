"""
YouTube Data API v3 — загрузка Shorts.
Требует client_secret.json от Google Cloud Console.
"""
import json
import os
import tempfile
from typing import Optional
from dataclasses import dataclass

from backend.config import YOUTUBE_CATEGORY_ID, YOUTUBE_SCOPES


@dataclass
class PublishResult:
    success: bool
    video_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


def upload_shorts(
    video_path: str,
    title: str,
    description: str,
    client_secret_json: str,
    privacy: str = "private",
) -> PublishResult:
    """
    Загружает вертикальное видео как YouTube Shorts.

    Args:
        video_path: путь к готовому MP4-файлу.
        title: название видео (автоматически добавляется #shorts).
        description: описание (автоматически добавляется #shorts).
        client_secret_json: содержимое client_secret.json (строка JSON).
        privacy: public | private | unlisted.

    Returns:
        PublishResult с video_id и url при успехе.
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        return PublishResult(
            success=False,
            error="Установите зависимости: pip install google-api-python-client google-auth-oauthlib",
        )

    # Сохраняем client_secret во временный файл
    fd, secret_path = tempfile.mkstemp(suffix=".json", prefix="yt_secret_")
    with os.fdopen(fd, "w") as f:
        f.write(client_secret_json)

    try:
        # OAuth2 flow
        flow = InstalledAppFlow.from_client_secrets_file(secret_path, YOUTUBE_SCOPES)
        credentials = flow.run_local_server(
            port=0,
            open_browser=False,
            authorization_prompt_message="Перейдите по ссылке для авторизации YouTube:",
        )

        youtube = build("youtube", "v3", credentials=credentials)

        # Добавляем #shorts в название и описание
        if "#shorts" not in title.lower():
            title = f"{title} #shorts"
        if "#shorts" not in description.lower():
            description = f"{description}\n\n#shorts"

        body = {
            "snippet": {
                "title": title[:100],  # YouTube лимит — 100 символов
                "description": description[:5000],
                "categoryId": YOUTUBE_CATEGORY_ID,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=256 * 1024,
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()

        video_id = response["id"]
        url = f"https://youtube.com/shorts/{video_id}"

        return PublishResult(success=True, video_id=video_id, url=url)

    except Exception as e:
        return PublishResult(success=False, error=str(e))

    finally:
        _safe_remove(secret_path)


def _safe_remove(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
