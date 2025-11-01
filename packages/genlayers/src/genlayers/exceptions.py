"""Исключения пакета genlayers."""

from __future__ import annotations


class GenerationError(RuntimeError):
    """Ошибка генерации структурированного ответа."""

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        if cause is not None:
            self.__cause__ = cause
