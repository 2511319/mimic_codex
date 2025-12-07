from __future__ import annotations

from typing import Iterable

from ..types import Chunk


def chunk_text(text: str, *, max_chars: int = 2000) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunks.append(text[start:end])
        start = end
    return chunks


def chunk_lore(chunks: Iterable[Chunk], *, max_chars: int = 2000) -> list[Chunk]:
    result: list[Chunk] = []
    for chunk in chunks:
        parts = chunk_text(chunk.text, max_chars=max_chars)
        if len(parts) == 1:
            result.append(chunk)
        else:
            for idx, part in enumerate(parts):
                result.append(
                    Chunk(
                        id=f"{chunk.id}::part{idx}",
                        domain=chunk.domain,
                        text=part,
                        payload=chunk.payload,
                        metadata=chunk.metadata,
                    )
                )
    return result
