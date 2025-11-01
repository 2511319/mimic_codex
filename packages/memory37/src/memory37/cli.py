"""Typer-based CLI for Memory37 ingestion workflows."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import psycopg
import typer

from .domain import ArtCard, NpcProfile, SceneState
from .embedding import OpenAIEmbeddingProvider, TokenFrequencyEmbeddingProvider
from .etl import ETLPipeline
from .ingest import build_runtime_items, load_knowledge_items_from_yaml
from .retrieval import HybridRetriever
from .rerankers import OpenAIChatRerankProvider
from .vector_store import MemoryVectorStore, PgVectorStore

app = typer.Typer(help="Memory37 CLI")


def _provider_from_flags(use_openai: bool, openai_model: Optional[str]) -> TokenFrequencyEmbeddingProvider | OpenAIEmbeddingProvider:

    if use_openai:
        return OpenAIEmbeddingProvider(model=openai_model)
    return TokenFrequencyEmbeddingProvider()


@app.command()
def ingest_file(
    path: Path,
    dsn: Optional[str] = typer.Option(None, "--dsn", envvar="MEMORY37_DATABASE_URL", help="PostgreSQL DSN"),
    table: str = typer.Option("memory37_vectors", help="Target table for pgvector store"),
    dimension: int = typer.Option(1536, help="Vector dimension"),
    dry_run: bool = typer.Option(False, help="Use in-memory store instead of database"),
    use_openai: bool = typer.Option(False, "--use-openai", help="Use OpenAI embeddings"),
    openai_embedding_model: Optional[str] = typer.Option(None, help="Override OpenAI embedding model"),
) -> None:
    """Load knowledge items from YAML file and ingest into vector store."""

    items = load_knowledge_items_from_yaml(path)
    provider = _provider_from_flags(use_openai or bool(os.environ.get("OPENAI_API_KEY")), openai_embedding_model)
    embedding_model = openai_embedding_model if isinstance(provider, OpenAIEmbeddingProvider) else None

    if dry_run or not dsn:
        store = MemoryVectorStore()
        typer.echo("Running in dry-run mode (memory store).")
    else:
        store = PgVectorStore(lambda: psycopg.connect(dsn), table=table, dimension=dimension)
    pipeline = ETLPipeline(vector_store=store, embedding_provider=provider, embedding_model=embedding_model)
    pipeline.ingest(items)
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
    if dry_run or not dsn:
        store = MemoryVectorStore()
        typer.echo("Running in dry-run mode (memory store).")
    else:
        store = PgVectorStore(lambda: psycopg.connect(dsn), table=table, dimension=dimension)
    pipeline = ETLPipeline(vector_store=store, embedding_provider=provider, embedding_model=embedding_model)
    pipeline.ingest(items)
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
    use_openai_rerank: bool = typer.Option(False, help="Use OpenAI reranker"),
    openai_rerank_model: Optional[str] = typer.Option(None, help="Override OpenAI rerank model"),
    ingest: bool = typer.Option(False, help="Ingest knowledge file before search"),
) -> None:
    """Query knowledge store and display top matching items."""

    provider = _provider_from_flags(use_openai or bool(os.environ.get("OPENAI_API_KEY")), openai_embedding_model)
    embedding_model = openai_embedding_model if isinstance(provider, OpenAIEmbeddingProvider) else None

    if dry_run or not dsn:
        store = MemoryVectorStore()
        if not knowledge_file:
            raise typer.BadParameter("knowledge-file is required in dry-run mode")
    else:
        store = PgVectorStore(lambda: psycopg.connect(dsn), table=table, dimension=dimension)

    documents = {}
    items = []
    if knowledge_file:
        items = load_knowledge_items_from_yaml(knowledge_file)
        documents = {item.item_id: item for item in items}
        if isinstance(store, MemoryVectorStore) or ingest:
            pipeline = ETLPipeline(vector_store=store, embedding_provider=provider, embedding_model=embedding_model)
            pipeline.ingest(items)
    elif isinstance(store, MemoryVectorStore):
        raise typer.BadParameter("knowledge-file is required when using in-memory store")

    rerank_provider = None
    if use_openai_rerank or (openai_rerank_model and bool(os.environ.get("OPENAI_API_KEY"))):
        rerank_provider = OpenAIChatRerankProvider(model=openai_rerank_model)

    retriever = HybridRetriever(
        vector_store=store,
        embedding_provider=provider,
        embedding_model=embedding_model,
        alpha=0.6,
        documents=documents,
        rerank_provider=rerank_provider,
    )

    results = retriever.query(query, top_k=top_k)
    if not results:
        typer.echo("No results")
        raise typer.Exit(code=0)

    for item, score in results:
        snippet = item.content[:160].replace("\n", " ")
        typer.echo(f"{item.item_id}\t{score:.3f}\t{snippet}")


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
