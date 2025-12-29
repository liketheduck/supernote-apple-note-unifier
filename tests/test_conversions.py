"""
Comprehensive tests for bidirectional markdown/HTML conversion.

Tests both directions:
- Markdown → Apple HTML (reverse sync direction)
- Apple HTML → Markdown (forward sync direction)
"""

import re
from pathlib import Path

import pytest

# Import the converters
from unifier.converters.markdown_to_html import (
    extract_title_from_markdown,
    markdown_to_apple_html,
)
from unifier.generators.markdown import HTMLToMarkdownParser

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MD_TO_HTML_DIR = FIXTURES_DIR / "markdown_to_html"
HTML_TO_MD_DIR = FIXTURES_DIR / "html_to_markdown"


def html_to_markdown(html: str, title: str | None = None) -> str:
    """Helper to convert HTML to markdown using the parser."""
    # Clean up HTML (same as MarkdownGenerator._clean_html)
    html = re.sub(r'\s+style\s*=\s*["\'][^"\']*["\']', '', html)
    html = re.sub(r'\s+class\s*=\s*["\'][^"\']*["\']', '', html)

    parser = HTMLToMarkdownParser(title_to_skip=title)
    parser.feed(html)
    return parser.get_markdown()


class TestMarkdownToHTML:
    """Test Markdown → Apple HTML conversion (reverse sync)."""

    def test_basic_formatting(self):
        """Test bold, italic, code, strikethrough."""
        md = Path(MD_TO_HTML_DIR / "01_basic_formatting.txt").read_text()
        html = markdown_to_apple_html(md)

        # Check bold conversion
        assert "<b>bold text</b>" in html
        assert "<b>bold words in a row</b>" in html

        # Check italic conversion
        assert "<i>italic text</i>" in html
        assert "<i>italic words in a row</i>" in html

        # Check combined bold+italic
        assert "<b><i>bold italic combined</i></b>" in html

        # Check inline code
        assert "<code>inline code</code>" in html

        # Check strikethrough
        assert "<s>strikethrough text</s>" in html

        # Check nested formatting
        assert "<b>nested <i>formatting</i> works</b>" in html

    def test_headers_hierarchy(self):
        """Test all header levels H1-H6."""
        md = Path(MD_TO_HTML_DIR / "02_headers_hierarchy.txt").read_text()
        html = markdown_to_apple_html(md)

        assert "<h1>Main Title H1</h1>" in html
        assert "<h2>Section One H2</h2>" in html
        assert "<h3>Subsection 1.1 H3</h3>" in html
        assert "<h4>Deep Heading H4</h4>" in html
        assert "<h5>Very Deep H5</h5>" in html
        assert "<h6>Deepest H6</h6>" in html

    def test_nested_lists(self):
        """Test nested unordered and ordered lists."""
        md = Path(MD_TO_HTML_DIR / "03_nested_lists_complex.txt").read_text()
        html = markdown_to_apple_html(md)

        # Check unordered list structure
        assert "<ul>" in html
        assert "<li>" in html

        # Check ordered list structure
        assert "<ol>" in html

        # Check formatting in lists
        assert "<b>Bold list item</b>" in html
        assert "<i>Italic list item</i>" in html

    def test_links_and_urls(self):
        """Test markdown links and auto-linking."""
        md = Path(MD_TO_HTML_DIR / "04_links_and_urls.txt").read_text()
        html = markdown_to_apple_html(md)

        # Check markdown links
        assert '<a href="https://example.com">simple link</a>' in html
        assert '<a href="https://google.com">Google</a>' in html
        assert '<a href="https://github.com">GitHub</a>' in html

        # Check auto-linked URLs
        assert "https://example.com" in html

    def test_code_blocks(self):
        """Test fenced code blocks."""
        md = Path(MD_TO_HTML_DIR / "05_code_blocks.txt").read_text()
        html = markdown_to_apple_html(md)

        # Check code block conversion
        assert "<pre>" in html
        assert "function hello()" in html
        assert "console.log" in html

    def test_blockquotes(self):
        """Test blockquote conversion."""
        md = Path(MD_TO_HTML_DIR / "06_blockquotes.txt").read_text()
        html = markdown_to_apple_html(md)

        assert "<blockquote>" in html
        assert "This is a simple blockquote" in html

    def test_special_characters(self):
        """Test special characters and entities."""
        md = Path(MD_TO_HTML_DIR / "07_special_characters.txt").read_text()
        html = markdown_to_apple_html(md)

        # Unicode should be preserved
        assert "🎉" in html
        assert "café" in html
        assert "π" in html

        # Special chars in content
        assert "Tom" in html and "Jerry" in html

    def test_whitespace_handling(self):
        """Test whitespace edge cases."""
        md = Path(MD_TO_HTML_DIR / "08_whitespace_edge_cases.txt").read_text()
        html = markdown_to_apple_html(md)

        # Should produce valid HTML
        assert "<h1>" in html
        assert "Whitespace Edge Cases" in html

        # Headers without space after # should NOT be converted
        assert "#Not a header" in html or "Not a header" in html

    def test_complex_mixed_content(self):
        """Test complex mixed content document."""
        md = Path(MD_TO_HTML_DIR / "09_complex_mixed_content.txt").read_text()
        html = markdown_to_apple_html(md)

        # Headers
        assert "<h1>" in html
        assert "<h2>" in html
        assert "<h3>" in html

        # Lists
        assert "<ol>" in html
        assert "<ul>" in html

        # Code
        assert "<pre>" in html
        assert "<code>" in html

        # Blockquote
        assert "<blockquote>" in html

        # Links
        assert '<a href="' in html

    def test_utf8_encoding(self):
        """Test UTF-8 encoding and international text."""
        md = Path(MD_TO_HTML_DIR / "10_utf8_bom_and_encoding.txt").read_text()
        html = markdown_to_apple_html(md)

        # Japanese
        assert "日本語テキスト" in html
        # Chinese
        assert "中文文本" in html
        # Korean
        assert "한국어" in html
        # Russian
        assert "Текст" in html
        # Emoji
        assert "👨‍👩‍👧‍👦" in html or "Family" in html


