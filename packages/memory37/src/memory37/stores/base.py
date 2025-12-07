from __future__ import annotations

from typing import Protocol

from ..types import Chunk, ChunkScore, GraphFact


class VectorStore(Protocol):
    async def upsert(self, *, domain: str, items: list[Chunk]) -> None: ...

    async def search(
        self,
        *,
        domain: str,
        query: str,
        k_vector: int,
        k_keyword: int | None = None,
        filters: dict | None = None,
    ) -> list[ChunkScore]: ...


class GraphStore(Protocol):
    async def upsert_facts(self, facts: list[GraphFact]) -> None: ...

    async def neighbors(self, *, node_id: str, depth: int = 1) -> dict: ...

    async def shortest_path(self, *, src_id: str, dst_id: str, max_depth: int = 4) -> dict | None: ...
