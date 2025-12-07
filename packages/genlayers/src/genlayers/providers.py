"""Провайдеры LLM для пакета genlayers."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Protocol, runtime_checkable

from .exceptions import GenerationError

logger = logging.getLogger(__name__)


@runtime_checkable
class LanguageModelProvider(Protocol):
    """Контракт провайдера генерации текста."""

    def generate(
        self,
        *,
        prompt: str,
        temperature: float,
        max_output_tokens: int,
        schema: dict[str, Any],
        schema_name: str,
    ) -> str:
        """Выполняет генерацию с учётом схемы ответа."""


try:  # pragma: no cover - импорт зависит от окружения
    from openai import OpenAI
except ModuleNotFoundError:  # pragma: no cover - openai не установлен
    OpenAI = None  # type: ignore[assignment]


class OpenAIResponsesProvider(LanguageModelProvider):
    """Провайдер, использующий OpenAI Responses API с JSON Schema."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        client: Any | None = None,
        timeout: float | None = 120.0,
    ) -> None:
        if OpenAI is None:
            raise GenerationError("OpenAI SDK is not installed or misconfigured")
        self._model = model
        self._client = client or OpenAI(api_key=api_key, timeout=timeout)

    def generate(
        self,
        *,
        prompt: str,
        temperature: float,
        max_output_tokens: int,
        schema: dict[str, Any],
        schema_name: str,
    ) -> str:
        logger.info(
            "OpenAI generate model=%s prompt_len=%d max_output_tokens=%d schema=%s",
            self._model,
            len(prompt),
            max_output_tokens,
            schema_name,
        )
        try:
            schema_payload = _normalize_schema(schema)
            response = self._client.responses.create(
                model=self._model,
                input=prompt,
                max_output_tokens=max_output_tokens,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "schema": schema_payload,
                    }
                },
            )
        except Exception as exc:  # pragma: no cover - требует сетевого вызова
            logger.exception("LLM provider failed")
            raise GenerationError("LLM provider failed", cause=exc) from exc

        text = self._extract_text(response)
        if text is None or not text.strip():
            raise GenerationError("OpenAI вернул пустой ответ.")
        return text

    @staticmethod
    def _extract_text(response: Any) -> str | None:
        if hasattr(response, "output_text"):
            return getattr(response, "output_text")  # type: ignore[no-any-return]
        output = getattr(response, "output", None)
        if not output:
            return None
        parts: list[str] = []
        for item in output:
            content = getattr(item, "content", None)
            if not content:
                continue
            for chunk in content:
                text = getattr(chunk, "text", None)
                if text:
                    parts.append(text)
        if parts:
            return "".join(parts)
        return None


def _normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Приводит схему к требованиям Responses API (все поля в required)."""

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            if node.get("type") == "object":
                props = node.get("properties")
                if isinstance(props, dict) and props:
                    node["required"] = list(props.keys())
                    for value in props.values():
                        _walk(value)
            if "items" in node:
                _walk(node["items"])
            for key in ("anyOf", "oneOf", "allOf"):
                if key in node and isinstance(node[key], list):
                    for item in node[key]:
                        _walk(item)
        return node

    return _walk(deepcopy(schema))
