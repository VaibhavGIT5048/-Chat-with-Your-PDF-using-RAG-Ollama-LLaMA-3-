import unittest

from langchain_core.documents import Document

from APP.rag.structure_chunking import (
    MIN_SECTION_CHARS,
    _detect_boilerplate,
    _is_heading,
    _strip_trailing_page_number,
    split_into_sections,
)

BODY = ("This is a reasonably long body paragraph that comfortably exceeds the minimum "
        "section length so the section is not merged away by the small-section pass. " * 3)


def _page(text: str, page: int) -> Document:
    return Document(page_content=text, metadata={"source": "doc.pdf", "page": page})


class HeadingDetectionTests(unittest.TestCase):
    def test_markdown_heading_wins(self):
        # The Phase 3 path: Document Intelligence emits markdown headings.
        self.assertEqual(_is_heading("## Guiding principles"), (True, "Guiding principles"))

    def test_prose_is_not_a_heading(self):
        self.assertEqual(_is_heading("This is an ordinary sentence of prose.")[0], False)

    def test_numbered_and_caps_headings(self):
        self.assertTrue(_is_heading("1.2 Tension points")[0])
        self.assertTrue(_is_heading("EXECUTIVE SUMMARY")[0])

    def test_wrapped_title_line_rejected(self):
        # "Travel and Tourism at a" is one line of a wrapped cover title; a
        # trailing function word is the giveaway. Without this the title
        # shatters into several bogus sections.
        self.assertEqual(_is_heading("Travel and Tourism at a")[0], False)
        self.assertEqual(_is_heading("Principles for Transformative Growth and")[0], False)

    def test_boilerplate_line_rejected(self):
        header = "Annual Report of Something Important"
        self.assertTrue(_is_heading(header)[0])
        self.assertEqual(_is_heading(header, {header})[0], False)


class PageNumberTests(unittest.TestCase):
    def test_strips_toc_page_number(self):
        self.assertEqual(_strip_trailing_page_number("Growth areas and tensions 12"), "Growth areas and tensions")

    def test_keeps_number_that_is_part_of_the_title(self):
        # Only one word precedes the digit, so it's "Chapter 3", not a TOC entry.
        self.assertEqual(_strip_trailing_page_number("Chapter 3"), "Chapter 3")


class BoilerplateTests(unittest.TestCase):
    def test_detects_running_header_despite_varying_page_number(self):
        # The real-world failure: the header carries the page number, so raw
        # line counting finds zero repeats and the header is never filtered.
        pages = [_page(f"Report Title That Repeats Everywhere {i}\n{BODY}", i) for i in range(1, 9)]
        self.assertIn("Report Title That Repeats Everywhere", _detect_boilerplate(pages))

    def test_ignores_lines_on_few_pages(self):
        # Every line genuinely distinct — note the heading words must differ,
        # not just a trailing number, since detection compares the
        # page-number-stripped form (that is the whole point of it).
        words = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel"]
        pages = [_page(f"{w} Section Heading\n{BODY} {w}", i) for i, w in enumerate(words, start=1)]
        self.assertEqual(_detect_boilerplate(pages), set())


class SectionSplittingTests(unittest.TestCase):
    def test_splits_on_headings_and_labels_sections(self):
        pages = [_page(f"1 First Section\n{BODY}\n2 Second Section\n{BODY}", 1)]
        sections = split_into_sections(pages)
        self.assertEqual([s.metadata.get("section") for s in sections], ["1 First Section", "2 Second Section"])

    def test_page_metadata_is_preserved_for_citations(self):
        pages = [_page(f"1 Alpha\n{BODY}", 1), _page(f"2 Beta\n{BODY}", 2)]
        self.assertEqual([s.metadata["page"] for s in split_into_sections(pages)], [1, 2])

    def test_tiny_sections_are_merged_not_emitted(self):
        # A caption-like heading with almost no body must not become its own
        # chunk; the first run of this chunker produced 3-character chunks.
        pages = [_page(f"FIGURE 1\ntiny\n1 Real Section\n{BODY}", 1)]
        sections = split_into_sections(pages)
        self.assertTrue(all(len(s.page_content) >= MIN_SECTION_CHARS for s in sections))
        self.assertIn("tiny", "\n".join(s.page_content for s in sections))

    def test_consecutive_heading_merge_is_capped(self):
        # A table-of-contents page is nothing but heading-like lines. Uncapped
        # merging collapsed all of them into one enormous label.
        toc = "\n".join(f"{i} Section Title Number {i}" for i in range(1, 13))
        sections = split_into_sections([_page(f"{toc}\n{BODY}", 1)])
        for s in sections:
            self.assertLess(len(s.metadata.get("section") or ""), 200)


if __name__ == "__main__":
    unittest.main()
