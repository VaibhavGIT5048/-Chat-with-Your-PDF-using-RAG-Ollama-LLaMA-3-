import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from APP.parsers import ROUTING, SUPPORTED_EXTENSIONS, extraction_quality, parse_document
from APP.parsers.adapters import LocalCsvParser, LocalTextParser
from APP.parsers.base import DocumentParser, is_extraction_acceptable


def _doc(text: str, page: int = 1) -> Document:
    return Document(page_content=text, metadata={"source": "f.pdf", "page": page})


class ExtractionQualityTests(unittest.TestCase):
    def test_empty_extraction_scores_zero(self):
        self.assertEqual(extraction_quality([]), 0.0)
        self.assertEqual(extraction_quality([_doc("")]), 0.0)

    def test_healthy_text_is_acceptable(self):
        self.assertTrue(is_extraction_acceptable([_doc("This is a full page of ordinary prose. " * 10)]))

    def test_scanned_page_with_stray_characters_is_rejected(self):
        # A PDF with no text layer yields a few stray glyphs, not nothing —
        # so an emptiness check alone would wrongly pass this.
        self.assertFalse(is_extraction_acceptable([_doc("Fig. 1"), _doc("2")]))

    def test_mojibake_is_rejected_despite_being_long(self):
        # Failed OCR produces plenty of characters but almost no text; a
        # length-only check would accept this.
        self.assertFalse(is_extraction_acceptable([_doc("�\x01\x02\x03" * 200)]))


class RoutingTableTests(unittest.TestCase):
    def test_csv_never_leaves_the_process(self):
        # Sending CSV to an OCR vendor would be slower, cost money, and risk
        # misreading values that were never ambiguous.
        self.assertEqual([p.name for p in ROUTING[".csv"]], ["local-csv"])

    def test_pdf_tries_free_local_extraction_first(self):
        self.assertEqual(ROUTING[".pdf"][0].name, "local-pdf")

    def test_webp_has_no_azure_tier(self):
        # Azure Document Intelligence does not support .webp in any capacity.
        self.assertNotIn("azure-document-intelligence", [p.name for p in ROUTING[".webp"]])
        self.assertEqual([p.name for p in ROUTING[".webp"]], ["mistral-ocr"])

    def test_office_formats_route_to_document_intelligence(self):
        for ext in (".docx", ".pptx", ".xlsx"):
            self.assertEqual(ROUTING[ext][0].name, "azure-document-intelligence", ext)

    def test_supported_extensions_matches_routing(self):
        self.assertEqual(set(SUPPORTED_EXTENSIONS), set(ROUTING))


class LocalParserTests(unittest.TestCase):
    def test_csv_rows_keep_their_column_names(self):
        # "45, 2030" is unsearchable; "target: 45 | year: 2030" is. Retrieval
        # works on meaning, so the header association has to survive.
        docs = LocalCsvParser().parse(b"target,year\n45%,2030\n", "t.csv")
        self.assertIn("target: 45%", docs[0].page_content)
        self.assertIn("year: 2030", docs[0].page_content)

    def test_csv_without_header_returns_nothing(self):
        self.assertEqual(LocalCsvParser().parse(b"", "empty.csv"), [])

    def test_csv_paginates_large_files(self):
        rows = "a,b\n" + "".join(f"{i},{i}\n" for i in range(120))
        docs = LocalCsvParser().parse(rows.encode(), "big.csv")
        self.assertGreater(len(docs), 1)
        self.assertEqual([d.metadata["page"] for d in docs], list(range(1, len(docs) + 1)))

    def test_text_parser_survives_undecodable_bytes(self):
        docs = LocalTextParser().parse(b"good text \xff\xfe more text", "n.txt")
        self.assertIn("good text", docs[0].page_content)


class FallbackBehaviourTests(unittest.TestCase):
    class _Failing(DocumentParser):
        name = "failing"
        def parse(self, raw_bytes, filename):
            raise RuntimeError("vendor exploded")

    class _Empty(DocumentParser):
        name = "empty"
        def parse(self, raw_bytes, filename):
            return [Document(page_content="x", metadata={"source": filename, "page": 1})]

    class _Good(DocumentParser):
        name = "good"
        def parse(self, raw_bytes, filename):
            return [Document(page_content="Real extracted content. " * 20,
                             metadata={"source": filename, "page": 1})]

    class _Unconfigured(DocumentParser):
        name = "unconfigured"
        def is_available(self):
            return False
        def parse(self, raw_bytes, filename):
            raise AssertionError("must not be called when unavailable")

    def test_escalates_past_a_crashing_parser(self):
        with patch.dict(ROUTING, {".pdf": (self._Failing(), self._Good())}):
            result = parse_document(b"x", "a.pdf")
        self.assertEqual(result.parser, "good")
        self.assertTrue(result.fallback_used)

    def test_escalates_past_poor_quality_output(self):
        with patch.dict(ROUTING, {".pdf": (self._Empty(), self._Good())}):
            result = parse_document(b"x", "a.pdf")
        self.assertEqual(result.parser, "good")

    def test_unconfigured_parser_is_skipped_not_called(self):
        # A missing vendor key is a routing state, not an error.
        with patch.dict(ROUTING, {".pdf": (self._Unconfigured(), self._Good())}):
            result = parse_document(b"x", "a.pdf")
        self.assertEqual(result.parser, "good")
        self.assertFalse(result.fallback_used, "skipped tiers should not count as fallback")

    def test_first_tier_success_reports_no_fallback(self):
        with patch.dict(ROUTING, {".pdf": (self._Good(), self._Failing())}):
            result = parse_document(b"x", "a.pdf")
        self.assertEqual(result.parser, "good")
        self.assertFalse(result.fallback_used)

    def test_low_quality_is_returned_rather_than_nothing(self):
        # Every tier mediocre: returning the best attempt beats failing the
        # upload outright.
        with patch.dict(ROUTING, {".pdf": (self._Empty(),)}):
            result = parse_document(b"x", "a.pdf")
        self.assertEqual(result.parser, "empty")

    def test_all_tiers_failing_raises(self):
        with patch.dict(ROUTING, {".pdf": (self._Failing(),)}):
            with self.assertRaises(ValueError):
                parse_document(b"x", "a.pdf")

    def test_unsupported_extension_raises_with_guidance(self):
        with self.assertRaises(ValueError) as ctx:
            parse_document(b"x", "movie.mp4")
        self.assertIn(".pdf", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