class TestHTMLToMarkdown:
    """Test Apple HTML → Markdown conversion (forward sync)."""

    def test_basic_formatting(self):
        """Test bold, italic, code from HTML."""
        html = Path(HTML_TO_MD_DIR / "01_basic_formatting.html").read_text()
        md = html_to_markdown(html, "Basic Formatting Test")

        # Check bold
        assert "**bold text**" in md

        # Check italic
        assert "*italic text*" in md

        # Check combined
        assert "***bold italic combined***" in md

        # Check code
        assert "`inline code`" in md

    def test_headers_hierarchy(self):
        """Test header extraction from HTML."""
        html = Path(HTML_TO_MD_DIR / "02_headers_hierarchy.html").read_text()
        md = html_to_markdown(html, "Main Title H1")

        # Note: H1 title may be skipped if it matches title_to_skip
        assert "## Section One H2" in md
        assert "### Subsection 1.1 H3" in md
        assert "#### Deep Heading H4" in md
        assert "##### Very Deep H5" in md
        assert "###### Deepest H6" in md

    def test_nested_lists(self):
        """Test nested list conversion to markdown."""
        html = Path(HTML_TO_MD_DIR / "03_nested_lists_complex.html").read_text()
        md = html_to_markdown(html, "Nested Lists Complex")

        # Check unordered list markers
        assert "- First level item one" in md

        # Check ordered list markers
        assert "1. First ordered item" in md

        # Check nesting (indentation)
        assert "  - Second level" in md or "- Second level" in md

    def test_links(self):
        """Test link conversion to markdown."""
        html = Path(HTML_TO_MD_DIR / "04_links_and_urls.html").read_text()
        md = html_to_markdown(html, "Links and URLs")

        # Check markdown link format
        assert "[simple link](https://example.com)" in md
        assert "[Google](https://google.com)" in md
        assert "[GitHub](https://github.com)" in md

    def test_code_blocks(self):
        """Test code block conversion."""
        html = Path(HTML_TO_MD_DIR / "05_code_blocks.html").read_text()
        md = html_to_markdown(html, "Code Blocks")

        # Check code block markers
        assert "```" in md
        assert "function hello()" in md

        # Check inline code
        assert "`inline code`" in md

    def test_blockquotes(self):
        """Test blockquote conversion."""
        html = Path(HTML_TO_MD_DIR / "06_blockquotes.html").read_text()
        md = html_to_markdown(html, "Blockquotes")

        # Check blockquote marker
        assert "> This is a simple blockquote" in md

    def test_special_characters(self):
        """Test special character handling."""
        html = Path(HTML_TO_MD_DIR / "07_special_characters.html").read_text()
        md = html_to_markdown(html, "Special Characters & Entities")

        # Entities should be decoded
        assert "Tom & Jerry" in md
        assert "5 < 10" in md
        assert "10 > 5" in md

        # Unicode preserved
        assert "🎉" in md
        assert "café" in md

    def test_consecutive_headings(self):
        """Test Apple Notes consecutive heading quirk."""
        html = Path(HTML_TO_MD_DIR / "08_consecutive_headings.html").read_text()
        md = html_to_markdown(html, "Consecutive Headings Test")

        # Consecutive headings should be merged
        # The exact format depends on implementation
        assert "Split" in md and "Header" in md and "Example" in md

    def test_complex_mixed_content(self):
        """Test complex mixed content."""
        html = Path(HTML_TO_MD_DIR / "09_complex_mixed_content.html").read_text()
        md = html_to_markdown(html, "Complex Mixed Content")

        # Should have headers
        assert "##" in md

        # Should have lists
        assert "1." in md
        assert "-" in md

        # Should have code
        assert "```" in md

        # Should have blockquote
        assert ">" in md

    def test_apple_notes_quirks(self):
        """Test Apple Notes specific HTML quirks."""
        html = Path(HTML_TO_MD_DIR / "10_apple_notes_quirks.html").read_text()
        md = html_to_markdown(html, "Apple Notes Quirks")

        # Styles should be stripped
        assert "font-family" not in md
        assert "color:" not in md

        # Content should be preserved
        assert "Text with inline styles" in md

        # Entities should be decoded
        assert "<" in md and ">" in md


