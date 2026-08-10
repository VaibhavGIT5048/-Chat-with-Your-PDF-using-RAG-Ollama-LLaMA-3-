"""Embedding providers — self-hosted bge-m3 by default, plain OpenAI for BYO-key.

Both expose embed_documents()/embed_query() returning plain float lists, the
same shape APP/vector_store.py and APP/quality_gate.py already consume via
the old EmbeddingAdapter — swapping providers needs no changes downstream.
"""

from __future__ import annotations

import os

DEFAULT_BGE_MODEL = os.getenv("BGE_MODEL_NAME", "BAAI/bge-m3")
DEFAULT_BYO_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


class EmbeddingProvider:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


class BgeEmbeddingProvider(EmbeddingProvider):
    """Self-hosted BAAI/bge-m3 via sentence-transformers, CPU-only — no
    Azure resource, no per-token API cost. Loaded lazily on first use since
    the model weights (~2GB) shouldn't be pulled at process startup.
    """

    def __init__(self, model_name: str = DEFAULT_BGE_MODEL):
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            print(f"🔄 Loading self-hosted embedding model: {self.model_name}...")
            self._model = SentenceTransformer(self.model_name, device="cpu")
            print(f"✅ Self-hosted embedding model ready: {self.model_name}")
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """BYO-key — constructed per-request from a header, never persisted."""

    def __init__(self, api_key: str | None, model: str = DEFAULT_BYO_EMBEDDING_MODEL):
        self.api_key = api_key
        self.model = model
        self._backend = None

    def _load(self):
        if self._backend is None:
            from langchain_openai import OpenAIEmbeddings

            self._backend = OpenAIEmbeddings(model=self.model, api_key=self.api_key)
        return self._backend

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._load().embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._load().embed_query(text)


def build_default_embedding_provider() -> EmbeddingProvider:
    return BgeEmbeddingProvider()


def as_langchain_embeddings(provider: EmbeddingProvider):
    """Wraps a provider in LangChain's `Embeddings` base class.

    SemanticChunker declares `embeddings: Embeddings` as a pydantic field, so
    a duck-typed object with the right methods isn't guaranteed to pass
    validation — this makes the relationship explicit rather than relying on
    whether pydantic happens to be lenient in a given version.
    """
    from langchain_core.embeddings import Embeddings

    class _ProviderBackedEmbeddings(Embeddings):
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return provider.embed_documents(texts)

        def embed_query(self, text: str) -> list[float]:
            return provider.embed_query(text)

    return _ProviderBackedEmbeddings()
