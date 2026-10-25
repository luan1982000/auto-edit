"""Subtitle translation through DeepSeek's OpenAI-compatible chat API."""

from __future__ import annotations

import json
import re

import httpx

from app.services.subtitles import SubtitleSegment

SYSTEM_PROMPT = (
    "You are a professional subtitle translator. Translate every subtitle "
    "segment into the requested target language. Keep the meaning natural and "
    "concise, suitable for reading on screen. Never merge, split, reorder, add "
    "or drop segments. Do not output timestamps. Reply with JSON only, in the "
    'form {"segments": [{"id": <int>, "text": "<translated text>"}]}. '
    "Every input id must appear exactly once."
)

_CODE_FENCE = re.compile(r"\A\s*```(?:json)?\s*(.*?)\s*```\s*\Z", re.DOTALL)


class TranslationError(RuntimeError):
    """Raised when DeepSeek cannot translate the subtitles."""


def _extract_content(body: str) -> str:
    data = json.loads(body)
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise TranslationError("DeepSeek trả về dữ liệu không hợp lệ (thiếu choices)")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise TranslationError("DeepSeek trả về nội dung rỗng")
    return content


def _parse_translation(content: str, expected_count: int) -> list[str]:
    fenced = _CODE_FENCE.match(content)
    if fenced:
        content = fenced.group(1)
    try:
        data = json.loads(content)
    except ValueError as exc:
        raise TranslationError(f"Không đọc được JSON dịch từ DeepSeek: {exc}") from exc
    raw_segments = data.get("segments") if isinstance(data, dict) else None
    if not isinstance(raw_segments, list):
        raise TranslationError("DeepSeek không trả về danh sách segments")

    translated: dict[int, str] = {}
    for item in raw_segments:
        if not isinstance(item, dict):
            raise TranslationError("DeepSeek trả về segment không hợp lệ")
        try:
            segment_id = int(item["id"])
            text = str(item["text"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TranslationError("DeepSeek trả về segment không hợp lệ") from exc
        text = " ".join(text.split())
        if segment_id in translated:
            raise TranslationError(f"DeepSeek trả về trùng id {segment_id}")
        if not text:
            raise TranslationError(f"DeepSeek trả về bản dịch rỗng cho id {segment_id}")
        translated[segment_id] = text

    expected_ids = set(range(expected_count))
    if set(translated) != expected_ids:
        raise TranslationError(
            "DeepSeek trả về thiếu hoặc thừa segment "
            f"(cần {expected_count}, nhận {len(translated)})"
        )
    return [translated[index] for index in range(expected_count)]


def translate_segments(
    segments: list[SubtitleSegment],
    target_language: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
    client: httpx.Client | None = None,
    timeout: float = 120.0,
) -> list[SubtitleSegment]:
    if not segments:
        return []
    if not api_key.strip():
        raise TranslationError(
            "Chưa cấu hình DEEPSEEK_API_KEY trong .env — không thể dịch phụ đề"
        )

    payload = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 8000,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "target_language": target_language,
                        "segments": [
                            {"id": index, "text": segment.text}
                            for index, segment in enumerate(segments)
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }

    owns_client = client is None
    http = client or httpx.Client(timeout=timeout)
    try:
        try:
            response = http.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise TranslationError(f"Không gọi được DeepSeek API: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text.strip()[:500]
            raise TranslationError(
                f"DeepSeek API lỗi {response.status_code}: {detail}"
            )
        try:
            content = _extract_content(response.text)
        except ValueError as exc:
            raise TranslationError(f"DeepSeek trả về JSON không hợp lệ: {exc}") from exc
    finally:
        if owns_client:
            http.close()

    texts = _parse_translation(content, len(segments))
    return [
        SubtitleSegment(start=segment.start, end=segment.end, text=text)
        for segment, text in zip(segments, texts, strict=True)
    ]
