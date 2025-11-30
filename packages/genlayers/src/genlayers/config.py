from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


class PromptProfile(BaseModel):
    """Параметры конкретного профиля генерации."""

    temperature: Annotated[float, Field(ge=0.0, le=2.0)]
    max_output_tokens: Annotated[int, Field(ge=64, le=1024)]
    response_schema: str


class GenerationConfig(BaseModel):
    """Корневая конфигурация генеративных профилей."""

    profiles: dict[str, PromptProfile]

    def require_profile(self, name: str) -> PromptProfile:
        try:
            return self.profiles[name]
        except KeyError as exc:
            raise KeyError(f"Prompt profile '{name}' is not defined") from exc