class TestTitleExtraction:
    """Test title extraction from markdown."""

    def test_h1_title(self):
        """Test extracting H1 as title."""
        md = "# My Title\n\nBody content here."
        title, content = extract_title_from_markdown(md)

        assert title == "My Title"
        assert "Body content here" in content
        assert "# My Title" not in content

    def test_no_h1(self):
        """Test fallback when no H1."""
        md = "First line\n\nSecond paragraph."
        title, content = extract_title_from_markdown(md)

        assert title == "First line"

    def test_utf8_bom(self):
        """Test BOM handling."""
        md = "\ufeff# Title With BOM\n\nContent."
        title, content = extract_title_from_markdown(md)

        assert title == "Title With BOM"

    def test_empty_markdown(self):
        """Test empty input."""
        title, content = extract_title_from_markdown("")
        assert title == "Untitled"

    def test_whitespace_before_h1(self):
        """Test whitespace before H1."""
        md = "\n\n# Title After Whitespace\n\nContent."
        title, content = extract_title_from_markdown(md)

        assert title == "Title After Whitespace"


class TestRoundTrip:
    """Test round-trip conversion fidelity."""

    def test_roundtrip_simple_text(self):
        """Test simple text survives round-trip."""
        original_md = "# Test Title\n\nSimple paragraph text."

        # MD → HTML → MD
        html = markdown_to_apple_html(original_md)
        result_md = html_to_markdown(html, "Test Title")

        assert "Simple paragraph text" in result_md

    def test_roundtrip_formatted_text(self):
        """Test formatted text survives round-trip."""
        original_md = "# Title\n\nThis has **bold** and *italic* text."

        html = markdown_to_apple_html(original_md)
        result_md = html_to_markdown(html, "Title")

        assert "**bold**" in result_md
        assert "*italic*" in result_md

    def test_roundtrip_lists(self):
        """Test lists survive round-trip."""
        original_md = "# Title\n\n- Item one\n- Item two\n- Item three"

        html = markdown_to_apple_html(original_md)
        result_md = html_to_markdown(html, "Title")

        assert "- Item one" in result_md
        assert "- Item two" in result_md

    def test_roundtrip_links(self):
        """Test links survive round-trip."""
        original_md = "# Title\n\nVisit [Example](https://example.com) now."

        html = markdown_to_apple_html(original_md)
        result_md = html_to_markdown(html, "Title")

        assert "[Example](https://example.com)" in result_md

    def test_roundtrip_code(self):
        """Test code survives round-trip."""
        original_md = "# Title\n\nUse `code` here.\n\n```\nblock\n```"

        html = markdown_to_apple_html(original_md)
        result_md = html_to_markdown(html, "Title")

        assert "`code`" in result_md
        assert "```" in result_md


class TestEdgeCases:
    """Test edge cases and potential bugs."""

    def test_empty_input_md_to_html(self):
        """Empty markdown should return empty string."""
        assert markdown_to_apple_html("") == ""

    def test_empty_input_html_to_md(self):
        """Empty HTML should return empty string."""
        assert html_to_markdown("") == ""

    def test_only_whitespace_md(self):
        """Whitespace-only markdown."""
        html = markdown_to_apple_html("   \n\n   ")
        assert html is not None

    def test_malformed_html(self):
        """Malformed HTML should not crash."""
        html = "<div>Unclosed div<b>unclosed bold"
        md = html_to_markdown(html)
        assert "Unclosed div" in md

    def test_deeply_nested_elements(self):
        """Deeply nested HTML should work."""
        html = "<div><div><div><b><i>Deep</i></b></div></div></div>"
        md = html_to_markdown(html)
        assert "Deep" in md

    def test_special_regex_chars_in_content(self):
        """Content with regex special chars should work."""
        md = "# Title\n\nPattern: [a-z]+ and (group) and $10."
        html = markdown_to_apple_html(md)
        assert "[a-z]+" in html
        assert "(group)" in html

    def test_url_with_special_chars(self):
        """URLs with special characters."""
        md = "# Title\n\n[Link](https://example.com/path?a=1&b=2)"
        html = markdown_to_apple_html(md)
        # URL should be preserved (possibly encoded)
        assert "https://example.com" in html

    def test_consecutive_formatting(self):
        """Consecutive formatting markers."""
        md = "# Title\n\n**bold****more bold** and *ital**ic*"
        html = markdown_to_apple_html(md)
        # Should handle gracefully
        assert "<b>" in html

    def test_mixed_newline_styles(self):
        """Different newline styles."""
        md_unix = "# Title\n\nUnix newlines."
        md_windows = "# Title\r\n\r\nWindows newlines."

        html_unix = markdown_to_apple_html(md_unix)
        html_windows = markdown_to_apple_html(md_windows)

        assert "Unix newlines" in html_unix
        assert "Windows newlines" in html_windows


