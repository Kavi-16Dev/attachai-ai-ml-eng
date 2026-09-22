import hashlib

from app.config import settings


class BaseEmbeddingClient:
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class FakeEmbeddingClient(BaseEmbeddingClient):
    """Deterministic, free, local stand-in for a real embeddings API.

    Same text always yields the same vector; different text yields a
    different one. Used for everything already built in this app (knowledge
    base, matching) so the app runs end to end with zero API keys.

    Part 3 of the assignment is where a REAL LLM API is required — this
    class has nothing to do with that pipeline.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        dim = settings.embed_dim
        vec = [0.0] * dim
        for word in text.lower().split():
            digest = int(hashlib.sha256(word.encode()).hexdigest(), 16)
            idx = digest % dim
            sign = 1.0 if (digest // dim) % 2 == 0 else -1.0
            vec[idx] += sign
        norm = sum(v * v for v in vec) ** 0.5
        if norm == 0:
            return vec
        return [v / norm for v in vec]


embedding_client = FakeEmbeddingClient()
