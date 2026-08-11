"""Concrete parser adapters.

Routing rationale (see the plan's Phase 3 table):
- Local extraction first wherever it works — it is free and adds no latency.
- Azure Document Intelligence is the paid fallback and the primary for Office
  formats, where structure-aware extraction genuinely beats a raw cell dump.
- Mistral OCR handles .webp, which Azure does not support in any capacity.
- .csv is parsed locally and never sent anywhere: it is already flat,
  machine-readable text, so routing it through OCR would be slower, cost
  money, and risk transcription errors in the values.

Every adapter degrades rather than raising when its vendor isn't configured,
so an unset key means "skip this tier", not "fail the upload".
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from langchain_core.documents import Document

from APP.parsers.base import DocumentParser
from APP.rag.pdf_loading import load_pdf


class LocalPdfParser(DocumentParser):
    """pypdf/pdfplumber via the existing loader. Free, no network."""

    name = "local-pdf"
    extensions = (".pdf",)

    def parse(self, raw_bytes: bytes, filename: str) -> list[Document]:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(raw_bytes)
            tmp_path = Path(tmp.name)
        try:
            docs = []
            for page in load_pdf(tmp_path):
                meta = dict(page.metadata)
                meta["source"] = filename
                docs.append(Document(page_content=page.page_content, metadata=meta))
            return docs
        finally:
            tmp_path.unlink(missing_ok=True)


class LocalTextParser(DocumentParser):
    """Plain-text formats. Decoded with errors='ignore' rather than failing:
    a stray undecodable byte shouldn't cost the user the whole document."""

    name = "local-text"
    extensions = (".txt", ".md", ".markdown", ".json", ".log")

    def parse(self, raw_bytes: bytes, filename: str) -> list[Document]:
        text = raw_bytes.decode("utf-8", errors="ignore").strip()
        if not text:
            return []
        return [Document(page_content=text, metadata={"source": filename, "page": 1, "id": str(uuid4())})]


class LocalCsvParser(DocumentParser):
    """CSV, parsed locally and deliberately never sent to a vendor.

    Rows are rendered as "column: value" lines rather than raw comma-separated
    text, because retrieval works on meaning: a bare row loses the header
    association, so a chunk reading "45, 2030, scope 1" is unsearchable while
    "target: 45 | year: 2030" is not.
    """

    name = "local-csv"
    extensions = (".csv",)
    ROWS_PER_DOC = 50

    def parse(self, raw_bytes: bytes, filename: str) -> list[Document]:
        text = raw_bytes.decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return []

        docs: list[Document] = []
        buffer: list[str] = []
        page = 1
        for row in reader:
            rendered = " | ".join(
                f"{(k or '').strip()}: {(v or '').strip()}"
                for k, v in row.items() if v and str(v).strip()
            )
            if rendered:
                buffer.append(rendered)
            if len(buffer) >= self.ROWS_PER_DOC:
                docs.append(Document(page_content="\n".join(buffer),
                                     metadata={"source": filename, "page": page}))
                buffer, page = [], page + 1

        if buffer:
            docs.append(Document(page_content="\n".join(buffer),
                                 metadata={"source": filename, "page": page}))
        return docs


class AzureDocumentIntelligenceParser(DocumentParser):
    """Azure AI Document Intelligence — paid fallback, and primary for Office.

    Uses prebuilt-layout for its markdown output: the `#` headings feed
    structure-aware chunking directly, replacing the text heuristics that
    struggle with multi-column PDFs. Never prebuilt-documentSearch or any
    figure-analysis analyzer — those invoke an LLM and cost several times more
    for captioning this pipeline doesn't use.
    """

    name = "azure-document-intelligence"
    extensions = (".pdf", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".heif")

    def __init__(self) -> None:
        self.endpoint = os.getenv("AZURE_DOC_INTEL_ENDPOINT", "").rstrip("/")
        self.key = os.getenv("AZURE_DOC_INTEL_KEY", "")

    def is_available(self) -> bool:
        return bool(self.endpoint and self.key)

    def parse(self, raw_bytes: bytes, filename: str) -> list[Document]:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential

        client = DocumentIntelligenceClient(self.endpoint, AzureKeyCredential(self.key))
        poller = client.begin_analyze_document(
            "prebuilt-layout",
            body=raw_bytes,
            content_type="application/octet-stream",
            output_content_format="markdown",
        )
        result = poller.result()

        docs: list[Document] = []
        pages = getattr(result, "pages", None) or []
        content = getattr(result, "content", "") or ""

        if pages and getattr(result, "paragraphs", None):
            # Group paragraphs by their page so citations keep page numbers.
            by_page: dict[int, list[str]] = {}
            for para in result.paragraphs:
                regions = getattr(para, "bounding_regions", None) or []
                page_no = regions[0].page_number if regions else 1
                by_page.setdefault(page_no, []).append(para.content)
            for page_no in sorted(by_page):
                docs.append(Document(
                    page_content="\n".join(by_page[page_no]),
                    metadata={"source": filename, "page": page_no, "total_pages": len(pages)},
                ))
        elif content:
            docs.append(Document(page_content=content, metadata={"source": filename, "page": 1}))

        return docs


class MistralOcrParser(DocumentParser):
    """Mistral OCR — the only option for .webp, which Azure Document
    Intelligence does not support in any capacity (confirmed absent from its
    supported-format list)."""

    name = "mistral-ocr"
    extensions = (".webp", ".jpg", ".jpeg", ".png", ".pdf")

    def __init__(self) -> None:
        self.api_key = os.getenv("MISTRAL_API_KEY", "")
        self.model = os.getenv("MISTRAL_OCR_MODEL", "mistral-ocr-latest")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def parse(self, raw_bytes: bytes, filename: str) -> list[Document]:
        import base64

        import httpx

        suffix = Path(filename).suffix.lower().lstrip(".") or "png"
        mime = "application/pdf" if suffix == "pdf" else f"image/{'jpeg' if suffix in ('jpg', 'jpeg') else suffix}"
        encoded = base64.b64encode(raw_bytes).decode()

        doc_key = "document_url" if suffix == "pdf" else "image_url"
        with httpx.Client(timeout=180) as client:
            response = client.post(
                "https://api.mistral.ai/v1/ocr",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "document": {"type": doc_key, doc_key: f"data:{mime};base64,{encoded}"},
                },
            )
            response.raise_for_status()
            payload = response.json()

        docs: list[Document] = []
        for index, page in enumerate(payload.get("pages", []), start=1):
            text = (page.get("markdown") or page.get("text") or "").strip()
            if text:
                docs.append(Document(page_content=text, metadata={"source": filename, "page": index}))
        return docs