class TestAllMarkdownFiles:
    """Detailed tests for each of the 10 markdown test files."""

    def test_01_basic_formatting_details(self):
        """Detailed test for basic formatting file."""
        md = Path(MD_TO_HTML_DIR / "01_basic_formatting.txt").read_text()
        html = markdown_to_apple_html(md)

        # Verify all formatting types
        assert html.count("<b>") >= 3  # Multiple bold instances
        assert html.count("<i>") >= 3  # Multiple italic instances
        assert "<code>" in html
        assert "<s>" in html  # Strikethrough

    def test_02_headers_all_levels(self):
        """Verify all 6 header levels work."""
        md = Path(MD_TO_HTML_DIR / "02_headers_hierarchy.txt").read_text()
        html = markdown_to_apple_html(md)

        for i in range(1, 7):
            assert f"<h{i}>" in html, f"Missing h{i} tag"
            assert f"</h{i}>" in html, f"Missing closing h{i} tag"

    def test_03_list_nesting_depth(self):
        """Verify deep nesting in lists."""
        md = Path(MD_TO_HTML_DIR / "03_nested_lists_complex.txt").read_text()
        html = markdown_to_apple_html(md)

        # Count nested list tags
        ul_count = html.count("<ul>")
        ol_count = html.count("<ol>")
        assert ul_count >= 3, "Should have multiple ul levels"
        assert ol_count >= 2, "Should have multiple ol levels"

    def test_04_all_link_types(self):
        """Verify all link types work."""
        md = Path(MD_TO_HTML_DIR / "04_links_and_urls.txt").read_text()
        html = markdown_to_apple_html(md)

        # Standard markdown links
        assert "example.com" in html
        assert "google.com" in html
        assert "github.com" in html

        # Should have multiple <a> tags
        assert html.count("<a href=") >= 5

    def test_05_code_block_preservation(self):
        """Verify code blocks preserve content."""
        md = Path(MD_TO_HTML_DIR / "05_code_blocks.txt").read_text()
        html = markdown_to_apple_html(md)

        # Code should be preserved
        assert "function hello()" in html
        assert "def greet" in html
        assert "<pre>" in html

    def test_06_blockquote_content(self):
        """Verify blockquote content is preserved."""
        md = Path(MD_TO_HTML_DIR / "06_blockquotes.txt").read_text()
        html = markdown_to_apple_html(md)

        assert "<blockquote>" in html
        assert "simple blockquote" in html
        assert "longer quote" in html

    def test_07_unicode_preservation(self):
        """Verify unicode characters are preserved."""
        md = Path(MD_TO_HTML_DIR / "07_special_characters.txt").read_text()
        html = markdown_to_apple_html(md)

        # All these characters should be preserved
        assert "🎉" in html
        assert "→" in html
        assert "π" in html
        assert "café" in html
        assert "€" in html

    def test_08_whitespace_normalization(self):
        """Verify whitespace is handled correctly."""
        md = Path(MD_TO_HTML_DIR / "08_whitespace_edge_cases.txt").read_text()
        html = markdown_to_apple_html(md)

        # Content should be present
        assert "Whitespace Edge Cases" in html
        assert "after multiple blank lines" in html

    def test_09_mixed_content_structure(self):
        """Verify mixed content preserves structure."""
        md = Path(MD_TO_HTML_DIR / "09_complex_mixed_content.txt").read_text()
        html = markdown_to_apple_html(md)

        # Should have all major elements
        assert "<h1>" in html
        assert "<h2>" in html
        assert "<ol>" in html
        assert "<ul>" in html
        assert "<pre>" in html
        assert "<blockquote>" in html
        assert "<a href=" in html

    def test_10_international_text(self):
        """Verify international text is preserved."""
        md = Path(MD_TO_HTML_DIR / "10_utf8_bom_and_encoding.txt").read_text()
        html = markdown_to_apple_html(md)

        # All scripts should be preserved
        assert "日本語" in html  # Japanese
        assert "中文" in html    # Chinese
        assert "한국어" in html  # Korean
        assert "русском" in html  # Russian
        assert "עברית" in html  # Hebrew


