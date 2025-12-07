from __future__ import annotations

from typing import Literal

from ..types import Chunk
from .lore import lore_search
from .rules import rules_lookup


async def lore_assert(store, fact: str, *, version_id: str | None = None) -> dict[str, object]:
    candidates = await lore_search(store, query=fact, k=3, version_id=version_id)
    rules = await rules_lookup(store, term=fact, k=3, version_id=version_id)
    sources = candidates + rules
    if sources:
        return {"result": "unknown", "sources": [c.model_dump() for c in sources]}  # type: ignore[return-value]
    return {"result": "unknown", "sources": []}  # type: ignore[return-value]
