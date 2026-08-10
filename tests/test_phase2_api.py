import unittest

from fastapi.testclient import TestClient

from APP.auth import get_current_user
from APP.main import app
from APP.schemas import HealthStatus, QueryResponse, SourceChunk

FAKE_USER = {"id": "test-user-id", "email": "test@example.com"}


class FakeService:
    def health(self):
        return HealthStatus(status="ok", service="rag-api", qdrant="up", openai="up", collection_name="chunks_collection")

    def answer(self, owner_id, request, byo_openai_key=None):
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
        # Auth is exercised separately (OAuth exchange, OTP flow, JWT
        # decoding) — these route-level tests stub the identity so they
        # only assert on request/response shape, not on the real auth path.
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_health_route(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertIn("X-Request-ID", response.headers)

    def test_query_route(self):
        response = self.client.post(
            "/query",
            json={"document_id": "doc-1", "question": "What is the summary?", "top_k": 3},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["answer"], "stub answer")
        self.assertEqual(payload["model"], "gpt-4o-mini")
        self.assertEqual(len(payload["sources"]), 1)

    def test_query_route_requires_auth(self):
        app.dependency_overrides.clear()  # exercise the real dependency for this one case
        response = self.client.post(
            "/query",
            json={"document_id": "doc-1", "question": "What is the summary?", "top_k": 3},
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