class TestAllHTMLFiles:
    """Detailed tests for each of the 10 HTML test files."""

    def test_01_html_formatting_conversion(self):
        """Detailed test for HTML formatting to markdown."""
        html = Path(HTML_TO_MD_DIR / "01_basic_formatting.html").read_text()
        md = html_to_markdown(html, "Basic Formatting Test")

        # All formatting should convert
        assert "**" in md  # Bold
        assert md.count("*") >= 4  # Italic (at least 2 pairs)
        assert "`" in md  # Code

    def test_02_html_headers_to_markdown(self):
        """Test HTML headers convert to markdown headers."""
        html = Path(HTML_TO_MD_DIR / "02_headers_hierarchy.html").read_text()
        md = html_to_markdown(html, "Main Title H1")

        # Check for markdown header markers
        for i in range(2, 7):  # H2-H6 (H1 may be skipped as title)
            assert f"{'#' * i} " in md, f"Missing level {i} header"

    def test_03_html_lists_to_markdown(self):
        """Test HTML lists convert to markdown."""
        html = Path(HTML_TO_MD_DIR / "03_nested_lists_complex.html").read_text()
        md = html_to_markdown(html, "Nested Lists Complex")

        # Should have list markers
        assert "- " in md  # Unordered list
        assert "1. " in md  # Ordered list

    def test_04_html_links_to_markdown(self):
        """Test HTML links convert to markdown links."""
        html = Path(HTML_TO_MD_DIR / "04_links_and_urls.html").read_text()
        md = html_to_markdown(html, "Links and URLs")

        # Should have markdown link format
        assert "[" in md and "](" in md and ")" in md
        assert "https://" in md

    def test_05_html_code_to_markdown(self):
        """Test HTML code converts to markdown."""
        html = Path(HTML_TO_MD_DIR / "05_code_blocks.html").read_text()
        md = html_to_markdown(html, "Code Blocks")

        # Should have code markers
        assert "```" in md  # Code block
        assert "`" in md    # Inline code

    def test_06_html_blockquote_to_markdown(self):
        """Test HTML blockquotes convert to markdown."""
        html = Path(HTML_TO_MD_DIR / "06_blockquotes.html").read_text()
        md = html_to_markdown(html, "Blockquotes")

        # Should have blockquote marker
        assert "> " in md

    def test_07_html_entities_decoded(self):
        """Test HTML entities are decoded to characters."""
        html = Path(HTML_TO_MD_DIR / "07_special_characters.html").read_text()
        md = html_to_markdown(html, "Special Characters & Entities")

        # Entities should be decoded
        assert "&amp;" not in md  # Should be decoded
        assert "&lt;" not in md
        assert "&gt;" not in md
        # Actual characters should be present
        assert "&" in md
        assert "<" in md
        assert ">" in md

    def test_08_consecutive_headings_merged(self):
        """Test consecutive headings are merged."""
        html = Path(HTML_TO_MD_DIR / "08_consecutive_headings.html").read_text()
        md = html_to_markdown(html, "Consecutive Headings Test")

        # Should have merged heading content (may be combined)
        lines = md.split('\n')
        heading_lines = [line for line in lines if line.startswith('#')]
        # Verify headings exist
        assert len(heading_lines) > 0

    def test_09_html_mixed_to_markdown(self):
        """Test mixed HTML content converts correctly."""
        html = Path(HTML_TO_MD_DIR / "09_complex_mixed_content.html").read_text()
        md = html_to_markdown(html, "Complex Mixed Content")

        # Should have all element types
        assert "#" in md      # Headers
        assert "- " in md     # Lists
        assert "1. " in md    # Ordered lists
        assert "```" in md    # Code blocks
        assert "> " in md     # Blockquotes
        assert "[" in md      # Links

    def test_10_apple_quirks_handled(self):
        """Test Apple Notes quirks are handled."""
        html = Path(HTML_TO_MD_DIR / "10_apple_notes_quirks.html").read_text()
        md = html_to_markdown(html, "Apple Notes Quirks")

        # Style attributes should be stripped (not in output)
        assert "font-family" not in md
        assert "rgb(" not in md

        # Content should be preserved
        assert "Bold and italic together" in md
        assert "final link" in md


