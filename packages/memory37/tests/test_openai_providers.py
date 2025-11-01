import types

import pytest

from memory37.embedding import OpenAIEmbeddingProvider
from memory37.rerankers import OpenAIChatRerankProvider


class DummyEmbeddingsClient:
    def create(self, model, input):
        class Response:
            data = [types.SimpleNamespace(embedding=[float(len(text))]) for text in input]

        return Response()


def test_openai_embedding_provider_with_stub_client(monkeypatch):
    provider = OpenAIEmbeddingProvider(client=types.SimpleNamespace(embeddings=DummyEmbeddingsClient()), model="stub")
    vectors = provider.embed(["hello", "world"], model="stub")
    assert vectors == [[5.0], [5.0]]


class DummyResponsesClient:
    def create(self, *args, **kwargs):
        class Response:
            output = [types.SimpleNamespace(content=[types.SimpleNamespace(text='{"ranking":[{"item_id":"a","score":0.9},{"item_id":"b","score":0.5}]}')])]

        return Response()


def test_openai_rerank_provider_with_stub(monkeypatch):
    items = [types.SimpleNamespace(item_id="a", content="A"), types.SimpleNamespace(item_id="b", content="B")]
    client = types.SimpleNamespace(responses=DummyResponsesClient())
    provider = OpenAIChatRerankProvider(client=client, model="stub")
    ranked = provider.rerank("test", items)
    assert ranked[0][0].item_id == "a"
    assert ranked[0][1] == pytest.approx(0.9)
