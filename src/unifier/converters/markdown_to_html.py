"""
Markdown to Apple Notes HTML converter.

Converts Markdown format back to Apple Notes HTML for reverse sync.
"""

import re


def markdown_to_apple_html(markdown: str) -> str:
    """
    Convert Markdown to Apple Notes HTML format.

    Apple Notes uses specific HTML patterns:
    - <h1>-<h6> for headers
    - <ul>/<ol> for lists
    - <div><br></div> for blank lines
    - <b>/<i> for bold/italic
    - <a href="...">text</a> for links
    - <br> for line breaks

    Args:
        markdown: Markdown-formatted text

    Returns:
        HTML string suitable for Apple Notes
    """
    if not markdown:
        return ""

    lines = markdown.split('\n')
    html_parts: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check for code blocks
        if line.startswith('```'):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                code_lines.append(lines[i])
                i += 1
            html_parts.append(_convert_code_block(code_lines))
            i += 1
            continue

        # Check for headers (must be at start of line)
        header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if header_match:
            level = len(header_match.group(1))
            text = header_match.group(2)
            html_parts.append(f'<h{level}>{_convert_inline(text)}</h{level}>')
            i += 1
            continue

        # Check for unordered list
        if re.match(r'^(\s*)-\s+', line):
            list_lines = []
            while i < len(lines) and (re.match(r'^(\s*)-\s+', lines[i]) or
                                       (lines[i].strip() == '' and i + 1 < len(lines) and
                                        re.match(r'^(\s*)-\s+', lines[i + 1]))):
                list_lines.append(lines[i])
                i += 1
            html_parts.append(_convert_unordered_list(list_lines))
            continue

        # Check for ordered list
        if re.match(r'^(\s*)\d+\.\s+', line):
            list_lines = []
            while i < len(lines) and (re.match(r'^(\s*)\d+\.\s+', lines[i]) or
                                       (lines[i].strip() == '' and i + 1 < len(lines) and
                                        re.match(r'^(\s*)\d+\.\s+', lines[i + 1]))):
                list_lines.append(lines[i])
                i += 1
            html_parts.append(_convert_ordered_list(list_lines))
            continue

        # Check for blockquote
        if line.startswith('>'):
            quote_lines = []
            while i < len(lines) and lines[i].startswith('>'):
                quote_lines.append(lines[i][1:].lstrip())
                i += 1
            html_parts.append(f'<blockquote>{_convert_inline(" ".join(quote_lines))}</blockquote>')
            continue

        # Blank line
        if not line.strip():
            html_parts.append('<div><br></div>')
            i += 1
            continue

        # Regular paragraph
        para_lines = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not _is_block_element(lines[i]):
            para_lines.append(lines[i])
            i += 1

        text = ' '.join(para_lines)
        html_parts.append(f'<div>{_convert_inline(text)}</div>')

    return ''.join(html_parts)


def _is_block_element(line: str) -> bool:
    """Check if line starts a block element."""
    if line.startswith('#'):
        return True
    if re.match(r'^(\s*)-\s+', line):
        return True
    if re.match(r'^(\s*)\d+\.\s+', line):
        return True
    if line.startswith('>'):
        return True
    if line.startswith('```'):
        return True
    return False


def _convert_inline(text: str) -> str:
    """Convert inline Markdown formatting to HTML."""
    if not text:
        return ""

    # Escape HTML entities first (but preserve existing ones)
    # text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Bold and italic combined: ***text*** or ___text___
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)
    text = re.sub(r'___(.+?)___', r'<b><i>\1</i></b>', text)

    # Bold: **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

    # Italic: *text* or _text_ (but not in the middle of words)
    text = re.sub(r'(?<!\w)\*([^*]+?)\*(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!\w)_([^_]+?)_(?!\w)', r'<i>\1</i>', text)

    # Inline code: `code`
    text = re.sub(r'`([^`]+?)`', r'<code>\1</code>', text)

    # Links: [text](url)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

    # Auto-link plain URLs (not already in href="...")
    # Match http/https URLs that aren't already inside an href attribute
    text = re.sub(
        r'(?<!href=")(?<!href=\')(https?://[^\s<>"\'\)]+)',
        r'<a href="\1">\1</a>',
        text
    )

    # Strikethrough: ~~text~~
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)

    return text


def _convert_code_block(lines: list[str]) -> str:
    """Convert code block to HTML."""
    code = '\n'.join(lines)
    return f'<pre>{code}</pre>'


def _convert_unordered_list(lines: list[str]) -> str:
    """Convert unordered list to HTML."""
    items = _parse_list_items(lines, ordered=False)
    return _build_list_html(items, ordered=False)


def _convert_ordered_list(lines: list[str]) -> str:
    """Convert ordered list to HTML."""
    items = _parse_list_items(lines, ordered=True)
    return _build_list_html(items, ordered=True)


def _parse_list_items(lines: list[str], ordered: bool) -> list[tuple[int, str]]:
    """Parse list items with their indent levels."""
    items = []

    for line in lines:
        if not line.strip():
            continue

        # Count leading spaces for indent level
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        level = indent // 2  # 2 spaces per level

        # Remove list marker
        if ordered:
            text = re.sub(r'^\d+\.\s+', '', stripped)
        else:
            text = re.sub(r'^-\s+', '', stripped)

        items.append((level, text))

    return items


def _build_list_html(items: list[tuple[int, str]], ordered: bool) -> str:
    """Build nested list HTML from items."""
    if not items:
        return ""

    tag = 'ol' if ordered else 'ul'
    result = [f'<{tag}>']
    current_level = 0

    for level, text in items:
        # Handle nesting
        while level > current_level:
            result.append(f'<{tag}>')
            current_level += 1
        while level < current_level:
            result.append(f'</{tag}></li>')
            current_level -= 1

        result.append(f'<li>{_convert_inline(text)}')

    # Close remaining lists
    while current_level > 0:
        result.append(f'</li></{tag}>')
        current_level -= 1
    result.append(f'</li></{tag}>')

    return ''.join(result)


def extract_title_from_markdown(markdown: str) -> tuple[str, str]:
    """
    Extract H1 title from markdown and return (title, remaining_content).

    Args:
        markdown: Full markdown text

    Returns:
        Tuple of (title, content_without_title)
    """
    # Strip UTF-8 BOM if present
    if markdown.startswith('\ufeff'):
        markdown = markdown[1:]

    lines = markdown.split('\n')

    for i, line in enumerate(lines):
        match = re.match(r'^#\s+(.+)$', line.strip())
        if match:
            title = match.group(1)
            # Remove the title line and any immediately following blank lines
            remaining = lines[:i] + lines[i + 1:]
            while remaining and not remaining[0].strip():
                remaining = remaining[1:]
            return title, '\n'.join(remaining)

    # No H1 found, use first non-empty line as title
    for i, line in enumerate(lines):
        if line.strip():
            remaining = lines[:i] + lines[i + 1:]
            return line.strip(), '\n'.join(remaining)

    return "Untitled", markdown
