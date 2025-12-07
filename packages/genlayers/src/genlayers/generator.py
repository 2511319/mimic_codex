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
        provider: LanguageModelProvider,
        schema_loader: SchemaLoader,
        max_retries: int = 2,
    ) -> None:
        self._config = config
        self._schema_loader = schema_loader
        self._provider = provider
        self._max_retries = max(0, max_retries)

    def generate(self, profile: str, prompt: str) -> dict[str, Any]:
        """Генерирует payload согласно профилю и JSON Schema."""

        try:
            profile_cfg = self._config.require_profile(profile)
        except KeyError as exc:
            raise GenerationError(f"Unknown profile: {profile}", cause=exc) from exc

        schema = self._schema_loader.load_schema(profile_cfg.response_schema)
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            issue = last_error or Exception("previous attempt failed")
            attempt_prompt = prompt if attempt == 0 else self._augment_prompt(prompt, issue)

            try:
                raw = self._provider.generate(
                    prompt=attempt_prompt,
                    temperature=profile_cfg.temperature,
                    max_output_tokens=profile_cfg.max_output_tokens,
                    schema=schema,
                    schema_name=profile_cfg.response_schema.replace(".json", "").replace("-", "_").replace(".", "_"),
                )
            except GenerationError as exc:
                logger.error("Ошибка провайдера на попытке %d: %s", attempt + 1, exc)
                raise GenerationError("Провайдер не смог сгенерировать ответ.", cause=exc) from exc

            try:
                payload = json.loads(raw)
            except Exception as exc:
                last_error = exc
                logger.warning("Ответ LLM не является валидным JSON (attempt=%d): %s", attempt + 1, exc)
                continue

            try:
                jsonschema.validate(instance=payload, schema=schema)
                return payload
            except jsonschema.ValidationError as exc:
                last_error = exc
                logger.warning("Ответ не прошёл JSON Schema validation (attempt=%d): %s", attempt + 1, exc)
                continue

        if last_error:
            raise GenerationError("Не удалось получить валидный JSON после повторных попыток.", cause=last_error)
        raise GenerationError("Не удалось получить валидный JSON после повторных попыток.")

    @staticmethod
    def _augment_prompt(prompt: str, issue: Exception) -> str:
        hint = (
            "Ответ должен строго соответствовать JSON Schema. "
            "Используй только корректный JSON без дополнительных пояснений. "
            f"Ошибка предыдущей попытки: {issue}."
        )
        return f"{prompt}\n\n{hint}"
