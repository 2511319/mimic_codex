"""Типы конфигурации для системы памяти «Память37»."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class EmbeddingConfig(BaseModel):
    """Настройки модели эмбеддингов."""

    provider: Literal["openai"]
    model: str
    dimensions: Annotated[int, Field(ge=256, le=3072)]


class RetrievalConfig(BaseModel):
    """Настройки ретрива документов."""

    mode: Literal["vector", "hybrid"]
    k_vector: Annotated[int, Field(ge=1, le=32)]
    k_keyword: Annotated[int | None, Field(ge=1, le=200)] = None
    fuse: Literal["rrf"] | None = None
    filters: dict[str, str] | None = None

    @model_validator(mode="after")
    def validate_rrf(self) -> "RetrievalConfig":
        if self.mode == "hybrid" and self.k_keyword is None:
            raise ValueError("k_keyword is required for hybrid retrieval mode")
        if self.mode == "vector" and self.k_keyword is not None:
            raise ValueError("k_keyword must be omitted for vector mode")
        if self.mode == "vector" and self.fuse is not None:
            raise ValueError("fuse is allowed only for hybrid mode")
        return self


class KnowledgeDomainConfig(BaseModel):
    """Конфигурация одного домена знаний (SRD, лор, эпизоды)."""

    store: Literal["pgvector"]
    embedding: EmbeddingConfig
    retrieval: RetrievalConfig


class KnowledgeConfig(BaseModel):
    """Корневая конфигурация всех доменов знаний."""

    knowledge: dict[str, KnowledgeDomainConfig]

    def require_domain(self, name: str) -> KnowledgeDomainConfig:
        try:
            return self.knowledge[name]
        except KeyError as exc:
            raise KeyError(f"Knowledge domain '{name}' is not configured") from exc
