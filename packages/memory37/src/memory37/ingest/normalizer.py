from __future__ import annotations

from typing import Iterable

from ..types import Chunk, EpisodicSummary, ArtCard


def normalize_srd(raw: str | dict) -> list[Chunk]:
    if isinstance(raw, str):
        return [Chunk(id="srd::auto", domain="srd", text=raw, payload={}, metadata={})]
    return [
        Chunk(
            id=f"srd::{item.get('id') or idx}",
            domain="srd",
            text=item.get("text", ""),
            payload={},
            metadata=item.get("metadata", {}),
        )
        for idx, item in enumerate(raw or [])
    ]


def normalize_lore(raw: str | dict) -> list[Chunk]:
    if isinstance(raw, str):
        return [Chunk(id="lore::auto", domain="lore", text=raw, payload={}, metadata={})]
    return [
        Chunk(
            id=f"lore::{item.get('id') or idx}",
            domain="lore",
            text=item.get("body") or item.get("text") or "",
            payload={},
            metadata=item.get("metadata", {}),
        )
        for idx, item in enumerate(raw or [])
    ]


def normalize_episode(summary: EpisodicSummary) -> Chunk:
    return Chunk(
        id=f"episode::{summary.summary_id}",
        domain="episode",
        text=summary.notes or "",
        payload={},
        metadata={"party_id": summary.party_id, "campaign_id": summary.campaign_id},
    )


def normalize_art(card: ArtCard) -> Chunk:
    return Chunk(
        id=f"art::{card.image_id}",
        domain="art",
        text=card.prompt_text,
        payload={},
        metadata={"scene_id": card.scene_id, "cdn_url": str(card.cdn_url)},
    )