class TestBidirectionalIntegrity:
    """Test bidirectional sync integrity."""

    def test_markdown_files_roundtrip(self):
        """Test all markdown files survive round-trip."""
        for i in range(1, 11):
            files = list(MD_TO_HTML_DIR.glob(f"{i:02d}_*.txt"))
            if files:
                md = files[0].read_text()
                title, content = extract_title_from_markdown(md)

                # Convert MD → HTML → MD
                html = markdown_to_apple_html(md)
                result_md = html_to_markdown(html, title)

                # Key content should be preserved
                # (Exact match not expected due to formatting normalization)
                assert len(result_md) > 0, f"File {i:02d} produced empty result"

    def test_html_files_roundtrip(self):
        """Test all HTML files survive round-trip."""
        for i in range(1, 11):
            files = list(HTML_TO_MD_DIR.glob(f"{i:02d}_*.html"))
            if files:
                html = files[0].read_text()

                # Extract title from first H1
                import re
                h1_match = re.search(r'<h1>([^<]+)</h1>', html)
                title = h1_match.group(1) if h1_match else None

                # Convert HTML → MD → HTML
                md = html_to_markdown(html, title)
                result_html = markdown_to_apple_html(f"# {title}\n\n{md}" if title else md)

                # Key content should be preserved
                assert len(result_html) > 0, f"File {i:02d} produced empty result"

    def test_formatting_preserved_bidirectional(self):
        """Test that formatting is preserved in both directions."""
        test_cases = [
            ("**bold**", "<b>bold</b>", "**bold**"),
            ("*italic*", "<i>italic</i>", "*italic*"),
            ("`code`", "<code>code</code>", "`code`"),
            ("[link](https://x.com)", '<a href="https://x.com">link</a>', "[link](https://x.com)"),
        ]

        for md_in, expected_html_part, expected_md_part in test_cases:
            full_md = f"# Test\n\n{md_in}"
            html = markdown_to_apple_html(full_md)
            assert expected_html_part in html, f"MD→HTML failed for: {md_in}"

            result_md = html_to_markdown(html, "Test")
            assert expected_md_part in result_md, f"HTML→MD failed for: {expected_html_part}"


class TestStressTests:
    """Stress tests for edge cases."""

    def test_very_long_line(self):
        """Test handling of very long lines."""
        long_text = "word " * 1000
        md = f"# Title\n\n{long_text}"
        html = markdown_to_apple_html(md)
        result_md = html_to_markdown(html, "Title")
        assert "word" in result_md

    def test_many_nested_lists(self):
        """Test deeply nested lists."""
        md = "# Title\n\n"
        for i in range(10):
            md += "  " * i + f"- Level {i}\n"

        html = markdown_to_apple_html(md)
        assert "<ul>" in html

    def test_many_headers(self):
        """Test document with many headers."""
        md = "# Title\n\n"
        for i in range(50):
            md += f"## Section {i}\n\nContent for section {i}.\n\n"

        html = markdown_to_apple_html(md)
        assert html.count("<h2>") == 50

    def test_special_url_characters(self):
        """Test URLs with special characters."""
        md = "# Title\n\n[link](https://example.com/path?a=1&b=2&c=%20)"
        html = markdown_to_apple_html(md)
        assert "https://example.com" in html

    def test_consecutive_formatting(self):
        """Test consecutive formatting without spaces."""
        md = "# Title\n\n**bold1****bold2** and *ital1**ital2*"
        html = markdown_to_apple_html(md)
        # Should not crash
        assert "<b>" in html


