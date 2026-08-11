import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain_core.documents import Document

from APP.rag.chunking import chunk_documents
from APP.rag.embedding import load_embedding_model
from APP.rag.vector_store import apply_quality_penalty, flashrank_rerank


def main():
    docs = [Document(page_content="This is a short smoke-test document.", metadata={"page": 1})]
    chunks = chunk_documents(docs)
    print(f"chunk_count={len(chunks)}")

    adapter = load_embedding_model()
    vec = adapter.embed_query("smoke test")
    print(f"embedding_dim={len(vec)}")

    scored = apply_quality_penalty(chunks, [1.0 for _ in chunks])
    print(f"quality_scored={len(scored)}")

    reranked = flashrank_rerank("smoke test", chunks, k=1)
    print(f"reranked={len(reranked)}")


if __name__ == "__main__":
    main()
