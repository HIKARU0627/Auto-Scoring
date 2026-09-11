"""Tests for provider usage parsing (Issue #187)."""

from auto_scoring.adapters.ai_grading._usage import parse_gemini_usage, parse_openai_chat_usage


def test_openai_chat_usage_parses_prompt_and_completion() -> None:
    usage = parse_openai_chat_usage(
        {"usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}}
    )
    assert usage is not None
    assert usage.input_tokens == 120
    assert usage.output_tokens == 30


def test_openai_chat_usage_missing_returns_none_not_zero() -> None:
    assert parse_openai_chat_usage({}) is None


def test_gemini_usage_parses_metadata() -> None:
    usage = parse_gemini_usage(
        {
            "usageMetadata": {
                "promptTokenCount": 80,
                "candidatesTokenCount": 20,
                "totalTokenCount": 100,
            }
        }
    )
    assert usage is not None
    assert usage.input_tokens == 80
    assert usage.output_tokens == 20
