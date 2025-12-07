from __future__ import annotations

from typing import Iterable

from ..embedding import OpenAIEmbeddingProvider, TokenFrequencyEmbeddingProvider


class Embedder:
    """Простой обёртчик над уже существующими провайдерами."""

    def __init__(self, *, use_openai: bool, model: str | None = None) -> None:
        if use_openai:
            self._provider = OpenAIEmbeddingProvider(model=model)
            self._model = model
        else:
            self._provider = TokenFrequencyEmbeddingProvider()
            self._model = None

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        return self._provider.embed(list(texts), model=self._model)
