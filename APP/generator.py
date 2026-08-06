from __future__ import annotations

import os
import pickle
import time
from pathlib import Path

from openai import OpenAI

from APP.vector_store import (
    QdrantVectorStore,
    expand_with_neighbors_scored,
    flashrank_rerank,
    hybrid_retrieve,
)
from APP.embedding import load_embedding_model
from qdrant_client import QdrantClient

# ─────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT — strict grounding, zero hallucination
# Canonical export: api_service.py and ragas_evaluation.py import this.
# ─────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are a document analyst. Your ONLY job is to answer questions using the context below.

STRICT RULES (violation = wrong answer):
1. ONLY use information explicitly stated in the context. NEVER infer, extrapolate, or add general knowledge.
2. If the context does not contain enough information to answer, say EXACTLY:
   "I cannot find this information in the provided document."
3. Do NOT paraphrase facts you are unsure about — quote or closely follow the context wording.
4. Cite every key claim inline: [Source: <filename> | Page: <page>]
5. Do NOT answer from memory or training data. The context IS the only valid source.

ANSWERING STYLE:
- Factual questions: direct answer first, then supporting evidence from context.
- Explanatory questions: brief explanation + evidence.
- Comparison questions: compare only what the context explicitly states.
- If partial information exists: answer what is supported, flag what is missing.
"""

TOP_N = 5


def load_indices():
    bm25_path = Path("data/indexes/bm25_data.pkl")
    if not bm25_path.exists():
        raise FileNotFoundError("data/indexes/bm25_data.pkl not found. Run /ingest first.")

    print("🔄 Loading BM25 index...")
    with open(bm25_path, "rb") as f:
        data = pickle.load(f)
    bm25 = data["bm25"]
    chunks = data["chunks"]

    print("🔄 Connecting to Qdrant...")
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    client = QdrantClient(url=qdrant_url)
    embeddings = load_embedding_model()
    vectorstore = QdrantVectorStore(
        client=client,
        collection_name=os.getenv("QDRANT_COLLECTION", "chunks_collection"),
        embeddings=embeddings,
    )

    print("🔥 Warming up reranker...")
    if chunks:
        flashrank_rerank("warmup query", chunks[:1], k=1)
    print("✅ Reranker ready")

    return vectorstore, bm25, chunks


def generate_answer(prompt: str, model: str) -> str:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return (response.choices[0].message.content or "").strip()


def run_rag_chat():
    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

    vectorstore, bm25, chunks = load_indices()
    print(f"\n✅ RAG SYSTEM READY ({len(chunks)} chunks indexed)")
    print(f"   Model     : {model}  [OpenAI]")
    print(f"   Top-N     : {TOP_N}")
    print("   Type 'exit' to quit.\n")

    while True:
        query = input("👤 Question: ").strip()
        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            break

        t0 = time.perf_counter()
        results = hybrid_retrieve(query, vectorstore, bm25, chunks, top_n=TOP_N)
        retrieval_ms = (time.perf_counter() - t0) * 1000

        if not results:
            print("⚠️  No relevant chunks found.\n")
            continue

        expanded = expand_with_neighbors_scored(results=results, chunks=chunks, window=1)

        context_parts = []
        for doc, score in expanded:
            source = doc.metadata.get("source", "unknown")
            page = doc.metadata.get("page", "?")
            context_parts.append(
                f"[Source: {source} | Page: {page} | Score: {score:.3f}]\n"
                f"{doc.page_content}"
            )
        context_blob = "\n\n---\n\n".join(context_parts)

        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"CONTEXT:\n{context_blob}\n\n"
            f"QUESTION: {query}\n\n"
            f"ANSWER (use ONLY the context above):"
        )

        t1 = time.perf_counter()
        print(f"\n🤖 Generating... (retrieval: {retrieval_ms:.0f}ms)", flush=True)
        answer = generate_answer(prompt, model=model, ollama_url=ollama_url)
        generation_ms = (time.perf_counter() - t1) * 1000
        total_ms = retrieval_ms + generation_ms

        print(f"\n📝 ANSWER:\n{answer}")
        print(f"\n⏱  retrieval={retrieval_ms:.0f}ms  generation={generation_ms:.0f}ms  total={total_ms:.0f}ms\n")


if __name__ == "__main__":
    run_rag_chat()