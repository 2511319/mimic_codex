"""Построитель контекста генерации на основе Memory37."""

from __future__ import annotations

import logging
from .knowledge import KnowledgeSearchResult, KnowledgeService
from .models import SceneGenerateRequest

logger = logging.getLogger(__name__)


class GenerationContextBuilder:
    """Готовит текстовый knowledge-контекст для профилей генерации."""

    def __init__(self, knowledge: KnowledgeService | None) -> None:
        self._knowledge = knowledge

    async def build_scene_context(
        self,
        payload: SceneGenerateRequest,
        top_k: int = 6,
    ) -> tuple[str, list[KnowledgeSearchResult]]:
        if not self._knowledge or not self._knowledge.available:
            return ("", [])

        query_parts = [
            payload.scene_id or "",
            payload.campaign_id or "",
            payload.party_id or "",
            payload.prompt,
        ]
        query = " ".join(part for part in query_parts if part).strip()

        try:
            results = await self._knowledge.search(query, top_k=top_k)
        except Exception as exc:  # pragma: no cover - защитный fallback
            logger.warning("KnowledgeService search failed: %s", exc)
            return ("", [])

        if not results:
            return ("", [])

        context_lines = ["[KNOWLEDGE]"]
        for item in results:
            context_lines.append(f"- {item.content_snippet}")

        return ("\n".join(context_lines), results)
