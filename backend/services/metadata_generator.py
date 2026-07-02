"""
Генератор названий и описаний для Shorts/Клипов через локальный Ollama.
Использует qwen2.5:7b (быстрая модель для русского языка).
"""
import json
import httpx

OLLAMA_BASE = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:7b"   # быстрый, хороший русский, не-thinking


def generate_metadata(
    transcript_text: str,
    model: str = DEFAULT_MODEL,
    max_title_chars: int = 100,
    max_desc_chars: int = 500,
) -> dict:
    """
    Генерирует название и описание для Shorts/Клипа на основе текста транскрипции.

    Args:
        transcript_text: текст субтитров/транскрипции клипа
        model: имя модели в Ollama (по умолчанию qwen2.5:7b)
        max_title_chars: максимальная длина названия
        max_desc_chars: максимальная длина описания

    Returns:
        {"title": "...", "description": "..."}
    """
    prompt = f"""Сгенерируй название (до {max_title_chars} символов) и краткое описание (2-3 предложения, до {max_desc_chars} символов) для видео-клипа на основе этого текста:

ТЕКСТ:
{transcript_text[:2000]}

Ответ выдай ТОЛЬКО в формате JSON с ключами title и description. Никаких лишних слов.
Пример: {{"title": "Заголовок видео", "description": "Описание видео."}}"""

    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{OLLAMA_BASE}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.7, "max_tokens": 300},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("response", "").strip()

        # Пробуем распарсить JSON из ответа
        return _parse_metadata(raw)

    except httpx.ConnectError:
        return {"title": "", "description": "", "error": "Ollama недоступен. Запустите: ollama serve"}
    except Exception as e:
        return {"title": "", "description": "", "error": str(e)}


def _parse_metadata(raw: str) -> dict:
    """Извлекает title и description из ответа модели."""
    # Ищем JSON-блок
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(raw[start:end + 1])
            title = str(data.get("title", "")).strip()[:100]
            desc = str(data.get("description", "")).strip()[:500]
            return {"title": title, "description": desc}
        except json.JSONDecodeError:
            pass

    # Fallback: если JSON не получился — используем первую строку как название
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    title = ""
    desc = ""

    for line in lines:
        if line.lower().startswith("title:") or line.lower().startswith("название:"):
            title = line.split(":", 1)[-1].strip()[:100]
        elif line.lower().startswith("desc") or line.lower().startswith("описание"):
            desc = line.split(":", 1)[-1].strip()[:500]

    if not title and lines:
        title = lines[0][:100]
    if not desc and len(lines) > 1:
        desc = " ".join(lines[1:])[:500]

    return {"title": title, "description": desc}
