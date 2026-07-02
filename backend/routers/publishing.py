"""
Роутер публикации: отправка клипов в YouTube Shorts и VK Клипы.
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_session
from backend.models import Project, Clip, Settings
from backend.schemas import PublishRequest, PublishStatusResponse, TokensUpdate

router = APIRouter(prefix="/api/projects", tags=["publishing"])


async def _get_settings(session: AsyncSession) -> Settings:
    """Получить или создать запись Settings."""
    result = await session.execute(select(Settings).where(Settings.id == 1))
    s = result.scalar_one_or_none()
    if not s:
        s = Settings(id=1)
        session.add(s)
        await session.commit()
    return s


@router.put("/settings/tokens")
async def save_tokens(
    data: TokensUpdate,
    session: AsyncSession = Depends(get_session),
):
    """
    Сохранить токены VK и YouTube.
    """
    s = await _get_settings(session)
    if data.vk_access_token is not None:
        s.vk_access_token = data.vk_access_token
    if data.youtube_client_secret_json is not None:
        s.youtube_client_secret = data.youtube_client_secret_json
    await session.commit()
    return {"ok": True}


@router.post("/{project_id}/publish", response_model=list[PublishStatusResponse])
async def publish_clips(
    project_id: str,
    data: PublishRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Опубликовать выбранные клипы в YouTube и/или VK.
    """
    # Проверяем проект
    result = await session.execute(select(Project).where(Project.id == project_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Проект не найден")

    # Загружаем настройки
    s = await _get_settings(session)

    results: list[PublishStatusResponse] = []

    for clip_id in data.clip_ids:
        clip_result = await session.execute(
            select(Clip).where(Clip.project_id == project_id, Clip.id == clip_id)
        )
        clip = clip_result.scalar_one_or_none()
        if not clip:
            results.append(PublishStatusResponse(
                clip_id=clip_id, platform="all", status="error", error="Клип не найден"
            ))
            continue

        if not clip.output_path:
            results.append(PublishStatusResponse(
                clip_id=clip_id, platform="all", status="error", error="Клип не обработан"
            ))
            continue

        # ── YouTube ──
        if "youtube" in data.platforms:
            if not s.youtube_client_secret:
                results.append(PublishStatusResponse(
                    clip_id=clip_id, platform="youtube", status="error",
                    error="Не настроен YouTube client_secret"
                ))
            else:
                from backend.services.youtube_api import upload_shorts

                yt_result = upload_shorts(
                    video_path=clip.output_path,
                    title=clip.title or "Shorts",
                    description=clip.description or "",
                    client_secret_json=s.youtube_client_secret,
                    privacy=data.privacy,
                )

                if yt_result.success:
                    clip.yt_status = "published"
                    clip.yt_url = yt_result.url
                    results.append(PublishStatusResponse(
                        clip_id=clip_id, platform="youtube", status="published",
                        url=yt_result.url
                    ))
                else:
                    clip.yt_status = "error"
                    results.append(PublishStatusResponse(
                        clip_id=clip_id, platform="youtube", status="error",
                        error=yt_result.error
                    ))

        # ── VK ──
        if "vk" in data.platforms:
            if not s.vk_access_token:
                results.append(PublishStatusResponse(
                    clip_id=clip_id, platform="vk", status="error",
                    error="Не настроен VK Access Token"
                ))
            else:
                from backend.services.vk_api import upload_clip

                vk_result = upload_clip(
                    video_path=clip.output_path,
                    title=clip.title or "Клип",
                    description=clip.description or "",
                    access_token=s.vk_access_token,
                    is_private=(data.privacy != "public"),
                )

                if vk_result.success:
                    clip.vk_status = "published"
                    clip.vk_url = vk_result.url
                    results.append(PublishStatusResponse(
                        clip_id=clip_id, platform="vk", status="published",
                        url=vk_result.url
                    ))
                else:
                    clip.vk_status = "error"
                    results.append(PublishStatusResponse(
                        clip_id=clip_id, platform="vk", status="error",
                        error=vk_result.error
                    ))

        await session.commit()

    return results
