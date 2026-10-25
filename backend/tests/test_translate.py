import json

import httpx
import pytest

from app.services.subtitles import SubtitleSegment
from app.services.translate import TranslationError, translate_segments

SEGMENTS = [
    SubtitleSegment(0.0, 1.5, "你好"),
    SubtitleSegment(1.5, 3.0, "世界"),
]


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _deepseek_reply(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": content}}]},
    )


def test_translate_preserves_timings_and_returns_mapped_text() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["payload"] = json.loads(request.content)
        return _deepseek_reply(
            json.dumps(
                {
                    "segments": [
                        {"id": 0, "text": "Xin chào"},
                        {"id": 1, "text": "Thế giới"},
                    ]
                },
                ensure_ascii=False,
            )
        )

    with _client(handler) as client:
        result = translate_segments(
            SEGMENTS,
            "vi",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            client=client,
        )

    assert result == [
        SubtitleSegment(0.0, 1.5, "Xin chào"),
        SubtitleSegment(1.5, 3.0, "Thế giới"),
    ]
    assert seen["url"] == "https://api.deepseek.com/chat/completions"
    assert seen["auth"] == "Bearer sk-test"
    payload = seen["payload"]
    assert payload["model"] == "deepseek-chat"
    assert payload["response_format"] == {"type": "json_object"}
    user = json.loads(payload["messages"][1]["content"])
    assert user["target_language"] == "vi"
    assert user["segments"] == [
        {"id": 0, "text": "你好"},
        {"id": 1, "text": "世界"},
    ]


def test_translate_accepts_json_inside_a_code_fence() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _deepseek_reply(
            '```json\n{"segments": [{"id": 0, "text": "A"}, '
            '{"id": 1, "text": "B"}]}\n```'
        )

    with _client(handler) as client:
        result = translate_segments(
            SEGMENTS,
            "vi",
            api_key="k",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            client=client,
        )
    assert [segment.text for segment in result] == ["A", "B"]


def test_translate_returns_empty_without_calling_the_api() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("API must not be called for empty segments")

    with _client(handler) as client:
        assert (
            translate_segments(
                [],
                "vi",
                api_key="k",
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
                client=client,
            )
            == []
        )


def test_translate_requires_an_api_key() -> None:
    with pytest.raises(TranslationError, match="DEEPSEEK_API_KEY"):
        translate_segments(
            SEGMENTS,
            "vi",
            api_key="",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
        )


def test_translate_reports_api_errors_with_status_and_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text='{"error":"invalid key"}')

    with _client(handler) as client, pytest.raises(TranslationError) as error:
        translate_segments(
            SEGMENTS,
            "vi",
            api_key="bad",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            client=client,
        )
    assert "401" in str(error.value)
    assert "invalid key" in str(error.value)


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        json.dumps({"segments": [{"id": 0, "text": "only one"}]}),
        json.dumps(
            {
                "segments": [
                    {"id": 0, "text": "a"},
                    {"id": 0, "text": "b"},
                ]
            }
        ),
        json.dumps(
            {
                "segments": [
                    {"id": 0, "text": "a"},
                    {"id": 1, "text": "   "},
                ]
            }
        ),
        json.dumps({"segments": [{"id": 0, "text": "a"}, {"id": 2, "text": "b"}]}),
    ],
)
def test_translate_rejects_bad_model_output(content: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _deepseek_reply(content)

    with _client(handler) as client, pytest.raises(TranslationError):
        translate_segments(
            SEGMENTS,
            "vi",
            api_key="k",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            client=client,
        )


def test_translate_wraps_network_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with _client(handler) as client, pytest.raises(TranslationError, match="DeepSeek"):
        translate_segments(
            SEGMENTS,
            "vi",
            api_key="k",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            client=client,
        )
