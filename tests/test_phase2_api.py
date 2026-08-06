import unittest

from fastapi.testclient import TestClient

from APP.main import app
from APP.schemas import HealthStatus, QueryResponse, SourceChunk


class FakeService:
    def health(self):
        return HealthStatus(status="ok", service="rag-api", qdrant="up", openai="up", collection_name="chunks_collection")

    def answer(self, request):
        return QueryResponse(
            request_id="stub",
            answer="stub answer",
            sources=[SourceChunk(chunk_id=1, source="demo.pdf", page=1, score=0.99, content="demo chunk")],
            model="gpt-4o-mini",
            collection_name="chunks_collection",
        )


class Phase2ApiTests(unittest.TestCase):
    def setUp(self):
        app.state.rag_service = FakeService()
        self.client = TestClient(app)

    def test_health_route(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertIn("X-Request-ID", response.headers)

    def test_query_route(self):
        response = self.client.post("/query", json={"question": "What is the summary?", "top_k": 3})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["answer"], "stub answer")
        self.assertEqual(payload["model"], "gpt-4o-mini")
        self.assertEqual(len(payload["sources"]), 1)


if __name__ == "__main__":
    unittest.main()
