"""Движок структурированной генерации поверх LLM-провайдера."""

from __future__ import annotations

import json
import logging
from typing import Any

import jsonschema

from .config import GenerationConfig
from .exceptions import GenerationError
from .providers import LanguageModelProvider
from .schema_loader import SchemaLoader

logger = logging.getLogger(__name__)


class StructuredGenerationEngine:
    """Оркестратор запросов к LLM с JSON Schema-валидацией и ретраями."""

    def __init__(
        self,
        *,
        config: GenerationConfig,
        schema_loader: SchemaLoader,
        provider: LanguageModelProvider,
        max_retries: int = 2,
    ) -> None:
        self._config = config
        self._schema_loader = schema_loader
        self._provider = provider
        self._max_retries = max(0, max_retries)

    def generate(self, profile_name: str, prompt: str) -> dict[str, Any]:
        """Выполняет генерацию и гарантирует соответствие JSON Schema.

        Args:
            profile_name: Имя профиля из конфигурации.
            prompt: Исходный промпт.

        Returns:
            dict[str, Any]: Десериализованный валидный ответ.

        Raises:
            GenerationError: Если провайдер не вернул корректный ответ.
        """

        profile = self._config.require_profile(profile_name)
        schema = self._schema_loader.load(profile.response_schema)

        attempt_prompt = prompt
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                raw = self._provider.generate(
                    prompt=attempt_prompt,
                    temperature=profile.temperature,
                    max_output_tokens=profile.max_output_tokens,
                    schema=schema,
                    schema_name=profile.response_schema.replace(".json", "").replace("-", "_"),
                )
            except GenerationError as exc:
                logger.error("Ошибка провайдера на попытке %d: %s", attempt + 1, exc)
                raise GenerationError("Провайдер не смог сгенерировать ответ.", cause=exc) from exc

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                last_error = exc
                logger.warning(
                    "Попытка %d: ответ не является JSON (%s). Повтор запроса.",
                    attempt + 1,
                    exc,
                )
                attempt_prompt = self._augment_prompt(prompt, exc)
                continue

            try:
                jsonschema.validate(instance=payload, schema=schema)
                return payload
            except jsonschema.ValidationError as exc:
                last_error = exc
                logger.warning(
                    "Попытка %d: ответ не прошёл валидацию JSON Schema (%s).",
                    attempt + 1,
                    exc.message,
                )
                attempt_prompt = self._augment_prompt(prompt, exc)
                continue

        raise GenerationError(
            "Не удалось получить валидный JSON после повторных попыток.",
            cause=last_error,
        )

    @staticmethod
    def _augment_prompt(prompt: str, issue: Exception) -> str:
        hint = (
            "Ответ должен строго соответствовать JSON Schema. "
            "Используй только корректный JSON без дополнительных пояснений. "
            f"Ошибка предыдущей попытки: {issue}."
        )
        return f"{prompt}\n\n{hint}"
