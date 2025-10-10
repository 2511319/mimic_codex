"""Конфигурации генеративных слоёв."""

from .config import GenerationConfig, PromptProfile
from .loader import load_generation_config

__all__ = ["GenerationConfig", "PromptProfile", "load_generation_config"]
