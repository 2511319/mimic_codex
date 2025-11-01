from math import sqrt

from datetime import datetime

from memory37.domain import ArtCard, NpcMemoryEntry, NpcProfile, RelationDelta, SceneChronicleEntry, SceneState
from memory37.etl import ETLPipeline
from memory37.ingest import build_runtime_items
from memory37.retrieval import HybridRetriever
from memory37.vector_store import EmbeddingProvider, MemoryVectorStore


class TokenEmbeddingProvider:
    def embed(self, texts, *, model):
        vectors = []
        for text in texts:
            tokens = text.lower().split()
            freq = {}
            for token in tokens:
                freq[token] = freq.get(token, 0) + 1
            sorted_terms = sorted(freq)[:10]
            vec = [freq[term] for term in sorted_terms]
            # pad to fixed length 10
            vec += [0] * (10 - len(vec))
            norm = sqrt(sum(x * x for x in vec)) or 1.0
            vectors.append([x / norm for x in vec])
        return vectors


def test_end_to_end_ingest_and_retrieve() -> None:
    store = MemoryVectorStore()
    provider: EmbeddingProvider = TokenEmbeddingProvider()
    etl = ETLPipeline(vector_store=store, embedding_provider=provider, embedding_model="stub")

    scene = SceneState(
        scene_id="scn_100",
        campaign_id="cmp_alpha",
        title="Moonlit Ruins",
        summary="Party explores forgotten ruins",
        chronology=[SceneChronicleEntry(timestamp=datetime.utcnow(), summary="Discovery")],
        relations_delta=[RelationDelta(source_id="party", target_id="npc_sage", delta=1, reason="shared knowledge")],
        tags=["moon", "ruins"],
    )
    npc = NpcProfile(
        npc_id="npc_sage",
        name="Arin",
        archetype="sage",
        memory=[NpcMemoryEntry(summary_id="sum1", impact="trust+1")],
    )
    art = ArtCard(
        image_id="art_100",
        scene_id="scn_100",
        cdn_url="https://cdn.example/art_100.webp",
        prompt_text="moonlight over ruins",
        entities={"npc": ["npc_sage"]},
    )

    knowledge_items = build_runtime_items(scenes=[scene], npcs=[npc], art_cards=[art])
    etl.ingest(knowledge_items)

    retriever = HybridRetriever(
        vector_store=store,
        embedding_provider=provider,
        embedding_model="stub",
        alpha=0.5,
    )
    retriever.documents = {item.item_id: item for item in knowledge_items}

    results = retriever.query("moon ruins sage", top_k=2)
    ids = [item.item_id for item, _ in results]

    assert ids[0].startswith("scene::scn_100") or ids[0].startswith("npc::npc_sage")
