"""Side-by-side retrieval comparison of two already-ingested copies of the
same document, one chunked per strategy.

Speed benchmarks say nothing about whether chunk boundaries put the answer in
a retrievable place. This asks the same questions of both copies and reports
where they disagree — specifically where one grounds an answer and the other
refuses, which is the failure mode that matters: a false heading splitting a
passage so neither half retrieves well.

Usage:
  python scripts/compare_chunking_retrieval.py <structure_doc_id> <recursive_doc_id>
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

API = os.getenv("API_BASE_URL", "http://localhost:8000")
EMAIL = os.getenv("RAG_TEST_EMAIL", "vwork825@gmail.com")
PASSWORD = os.getenv("RAG_TEST_PASSWORD", "correct-horse-battery")

# Drawn from the document's own content so a correct system can answer them.
# The last one is deliberately unanswerable: both copies should refuse, which
# checks the grounding prompt still holds under either chunking.
QUESTIONS = [
    "What are the main tension points identified for travel and tourism?",
    "What are the guiding principles for a transformed sector?",
    "What does the report say about the labour and skills crisis?",
    "How is technology described as an enabler for the sector?",
    "What is the role of the wider ecosystem?",
    "What is the exact share price of the World Economic Forum?",  # unanswerable
]

REFUSAL_MARKERS = ("cannot find", "not find", "no information", "does not contain", "unable to find")


def _post(path: str, payload: dict, token: str | None = None) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{API}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())


def login() -> str:
    return _post("/auth/login", {"email": EMAIL, "password": PASSWORD})["access_token"]


def ask(token: str, doc_id: str, question: str) -> dict:
    return _post("/query", {"document_id": doc_id, "question": question, "top_k": 4}, token)


def refused(answer: str) -> bool:
    low = answer.lower()
    return any(m in low for m in REFUSAL_MARKERS)


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    structure_id, recursive_id = sys.argv[1], sys.argv[2]
    token = login()

    disagreements = 0
    for i, q in enumerate(QUESTIONS, start=1):
        print("=" * 78)
        print(f"Q{i}: {q}")
        print("=" * 78)
        row = {}
        for label, doc_id in (("structure", structure_id), ("recursive", recursive_id)):
            try:
                res = ask(token, doc_id, q)
                answer = res["answer"]
                pages = sorted({s.get("page") for s in res.get("sources", [])})
                row[label] = refused(answer)
                print(f"\n[{label}] refused={row[label]}  sources={len(res.get('sources', []))} pages={pages}")
                print(f"  {answer[:340]}")
            except Exception as exc:  # noqa: BLE001 - report and continue
                row[label] = None
                print(f"\n[{label}] ERROR: {exc}")
        if row.get("structure") != row.get("recursive"):
            disagreements += 1
            print("\n  >>> DISAGREEMENT: one grounded an answer, the other did not <<<")
        print()

    print("=" * 78)
    print(f"Questions: {len(QUESTIONS)}   Disagreements: {disagreements}")
    print("A disagreement on an answerable question means one strategy's chunk")
    print("boundaries hid the evidence. Zero disagreements means the strategies")
    print("are equivalent for retrieval on this document, so the faster one wins.")


if __name__ == "__main__":
    main()
