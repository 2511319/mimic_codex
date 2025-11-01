"""Embedding provider implementations used by Memory37 tooling."""

from __future__ import annotations

import os
from math import sqrt
from typing import Sequence

from .vector_store import EmbeddingProvider

try:  # pragma: no cover - optional dependency
    from openai import OpenAI  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore


class TokenFrequencyEmbeddingProvider(EmbeddingProvider):
    """Simple embedding provider based on token frequency (for local use/testing)."""

    def __init__(self, *, vocab_limit: int = 64) -> None:
        self.vocab_limit = vocab_limit

    def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for text in texts:
            tokens = text.lower().split()
            freq: dict[str, int] = {}
            for token in tokens:
                freq[token] = freq.get(token, 0) + 1
            sorted_terms = sorted(freq)[: self.vocab_limit]
            vec = [float(freq[term]) for term in sorted_terms]
            vec.extend([0.0] * (self.vocab_limit - len(vec)))
            norm = sqrt(sum(x * x for x in vec)) or 1.0
            embeddings.append([x / norm for x in vec])
        return embeddings


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Embedding provider backed by OpenAI API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client: object | None = None,
    ) -> None:
        if client is not None:
            self._client = client
        else:
            if OpenAI is None:
                raise RuntimeError("openai package is not installed")
            api_key = api_key or os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY is not configured")
            self._client = OpenAI(api_key=api_key)
        self._model = model or os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")

    def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        target_model = model or self._model
        response = self._client.embeddings.create(model=target_model, input=list(texts))
        vectors: list[list[float]] = []
        for entry in response.data:  # type: ignore[attr-defined]
            vector = getattr(entry, "embedding", None)
            if vector is None:
                raise RuntimeError("OpenAI embedding response missing 'embedding'")
            vectors.append(list(vector))
        return vectors
