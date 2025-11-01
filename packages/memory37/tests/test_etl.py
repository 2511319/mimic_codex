from memory37.domain import KnowledgeItem
from memory37.etl import ETLPipeline
from memory37.vector_store import EmbeddingProvider, MemoryVectorStore


class StubEmbeddingProvider:
    def embed(self, texts, *, model):
        # return identity vectors with padding
        result = []
        for text in texts:
            length = len(text)
            result.append([float(length), 0.0, 0.0])
        return result


def test_etl_ingest_writes_to_vector_store() -> None:
    store = MemoryVectorStore()
    provider: EmbeddingProvider = StubEmbeddingProvider()
    pipeline = ETLPipeline(vector_store=store, embedding_provider=provider, embedding_model="test-model")

    items = [
        KnowledgeItem(item_id="kn_001", domain="scene", content="Short scene summary"),
        KnowledgeItem(item_id="kn_002", domain="npc", content="NPC profile snippet", metadata={"npc_id": "npc_1"})
    ]

    pipeline.ingest(items)

    results = store.query([0.0, 0.0, 0.0], top_k=10)
    ids = {record.item_id for record in results}
    assert ids == {"kn_001", "kn_002"}
    assert all("content" in record.metadata for record in results)
