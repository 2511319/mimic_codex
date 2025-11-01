"""LLM-based rerank providers."""

from __future__ import annotations

import json
import os
from typing import Sequence

from .domain import KnowledgeItem
from .retrieval import RerankProvider

try:  # pragma: no cover - optional dependency
    from openai import OpenAI  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore


class OpenAIChatRerankProvider(RerankProvider):
    """Use OpenAI responses API to rerank retrieval results."""

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
        self._model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def rerank(self, query: str, items: Sequence[KnowledgeItem]) -> list[tuple[KnowledgeItem, float]]:
        if not items:
            return []

        payload = {
            "query": query,
            "documents": [
                {
                    "id": str(index),
                    "content": item.content,
                    "metadata": getattr(item, "metadata", {}),
                    "item_id": item.item_id,
                }
                for index, item in enumerate(items)
            ],
        }

        prompt = (
            "You are ranking knowledge items for an RPG assistant. "
            "Return JSON with array 'ranking' of objects {item_id: string, score: number} "
            "sorted by relevance (higher score first). If unsure, output original order."  # noqa: E501
        )

        response = self._client.responses.create(  # type: ignore[attr-defined]
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": prompt,
                },
                {
                    "role": "user",
                    "content": json.dumps(payload),
                },
            ],
            response_format={"type": "json_schema", "json_schema": {
                "name": "ranking",
                "schema": {
                    "type": "object",
                    "properties": {
                        "ranking": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "item_id": {"type": "string"},
                                    "score": {"type": "number"}
                                },
                                "required": ["item_id", "score"],
                            },
                        }
                    },
                    "required": ["ranking"],
                },
            }},
        )

        try:
            content = response.output[0].content[0].text  # type: ignore[attr-defined]
            ranking_payload = json.loads(content)
            ranking = ranking_payload.get("ranking", [])
        except Exception:  # pragma: no cover - fall back to original order
            ranking = []

        score_map = {entry.get("item_id"): entry.get("score", 0.0) for entry in ranking if entry.get("item_id")}
        ordered = [
            (item, float(score_map.get(item.item_id, len(items) - index)))
            for index, item in enumerate(items)
        ]
        ordered.sort(key=lambda entry: entry[1], reverse=True)
        return ordered
