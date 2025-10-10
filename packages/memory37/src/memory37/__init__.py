"""Библиотека конфигураций «Память37»."""

from .config import KnowledgeConfig, KnowledgeDomainConfig, RetrievalConfig
from .loader import load_knowledge_config

__all__ = ["KnowledgeConfig", "KnowledgeDomainConfig", "RetrievalConfig", "load_knowledge_config"]
