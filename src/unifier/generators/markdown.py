"""
Markdown/TXT generator for Supernote.

Creates .txt files with Markdown formatting from Apple Notes content.
Supernote can view TXT files natively.
"""

import logging
import re
from html.parser import HTMLParser
from pathlib import Path

from .base import BaseGenerator, GeneratorResult, GeneratorType, NoteContent

logger = logging.getLogger(__name__)


class HTMLToMarkdownParser(HTMLParser):
    """Parse Apple Notes HTML and convert to Markdown."""

    def __init__(self, title_to_skip: str | None = None):
        super().__init__()
        self.output = []
        self.is_bold = False
        self.is_italic = False
        self.is_code = False
        self.in_pre = False
        self.list_stack = []  # Track nested lists: 'ul' or 'ol'
        self.ol_counters = []  # Track ordered list counters
        self.pending_newlines = 0
        self.current_heading = 0
        self.current_link_href = None  # Track current link URL

        # Track title to skip (already added as H1)
        self.title_to_skip = title_to_skip.lower().strip() if title_to_skip else None
        self.title_skipped = False

        # Track consecutive heading fragments for merging
        self.in_consecutive_headings = False
        self.consecutive_heading_level = 0
        self.consecutive_heading_text = []

    def _add_text(self, text: str):
        """Add text with current formatting."""
        if not text:
            return

        # Apply inline formatting
        if self.is_code:
            text = f'`{text}`'
        if self.is_bold and self.is_italic:
            text = f'***{text}***'
        elif self.is_bold:
            text = f'**{text}**'
        elif self.is_italic:
            text = f'*{text}*'

        self.output.append(text)

    def _add_newlines(self, count: int = 1):
        """Queue newlines (deduplicated on output)."""
        self.pending_newlines = max(self.pending_newlines, count)

    def _flush_newlines(self):
        """Flush pending newlines."""
        if self.pending_newlines > 0:
            self.output.append('\n' * self.pending_newlines)
            self.pending_newlines = 0

    def _flush_consecutive_headings(self):
        """Flush accumulated consecutive heading text as a single heading."""
        if not self.in_consecutive_headings or not self.consecutive_heading_text:
            self.in_consecutive_headings = False
            return

        merged_text = ''.join(self.consecutive_heading_text).strip()

        # Check if this heading matches the title we should skip
        # Apple Notes often puts the title (or part of it) in the body as a heading
        if self.title_to_skip and not self.title_skipped:
            # Normalize both for comparison (remove special chars, lowercase)
            merged_normalized = re.sub(r'[^\w\s]', '', merged_text.lower()).strip()
            title_normalized = re.sub(r'[^\w\s]', '', self.title_to_skip).strip()
            # Check if heading matches title or is a significant suffix of it
            # (e.g., title="#GMC Tire Pressure", body heading="Tire Pressure")
            if (merged_normalized == title_normalized or
                merged_text.lower().strip() == self.title_to_skip or
                (len(merged_normalized) >= 3 and title_normalized.endswith(merged_normalized))):
                self.title_skipped = True
                self.in_consecutive_headings = False
                self.consecutive_heading_text = []
                return

        if merged_text:
            self._flush_newlines()
            self.output.append('\n\n')
            self.output.append('#' * self.consecutive_heading_level + ' ')
            self.output.append(merged_text)
            self._add_newlines(2)

        self.in_consecutive_headings = False
        self.consecutive_heading_text = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if tag == 'br':
            # br inside heading continues accumulation
            if not self.in_consecutive_headings:
                self.output.append('\n')
        elif tag == 'p':
            self._flush_consecutive_headings()
            self._flush_newlines()
            self._add_newlines(2)
        elif tag == 'div':
            # Flush any pending consecutive headings before processing div content
            self._flush_consecutive_headings()
            self._flush_newlines()
            self._add_newlines(1)
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(tag[1])
            # Check if this is a consecutive heading at the same level
            if self.in_consecutive_headings and level == self.consecutive_heading_level:
                # Continue accumulating text for merged heading
                pass
            else:
                # Flush any previous consecutive headings
                self._flush_consecutive_headings()
                # Start new heading (might be consecutive)
                self.in_consecutive_headings = True
                self.consecutive_heading_level = level
                self.consecutive_heading_text = []
            self.current_heading = level
        elif tag in ('b', 'strong'):
            self.is_bold = True
        elif tag in ('i', 'em'):
            self.is_italic = True
        elif tag == 'code':
            self.is_code = True
        elif tag == 'pre':
            self._flush_consecutive_headings()
            self._flush_newlines()
            self._add_newlines(2)
            self.output.append('```\n')
            self.in_pre = True
        elif tag == 'ul':
            self._flush_consecutive_headings()
            self._flush_newlines()
            if not self.list_stack:
                self._add_newlines(2)
            self.list_stack.append('ul')
        elif tag == 'ol':
            self._flush_consecutive_headings()
            self._flush_newlines()
            if not self.list_stack:
                self._add_newlines(2)
            self.list_stack.append('ol')
            self.ol_counters.append(1)
        elif tag == 'li':
            self._flush_consecutive_headings()
            self._flush_newlines()
            indent = '  ' * (len(self.list_stack) - 1)
            if self.list_stack and self.list_stack[-1] == 'ol':
                counter = self.ol_counters[-1] if self.ol_counters else 1
                self.output.append(f'{indent}{counter}. ')
                if self.ol_counters:
                    self.ol_counters[-1] += 1
            else:
                self.output.append(f'{indent}- ')
        elif tag == 'a':
            self._flush_consecutive_headings()
            self._flush_newlines()  # Flush before the [ to keep link together
            # Start of link - store href and open bracket
            for name, value in attrs:
                if name == 'href':
                    self.current_link_href = value
                    self.output.append('[')
                    break
        elif tag == 'blockquote':
            self._flush_consecutive_headings()
            self._flush_newlines()
            self._add_newlines(2)
            self.output.append('> ')

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in ('p', 'div'):
            self._add_newlines(2)
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            # Heading end - text already captured in consecutive_heading_text
            # Don't flush yet - wait to see if more consecutive headings follow
            self.current_heading = 0
        elif tag in ('b', 'strong'):
            self.is_bold = False
        elif tag in ('i', 'em'):
            self.is_italic = False
        elif tag == 'code':
            self.is_code = False
        elif tag == 'pre':
            self.in_pre = False
            self.output.append('\n```')
            self._add_newlines(2)
        elif tag == 'ul':
            if self.list_stack and self.list_stack[-1] == 'ul':
                self.list_stack.pop()
            if not self.list_stack:
                self._add_newlines(2)
        elif tag == 'ol':
            if self.list_stack and self.list_stack[-1] == 'ol':
                self.list_stack.pop()
            if self.ol_counters:
                self.ol_counters.pop()
            if not self.list_stack:
                self._add_newlines(2)
        elif tag == 'li':
            self._add_newlines(1)
        elif tag == 'blockquote':
            self._add_newlines(2)
        elif tag == 'a':
            # Close link with URL
            if self.current_link_href:
                self.output.append(f']({self.current_link_href})')
                self.current_link_href = None

    def handle_data(self, data):
        if self.in_pre:
            # Preserve whitespace in pre blocks
            self.output.append(data)
        elif self.in_consecutive_headings:
            # Accumulate heading text for potential merging
            text = ' '.join(data.split())
            if text:
                self.consecutive_heading_text.append(text)
        else:
            # Check if there was leading whitespace in original
            has_leading_space = data and data[0] in ' \t\n'
            has_trailing_space = data and data[-1] in ' \t\n'

            # Normalize whitespace
            text = ' '.join(data.split())
            if text:
                self._flush_newlines()
                # Add leading space if needed to separate from previous content
                if has_leading_space and self.output and self.output[-1] and self.output[-1][-1] not in ' \t\n':
                    self.output.append(' ')
                self._add_text(text)
                # Add trailing space if needed
                if has_trailing_space:
                    self.output.append(' ')

    def handle_entityref(self, name):
        import html
        char = html.unescape(f'&{name};')
        self.handle_data(char)

    def handle_charref(self, name):
        import html
        char = html.unescape(f'&#{name};')
        self.handle_data(char)

    def get_markdown(self) -> str:
        """Get the final Markdown output."""
        # Flush any remaining consecutive headings
        self._flush_consecutive_headings()
        result = ''.join(self.output)
        # Clean up excessive newlines
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()