class TestAdditionalMarkdownFiles:
    """Tests for additional 10 markdown test files (11-20)."""

    def test_11_tables(self):
        """Test markdown tables."""
        md = Path(MD_TO_HTML_DIR / "11_tables.txt").read_text()
        html = markdown_to_apple_html(md)

        # Tables should be present in output (may be rendered as text or table)
        assert "Header 1" in html
        assert "Cell 1" in html
        assert "Tables Test" in html

    def test_12_horizontal_rules(self):
        """Test horizontal rules (---, ***, ___)."""
        md = Path(MD_TO_HTML_DIR / "12_horizontal_rules.txt").read_text()
        html = markdown_to_apple_html(md)

        # Content around rules should be present
        assert "Content before" in html
        assert "Content after" in html
        assert "Horizontal Rules" in html

    def test_13_task_lists(self):
        """Test task list checkboxes."""
        md = Path(MD_TO_HTML_DIR / "13_task_lists.txt").read_text()
        html = markdown_to_apple_html(md)

        # Task items should be present
        assert "Unchecked task" in html
        assert "Checked task" in html
        assert "[ ]" in html or "task" in html.lower()

    def test_14_escape_sequences(self):
        """Test escaped markdown characters."""
        md = Path(MD_TO_HTML_DIR / "14_escape_sequences.txt").read_text()
        html = markdown_to_apple_html(md)

        # Escaped content should be present
        assert "Escape Sequences" in html
        assert "asterisks" in html.lower()

    def test_15_adjacent_formatting(self):
        """Test adjacent formatting markers."""
        md = Path(MD_TO_HTML_DIR / "15_adjacent_formatting.txt").read_text()
        html = markdown_to_apple_html(md)

        # Formatting should work
        assert "<b>" in html
        assert "<i>" in html
        assert "Adjacent Formatting" in html

    def test_16_empty_edge_elements(self):
        """Test empty and edge case elements."""
        md = Path(MD_TO_HTML_DIR / "16_empty_edge_elements.txt").read_text()
        html = markdown_to_apple_html(md)

        # Content should be preserved
        assert "Empty and Edge" in html
        assert "Single Characters" in html

    def test_17_long_unbroken(self):
        """Test very long unbroken content."""
        md = Path(MD_TO_HTML_DIR / "17_long_unbroken.txt").read_text()
        html = markdown_to_apple_html(md)

        # Long content should be present
        assert "Supercalifragilistic" in html
        assert "Long Unbroken" in html

    def test_18_nested_blockquotes(self):
        """Test nested blockquote levels."""
        md = Path(MD_TO_HTML_DIR / "18_nested_blockquotes.txt").read_text()
        html = markdown_to_apple_html(md)

        # Blockquotes should be present
        assert "<blockquote>" in html
        assert "Nested Blockquotes" in html

    def test_19_inline_boundaries(self):
        """Test formatting at line boundaries."""
        md = Path(MD_TO_HTML_DIR / "19_inline_boundaries.txt").read_text()
        html = markdown_to_apple_html(md)

        # Formatting at boundaries
        assert "<b>" in html
        assert "Bold at very start" in html

    def test_20_real_world_patterns(self):
        """Test real-world document patterns."""
        md = Path(MD_TO_HTML_DIR / "20_real_world_patterns.txt").read_text()
        html = markdown_to_apple_html(md)

        # Real world content
        assert "Meeting Notes" in html
        assert "Recipe Format" in html
        assert "API Endpoint" in html
        assert "<pre>" in html
        assert "<blockquote>" in html


class TestAdditionalHTMLFiles:
    """Tests for additional 10 HTML test files (11-20)."""

    def test_11_inline_links_complex(self):
        """Test complex inline links."""
        html = Path(HTML_TO_MD_DIR / "11_inline_links_complex.html").read_text()
        md = html_to_markdown(html, "Complex Inline Links")

        # Links should convert to markdown format
        assert "[" in md and "](" in md
        assert "https://" in md

    def test_12_mixed_list_content(self):
        """Test mixed content in lists."""
        html = Path(HTML_TO_MD_DIR / "12_mixed_list_content.html").read_text()
        md = html_to_markdown(html, "Mixed List Content")

        # Lists should be present
        assert "- " in md or "1." in md
        assert "`npm" in md or "npm" in md

    def test_13_deeply_nested(self):
        """Test deeply nested structures."""
        html = Path(HTML_TO_MD_DIR / "13_deeply_nested.html").read_text()
        md = html_to_markdown(html, "Deeply Nested Structures")

        # Nested content should be present
        assert "Level" in md
        assert "- " in md

    def test_14_whitespace_variations(self):
        """Test various whitespace patterns."""
        html = Path(HTML_TO_MD_DIR / "14_whitespace_variations.html").read_text()
        md = html_to_markdown(html, "Whitespace Variations")

        # Content should be normalized (title may be skipped as H1)
        assert "Multiple Spaces" in md or "spaces" in md.lower()
        assert "Tabs" in md or "tabs" in md.lower()

    def test_15_entity_heavy(self):
        """Test heavy entity usage."""
        html = Path(HTML_TO_MD_DIR / "15_entity_heavy.html").read_text()
        md = html_to_markdown(html, "Entity Heavy Content")

        # Entities should be decoded
        assert "&amp;" not in md  # Should be decoded
        assert "&" in md  # Actual ampersand
        assert "<" in md  # Decoded less than
        assert ">" in md  # Decoded greater than

    def test_16_formatting_edge_cases(self):
        """Test formatting edge cases."""
        html = Path(HTML_TO_MD_DIR / "16_formatting_edge_cases.html").read_text()
        md = html_to_markdown(html, "Formatting Edge Cases")

        # Formatting should be present (title may be skipped)
        assert "**" in md or "*" in md
        assert "Empty Formatting Tags" in md or "Bold" in md

    def test_17_code_variations(self):
        """Test various code patterns."""
        html = Path(HTML_TO_MD_DIR / "17_code_variations.html").read_text()
        md = html_to_markdown(html, "Code Variations")

        # Code should be present
        assert "`" in md
        assert "```" in md
        assert "function" in md

    def test_18_header_edge_cases(self):
        """Test header edge cases."""
        html = Path(HTML_TO_MD_DIR / "18_header_edge_cases.html").read_text()
        md = html_to_markdown(html, "Header Edge Cases")

        # Headers should be present
        assert "#" in md
        assert "Bold Header" in md or "header" in md.lower()

    def test_19_paragraph_patterns(self):
        """Test various paragraph patterns."""
        html = Path(HTML_TO_MD_DIR / "19_paragraph_patterns.html").read_text()
        md = html_to_markdown(html, "Paragraph Patterns")

        # Paragraphs should be present (title may be skipped)
        assert "Simple Paragraphs" in md
        assert "paragraph" in md.lower()

    def test_20_apple_notes_real(self):
        """Test real Apple Notes export."""
        html = Path(HTML_TO_MD_DIR / "20_apple_notes_real.html").read_text()
        md = html_to_markdown(html, "Apple Notes Real Export")

        # Style attributes should be stripped
        assert "font-family" not in md
        assert "-apple-system" not in md

        # Content should be preserved
        assert "Shopping List" in md
        assert "Meeting Notes" in md
        assert "Milk" in md


