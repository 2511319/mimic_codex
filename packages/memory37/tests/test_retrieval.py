from math import sqrt

from memory37.domain import KnowledgeItem
from memory37.retrieval import HybridRetriever, RerankProvider
from memory37.vector_store import EmbeddingProvider, MemoryVectorStore, VectorRecord


class KeywordEmbeddingProvider:
    def __init__(self, keywords: list[str]) -> None:
        self.keywords = keywords

    def embed(self, texts, *, model):
        vectors = []
        for text in texts:
            tokens = text.lower().split()
            vec = [float(sum(1 for token in tokens if token == keyword or token.startswith(keyword))) for keyword in self.keywords]
            norm = sqrt(sum(x * x for x in vec)) or 1.0
            vectors.append([x / norm for x in vec])
        return vectors


def test_hybrid_retriever_prioritises_relevant_documents() -> None:
    keywords = ["moon", "ruins", "merchant"]
    provider: EmbeddingProvider = KeywordEmbeddingProvider(keywords)
    store = MemoryVectorStore()
    retriever = HybridRetriever(vector_store=store, embedding_provider=provider, embedding_model="test", alpha=0.5)

    items = [
        KnowledgeItem(item_id="scene_1", domain="scene", content="Ancient ruins under the moonlit sky"),
        KnowledgeItem(item_id="npc_1", domain="npc", content="Traveling merchant selling rare artifacts"),
        KnowledgeItem(item_id="lore_1", domain="lore", content="Legend says the moon bridge guards the ruins"),
    ]

    retriever.index(items)

    results = retriever.query("moon ruins", top_k=2)
    ids = [item.item_id for item, _ in results]

    assert ids[0] == "scene_1"
    assert "lore_1" in ids


class StubReranker:
    def rerank(self, query: str, items):
        ordered = sorted(items, key=lambda item: item.item_id, reverse=True)
        return [(item, float(idx)) for idx, item in enumerate(ordered, 1)]


def test_hybrid_retriever_with_rerank_provider_changes_order() -> None:
    keywords = ["moon", "ruins"]
    provider: EmbeddingProvider = KeywordEmbeddingProvider(keywords)
    store = MemoryVectorStore()
    retriever = HybridRetriever(
        vector_store=store,
        embedding_provider=provider,
        embedding_model="test",
        alpha=0.5,
        rerank_provider=StubReranker(),
    )

    items = [
        KnowledgeItem(item_id="scene_a", domain="scene", content="moon story"),
        KnowledgeItem(item_id="npc_b", domain="npc", content="ruins merchant"),
    ]

    retriever.index(items)
    results = retriever.query("moon ruins", top_k=2)
    ids = [item.item_id for item, _ in results]

    assert ids[0] == "scene_a"  # due to stub reranker reversing order


def test_hybrid_retriever_without_documents_uses_metadata() -> None:
    provider: EmbeddingProvider = KeywordEmbeddingProvider(["moon"])
    store = MemoryVectorStore()
    # simulate pre-ingested record with metadata/content
    store.upsert([
        VectorRecord(
            item_id="scene::demo",
            vector=[1.0],
            metadata={"domain": "scene", "content": "Moonlit forest encounter"}
        )
    ])
    retriever = HybridRetriever(vector_store=store, embedding_provider=provider, embedding_model="test", alpha=0.5)

    results = retriever.query("moon", top_k=1)

    assert results
    item, score = results[0]
    assert item.item_id == "scene::demo"
    assert score > 0.0
