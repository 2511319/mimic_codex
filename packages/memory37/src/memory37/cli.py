"""Typer-based CLI for Memory37 ingestion workflows."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

import typer

try:  # pragma: no cover - optional
    import psycopg  # type: ignore
except Exception:  # pragma: no cover
    psycopg = None  # type: ignore[assignment]

from .domain import ArtCard, KnowledgeItem, NpcProfile, SceneState
from .embedding import OpenAIEmbeddingProvider, TokenFrequencyEmbeddingProvider
from .ingest import build_runtime_items, load_knowledge_items_from_yaml
from .stores.pgvector_store import InMemoryVectorStore, PgVectorWrapper
from .types import Chunk

app = typer.Typer(help="Memory37 CLI")


def _provider_from_flags(use_openai: bool, openai_model: Optional[str]) -> TokenFrequencyEmbeddingProvider | OpenAIEmbeddingProvider:
    if use_openai:
        return OpenAIEmbeddingProvider(model=openai_model)
    return TokenFrequencyEmbeddingProvider()


def _build_store(
    *,
    dsn: Optional[str],
    table: str,
    dimension: int,
    dry_run: bool,
    provider,
    embedding_model: Optional[str],
):
    if dry_run or not dsn or psycopg is None:
        if dsn and psycopg is None and not dry_run:
            typer.echo("psycopg не установлен, используем in-memory store")
        return InMemoryVectorStore(embedding_provider=provider, embedding_model=embedding_model)
    return PgVectorWrapper(lambda: psycopg.connect(dsn), table=table, dimension=dimension, embedding_provider=provider, embedding_model=embedding_model)


async def _ingest_items(store, items: list[KnowledgeItem]) -> None:
    batches: dict[str, list[Chunk]] = {}
    for item in items:
        metadata = dict(item.metadata)
        if item.knowledge_version_id:
            metadata["knowledge_version_id"] = item.knowledge_version_id
        if item.expires_at:
            metadata["expires_at"] = item.expires_at.isoformat()
        chunk = Chunk(id=item.item_id, domain=item.domain, text=item.content, payload={}, metadata=metadata)
        batches.setdefault(item.domain, []).append(chunk)
    for domain, chunks in batches.items():
        if not chunks:
            continue
        await store.upsert(domain=domain, items=chunks)


async def _search(store, query: str, top_k: int, *, version_id: Optional[str]) -> list[tuple[str, float, str]]:
    domains = ["scene", "npc", "lore", "srd", "art"]
    results = []
    filters = {"knowledge_version_id": version_id} if version_id else {}
    for domain in domains:
        try:
            scores = await store.search(domain=domain, query=query, k_vector=top_k, filters=filters)
            for score in scores:
                snippet = score.chunk.text[:160].replace("\n", " ")
                results.append((score.chunk.id, score.score, snippet))
        except Exception:
            continue
    results.sort(key=lambda r: r[1], reverse=True)
    return results[:top_k]


@app.command()
def ingest_file(
    path: Path,
    dsn: Optional[str] = typer.Option(None, "--dsn", envvar="MEMORY37_DATABASE_URL", help="PostgreSQL DSN"),
    table: str = typer.Option("memory37_vectors", help="Target table for pgvector store"),
    dimension: int = typer.Option(1536, help="Vector dimension"),
    dry_run: bool = typer.Option(False, help="Use in-memory store instead of database"),
    use_openai: bool = typer.Option(False, "--use-openai", help="Use OpenAI embeddings"),
    openai_embedding_model: Optional[str] = typer.Option(None, help="Override OpenAI embedding model"),
    knowledge_version_id: Optional[str] = typer.Option(None, "--knowledge-version-id", help="Knowledge version id for ingested items"),
) -> None:
    """Load knowledge items from YAML file and ingest into vector store."""

    items = load_knowledge_items_from_yaml(path, knowledge_version_id=knowledge_version_id)
    provider = _provider_from_flags(use_openai or bool(os.environ.get("OPENAI_API_KEY")), openai_embedding_model)
    embedding_model = openai_embedding_model if isinstance(provider, OpenAIEmbeddingProvider) else None

    store = _build_store(dsn=dsn, table=table, dimension=dimension, dry_run=dry_run, provider=provider, embedding_model=embedding_model)
    if dry_run:
        typer.echo("Running in dry-run mode (memory store).")
    asyncio.run(_ingest_items(store, items))
    typer.echo(f"Ingested {len(items)} knowledge items.")


@app.command()
def ingest_runtime_snapshot(
    scenes_file: Optional[Path] = typer.Option(None, help="Path to YAML file with scenes"),
    npcs_file: Optional[Path] = typer.Option(None, help="Path to YAML file with NPCs"),
    art_file: Optional[Path] = typer.Option(None, help="Path to YAML file with art cards"),
    dsn: Optional[str] = typer.Option(None, envvar="MEMORY37_DATABASE_URL"),
    table: str = typer.Option("memory37_vectors"),
    dimension: int = typer.Option(1536),
    dry_run: bool = typer.Option(True, help="Default to dry run for runtime snapshots"),
    use_openai: bool = typer.Option(False, "--use-openai", help="Use OpenAI embeddings"),
    openai_embedding_model: Optional[str] = typer.Option(None, help="Override OpenAI embedding model"),
) -> None:
    """Load runtime snapshots (scenes/npcs/art) and ingest."""

    from yaml import safe_load

    def load_optional(path: Optional[Path]):
        if not path:
            return []
        data = safe_load(path.read_text(encoding="utf-8"))
        return data or []

    scenes_data = load_optional(scenes_file)
    npcs_data = load_optional(npcs_file)
    art_data = load_optional(art_file)

    scenes = [SceneState.model_validate(scene) for scene in scenes_data]
    npcs = [NpcProfile.model_validate(npc) for npc in npcs_data]
    art_cards = [ArtCard.model_validate(card) for card in art_data]

    items = build_runtime_items(scenes=scenes, npcs=npcs, art_cards=art_cards)

    provider = _provider_from_flags(use_openai or bool(os.environ.get("OPENAI_API_KEY")), openai_embedding_model)
    embedding_model = openai_embedding_model if isinstance(provider, OpenAIEmbeddingProvider) else None
    store = _build_store(dsn=dsn, table=table, dimension=dimension, dry_run=dry_run, provider=provider, embedding_model=embedding_model)
    if dry_run:
        typer.echo("Running in dry-run mode (memory store).")
    asyncio.run(_ingest_items(store, items))
    typer.echo(f"Ingested {len(items)} runtime items.")


@app.command()
def search(
    query: str,
    top_k: int = typer.Option(5, help="Number of results to display"),
    knowledge_file: Optional[Path] = typer.Option(None, help="YAML file to load knowledge items from"),
    dsn: Optional[str] = typer.Option(None, "--dsn", envvar="MEMORY37_DATABASE_URL", help="PostgreSQL DSN"),
    table: str = typer.Option("memory37_vectors"),
    dimension: int = typer.Option(1536),
    dry_run: bool = typer.Option(False, help="Use in-memory store even if DSN provided"),
    use_openai: bool = typer.Option(False, "--use-openai", help="Use OpenAI embeddings"),
    openai_embedding_model: Optional[str] = typer.Option(None, help="Override OpenAI embedding model"),
    ingest: bool = typer.Option(False, help="Ingest knowledge file before search"),
    knowledge_version_id: Optional[str] = typer.Option(None, "--knowledge-version-id", help="Knowledge version id for ingested items"),
) -> None:
    """Query knowledge store and display top matching items."""

    provider = _provider_from_flags(use_openai or bool(os.environ.get("OPENAI_API_KEY")), openai_embedding_model)
    embedding_model = openai_embedding_model if isinstance(provider, OpenAIEmbeddingProvider) else None

    store = _build_store(dsn=dsn, table=table, dimension=dimension, dry_run=dry_run, provider=provider, embedding_model=embedding_model)

    if knowledge_file:
        items = load_knowledge_items_from_yaml(knowledge_file, knowledge_version_id=knowledge_version_id)
        if isinstance(store, InMemoryVectorStore) or ingest or dry_run:
            asyncio.run(_ingest_items(store, items))
    elif isinstance(store, InMemoryVectorStore):
        raise typer.BadParameter("knowledge-file is required when using in-memory store")

    results = asyncio.run(_search(store, query, top_k, version_id=knowledge_version_id))
    if not results:
        typer.echo("No results")
        raise typer.Exit(code=0)

    for item_id, score, snippet in results:
        typer.echo(f"{item_id}\t{score:.3f}\t{snippet}")


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