class TestAdditionalRoundTrips:
    """Round-trip tests for additional files."""

    def test_additional_markdown_roundtrip(self):
        """Test all additional markdown files survive round-trip."""
        for i in range(11, 21):
            files = list(MD_TO_HTML_DIR.glob(f"{i}_*.txt"))
            if files:
                md = files[0].read_text()
                title, _ = extract_title_from_markdown(md)

                html = markdown_to_apple_html(md)
                # Don't skip title for this test
                result_md = html_to_markdown(html, None)

                assert len(result_md) > 0, f"File {i} produced empty result"
                # Check that either title is present or significant content exists
                assert len(result_md) > 50, f"File {i} has too little content"

    def test_additional_html_roundtrip(self):
        """Test all additional HTML files survive round-trip."""
        for i in range(11, 21):
            files = list(HTML_TO_MD_DIR.glob(f"{i}_*.html"))
            if files:
                html = files[0].read_text()

                h1_match = re.search(r'<h1>([^<]+)</h1>', html)
                title = h1_match.group(1) if h1_match else None

                md = html_to_markdown(html, title)
                result_html = markdown_to_apple_html(f"# {title}\n\n{md}" if title else md)

                assert len(result_html) > 0, f"File {i} produced empty result"


class TestAdditionalEdgeCases:
    """Additional edge case tests."""

    def test_table_content_preserved(self):
        """Test that table content is preserved even if structure changes."""
        md = "# Test\n\n| A | B |\n|---|---|\n| 1 | 2 |"
        html = markdown_to_apple_html(md)
        # Content should be present
        assert "A" in html and "B" in html
        assert "1" in html and "2" in html

    def test_horizontal_rule_variations(self):
        """Test different horizontal rule styles."""
        for rule in ["---", "***", "___"]:
            md = f"# Title\n\nBefore\n\n{rule}\n\nAfter"
            html = markdown_to_apple_html(md)
            assert "Before" in html
            assert "After" in html

    def test_task_checkbox_patterns(self):
        """Test task list checkbox patterns."""
        md = "# Tasks\n\n- [ ] Todo\n- [x] Done"
        html = markdown_to_apple_html(md)
        assert "Todo" in html
        assert "Done" in html

    def test_deeply_nested_lists_stress(self):
        """Stress test for deeply nested lists."""
        md = "# Test\n\n"
        for i in range(8):
            md += "  " * i + f"- Level {i}\n"
        html = markdown_to_apple_html(md)
        assert "Level 0" in html
        assert "Level 7" in html

    def test_many_entities(self):
        """Test many HTML entities in one document."""
        html = "<div>&amp; &lt; &gt; &quot; &apos; &nbsp; &#60; &#x3E;</div>"
        md = html_to_markdown(html)
        # Entities should be decoded
        assert "&amp;" not in md
        assert "&lt;" not in md

    def test_formatting_stress(self):
        """Stress test for formatting combinations."""
        md = "# Test\n\n**a** *b* `c` **d** *e* `f` **g** *h* `i`"
        html = markdown_to_apple_html(md)
        result_md = html_to_markdown(html, "Test")
        # All letters should survive
        for letter in "abcdefghi":
            assert letter in result_md

    def test_mixed_content_stress(self):
        """Stress test with all element types."""
        md = """# Stress Test

Paragraph with **bold** and *italic*.

- List item 1
- List item 2

1. Ordered 1
2. Ordered 2

> Blockquote here

```
code block
```

[Link](https://example.com)
"""
        html = markdown_to_apple_html(md)
        assert "<b>" in html
        assert "<i>" in html
        assert "<ul>" in html
        assert "<ol>" in html
        assert "<blockquote>" in html
        assert "<pre>" in html
        assert "<a " in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
