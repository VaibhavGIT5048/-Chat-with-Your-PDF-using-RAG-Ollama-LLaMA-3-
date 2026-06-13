from __future__ import annotations

import os
from time import perf_counter

import requests
import streamlit as st
from dotenv import load_dotenv
from requests.exceptions import ConnectionError

load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:8000")


def api_health() -> bool:
    try:
        resp = requests.get(f"{API_URL}/health", timeout=3)
        return resp.status_code == 200
    except (ConnectionError, requests.Timeout):
        return False


def api_ingest(filename: str, file_bytes: bytes, chunk_size: int, chunk_overlap: int, quality_threshold: float):
    files = {"file": (filename, file_bytes)}
    data = {
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "quality_threshold": quality_threshold,
    }
    started = perf_counter()
    resp = requests.post(f"{API_URL}/ingest", files=files, data=data, timeout=120)
    latency_ms = round((perf_counter() - started) * 1000, 2)
    resp.raise_for_status()
    return resp.json(), latency_ms


def api_query(question: str, top_k: int):
    started = perf_counter()
    resp = requests.post(f"{API_URL}/query", json={"question": question, "top_k": top_k}, timeout=120)
    latency_ms = round((perf_counter() - started) * 1000, 2)
    resp.raise_for_status()
    return resp.json(), latency_ms


def render_sources(sources: list[dict]) -> None:
    if not sources:
        st.info("No sources returned for this answer.")
        return

    with st.expander("Retrieved Chunks", expanded=True):
        for idx, source_chunk in enumerate(sources, start=1):
            st.markdown(
                f"**#{idx}** | Score: `{source_chunk.get('score', 0):.4f}` | "
                f"Source: `{source_chunk.get('source')}` | Page: `{source_chunk.get('page')}`"
            )
            st.write(source_chunk.get("content", "")[:900])
            st.divider()


def main() -> None:
    st.set_page_config(page_title="RAG Test UI", layout="wide")
    st.title("RAG Test UI")
    st.caption("Streamlit test client for the REST API backend")

    if not api_health():
        st.error(f"API backend is not reachable at {API_URL}")
        st.stop()

    st.success(f"Connected to API at {API_URL}")

    with st.sidebar:
        st.subheader("Test Controls")
        chunk_size = st.slider("Chunk size", 400, 2000, 1000, 100)
        chunk_overlap = st.slider("Chunk overlap", 50, 400, 150, 25)
        quality_threshold = st.slider("Quality threshold", 0.0, 7.0, 4.0, 0.5)
        top_k = st.slider("Retrieved chunks", 1, 8, 4)
        auto_clear = st.checkbox("Clear chat after ingest", value=True)

    uploaded_files = st.file_uploader("Upload PDF files", type=["pdf"], accept_multiple_files=True)
    ingest_requested = st.button("Ingest PDFs", type="primary", disabled=not uploaded_files)

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "pipeline_stats" not in st.session_state:
        st.session_state.pipeline_stats = None

    if ingest_requested and uploaded_files:
        for uploaded_file in uploaded_files:
            st.write(f"Ingesting `{uploaded_file.name}`")
            try:
                result, ingest_latency_ms = api_ingest(
                    filename=uploaded_file.name,
                    file_bytes=uploaded_file.getvalue(),
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    quality_threshold=quality_threshold,
                )
            except requests.HTTPError as exc:
                st.error(f"Ingest failed for {uploaded_file.name}: {exc.response.status_code} {exc.response.text}")
                st.stop()
            except (ConnectionError, requests.Timeout) as exc:
                st.error(f"API connection failed during ingest: {exc}")
                st.stop()

            st.session_state.pipeline_stats = result
            st.metric("Ingest latency", f"{ingest_latency_ms} ms")
            st.json(result)

        if auto_clear:
            st.session_state.chat_history = []

    if st.session_state.pipeline_stats:
        stats = st.session_state.pipeline_stats
        st.info(
            f"Filename: {stats.get('filename')} | Pages: {stats.get('pages')} | Chunks: {stats.get('chunks')} | "
            f"Passed: {stats.get('passed_chunks')} | Dropped: {stats.get('dropped_chunks')} | "
            f"Indexed: {stats.get('indexed_chunks')}"
        )

    if uploaded_files is None:
        st.warning("Upload and ingest a PDF to start querying.")
        return

    for item in st.session_state.chat_history:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])

    question = st.chat_input("Ask a question about the ingested PDF...")
    if not question:
        return

    st.session_state.chat_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Querying API..."):
            try:
                response, query_latency_ms = api_query(question, top_k)
            except requests.HTTPError as exc:
                st.error(f"Query failed: {exc.response.status_code} {exc.response.text}")
                st.stop()
            except (ConnectionError, requests.Timeout) as exc:
                st.error(f"API connection failed during query: {exc}")
                st.stop()

        answer = response.get("answer", "No answer generated")
        sources = response.get("sources", [])
        st.markdown(answer)
        st.caption(f"Query latency: {query_latency_ms} ms")
        st.session_state.chat_history.append({"role": "assistant", "content": answer})
        render_sources(sources)


if __name__ == "__main__":
    main()
