"""Провайдеры LLM для пакета genlayers."""

from __future__ import annotations

import logging
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
    from openai.error import OpenAIError
except ModuleNotFoundError:  # pragma: no cover - openai не установлен
    OpenAI = None  # type: ignore[assignment]
    OpenAIError = Exception  # type: ignore[assignment]


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
            raise GenerationError("OpenAI SDK недоступен. Установите пакет 'openai'.")
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
        try:
            response = self._client.responses.create(
                model=self._model,
                input=prompt,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "schema": schema},
                },
            )
        except OpenAIError as exc:  # pragma: no cover - требует сетевого вызова
            logger.exception("OpenAI generation failed")
            raise GenerationError("Не удалось получить ответ от OpenAI.", cause=exc) from exc

        text = self._extract_text(response)
        if text is None:
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
