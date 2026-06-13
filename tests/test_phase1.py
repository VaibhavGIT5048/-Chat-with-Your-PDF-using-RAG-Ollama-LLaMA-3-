import unittest
from langchain_core.documents import Document

import APP.chunking as chunking
import APP.vector_store as vector_store


class Phase1Tests(unittest.TestCase):
    def test_chunk_documents_splitter(self):
        original_recursive = chunking.RecursiveCharacterTextSplitter

        class DummySplitter:
            def __init__(self, *args, **kwargs):
                pass

            def split_documents(self, documents):
                return documents

        try:
            chunking.RecursiveCharacterTextSplitter = DummySplitter
            docs = [Document(page_content="Alpha beta gamma.", metadata={"page": 1})]
            chunks = chunking.chunk_documents(docs)
            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0].metadata["chunk_id"], 0)
            self.assertEqual(chunks[0].metadata["chunk_size"], len("Alpha beta gamma."))
        finally:
            chunking.RecursiveCharacterTextSplitter = original_recursive

    def test_flashrank_empty_candidates_returns_safe_slice(self):
        result = vector_store.flashrank_rerank("test query", [], k=5)
        self.assertEqual(result, [])

    def test_quality_penalty_prefers_passed_chunks(self):
        docs = [
            Document(page_content="one", metadata={"passed_gate": True}),
            Document(page_content="two", metadata={"passed_gate": False}),
        ]
        scored = vector_store.apply_quality_penalty(docs, [1.0, 1.0])
        self.assertEqual(scored[0][0].page_content, "one")
        self.assertGreater(scored[0][1], scored[1][1])


if __name__ == "__main__":
    unittest.main()
