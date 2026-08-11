import os
import json
import numpy as np

from langchain_core.documents import Document

from langchain_openai import OpenAIEmbeddings

DEFAULT_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


class EmbeddingAdapter:
    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL, api_key: str | None = None):
        self.model_name = model_name
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._backend = None

    def _load_backend(self):
        if self._backend is not None:
            return self._backend

        self._backend = OpenAIEmbeddings(model=self.model_name, api_key=self.api_key)
        return self._backend

    def embed_documents(self, texts: list[str]):
        backend = self._load_backend()
        return backend.embed_documents(texts)

    def embed_query(self, text: str):
        backend = self._load_backend()
        return backend.embed_query(text)


def load_filtered_chunks(input_path: str, passed_only: bool = False) -> list[Document]:
    passed_chunks = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            if passed_only and record["metadata"].get("passed_gate") is not True:
                continue
            passed_chunks.append(Document(
                page_content=record["page_content"],
                metadata=record["metadata"]
            ))

    if passed_only:
        print(f"📥 Loaded {len(passed_chunks)} high-quality chunks from {input_path}")
    else:
        print(f"📥 Loaded {len(passed_chunks)} chunks from {input_path}")
    return passed_chunks


def load_embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL):
    print(f"🔄 Loading embedding adapter: {model_name}...")
    embedding_model = EmbeddingAdapter(model_name=model_name)
    print(f"✅ Embedding adapter ready (primary: {model_name})")
    return embedding_model


def generate_embeddings(chunks, model):
    print(f"\n🔄 Generating vectors for {len(chunks)} chunks...")
    texts = [chunk.page_content for chunk in chunks]
    vectors = model.embed_documents(texts)
    vectors_np = np.array(vectors)
    print(f"✅ Created embedding matrix of shape: {vectors_np.shape}")
    return vectors


if __name__ == "__main__":
    INPUT_FILE = "data/chunks/chunks_processed.jsonl"

    high_quality_chunks = load_filtered_chunks(INPUT_FILE)

    if not high_quality_chunks:
        print("❌ No passed chunks found. Check your quality gate thresholds.")
    else:
        emb_model = load_embedding_model()
        chunk_vectors = generate_embeddings(high_quality_chunks, emb_model)

        print("\n--- 🔍 Quick Retrieval Test ---")
        query = "What are the growth drivers for tourism in Asia?"
        query_vector = emb_model.embed_query(query)

        for i in range(min(5, len(chunk_vectors))):
            sim = np.dot(query_vector, chunk_vectors[i])
            print(f"Chunk[{i}] Similarity: {sim:.4f}")