class MarkdownGenerator(BaseGenerator):
    """Generate Markdown .txt files for Supernote."""

    def __init__(self, output_base: Path):
        super().__init__(output_base)

    @property
    def generator_type(self) -> GeneratorType:
        return GeneratorType.TEXT

    def supports_formatting(self) -> bool:
        return True

    def generate(self, content: NoteContent, relative_path: str) -> GeneratorResult:
        """Generate a Markdown .txt file from note content."""
        try:
            # Change extension to .txt
            if relative_path.endswith('.note'):
                relative_path = relative_path[:-5] + '.txt'
            elif not relative_path.endswith('.txt'):
                relative_path += '.txt'

            output_path = self.output_base / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Convert to Markdown
            markdown = self._convert_to_markdown(content)

            # Write file
            output_path.write_text(markdown, encoding='utf-8')

            # Preserve Apple Notes modification timestamp
            self._set_file_timestamp(output_path, content.modified_at)

            logger.info(f"Created Markdown TXT: {output_path}")

            return GeneratorResult(
                success=True,
                output_path=output_path,
                error=None,
                pages_created=1
            )

        except Exception as e:
            logger.exception(f"Failed to generate Markdown: {content.title}")
            return GeneratorResult(
                success=False,
                output_path=None,
                error=str(e),
                pages_created=0
            )

    def _convert_to_markdown(self, content: NoteContent) -> str:
        """Convert note content to Markdown."""
        parts = []

        # Title as H1
        parts.append(f'# {content.title}')
        parts.append('')

        # Body
        if content.html:
            body = self._html_to_markdown(content.html, content.title)
            # Strip duplicate title at start of body (common in Apple Notes)
            body = self._strip_duplicate_title(body, content.title)
            parts.append(body)
        elif content.plain_text:
            # Strip duplicate title from plain text too
            plain = self._strip_duplicate_title(content.plain_text, content.title)
            parts.append(plain)

        return '\n'.join(parts)

    def _strip_duplicate_title(self, text: str, title: str) -> str:
        """Remove duplicate title from start of body text."""
        if not text or not title:
            return text

        lines = text.split('\n')
        if not lines:
            return text

        # Normalize for comparison
        first_line = lines[0].strip()
        title_normalized = re.sub(r'^#+\s*', '', title).strip()  # Remove leading # if present

        # Check if first line is the title (exact or close match)
        if (first_line.lower() == title_normalized.lower() or
            first_line.lower() == title.lower()):
            # Remove first line and any following blank lines
            lines = lines[1:]
            while lines and not lines[0].strip():
                lines = lines[1:]
            return '\n'.join(lines)

        return text

    def _html_to_markdown(self, html: str, title: str | None = None) -> str:
        """Convert HTML to Markdown."""
        # Clean up Apple Notes HTML
        html = self._clean_html(html)

        parser = HTMLToMarkdownParser(title_to_skip=title)
        try:
            parser.feed(html)
            return parser.get_markdown()
        except Exception as e:
            logger.warning(f"HTML parsing failed, stripping tags: {e}")
            # Fallback: strip tags
            text = re.sub(r'<[^>]+>', ' ', html)
            return ' '.join(text.split())

    def _clean_html(self, html: str) -> str:
        """Clean up Apple Notes HTML quirks."""
        # Remove style/class attributes
        html = re.sub(r'\s+style\s*=\s*["\'][^"\']*["\']', '', html)
        html = re.sub(r'\s+class\s*=\s*["\'][^"\']*["\']', '', html)
        return html
