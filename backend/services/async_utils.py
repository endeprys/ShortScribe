"""
Утилиты для запуска async-кода из синхронных фоновых потоков.
"""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import TypeVar

T = TypeVar("T")


def run_async_in_thread(coro: Coroutine[None, None, T]) -> T:
    """
    Безопасно выполняет coroutine в фоновом потоке без event loop.

    Предпочтительнее asyncio.run() в worker-потоках task_manager:
    явно создаёт и закрывает loop, не конфликтует с loop FastAPI.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)
