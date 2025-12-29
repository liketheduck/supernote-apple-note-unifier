# Testing Criteria for Apple Notes ↔ Supernote Sync

This document provides comprehensive testing instructions for verifying bidirectional sync integrity after Apple Notes or Supernote updates.

## Quick Start

```bash
# Run all automated tests
source .venv/bin/activate
pytest tests/test_conversions.py -v

# Generate visual samples for manual inspection
python tests/generate_visual_samples.py

# Run linting
ruff check src/
mypy src/
```

---

## Part 1: Automated Test Suite

### Test File Locations

| Directory | Purpose |
|-----------|---------|
| `tests/fixtures/markdown_to_html/` | 20 markdown files (01-20) for MD→HTML testing |
| `tests/fixtures/html_to_markdown/` | 20 HTML files (01-20) for HTML→MD testing |
| `tests/test_conversions.py` | Main test suite (96 tests) |
| `tests/generate_visual_samples.py` | Visual sample generator |
| `tests/visual_samples/` | Generated visual outputs |

### Test Categories to Run

```bash
# Run specific test classes
pytest tests/test_conversions.py::TestMarkdownToHTML -v
pytest tests/test_conversions.py::TestHTMLToMarkdown -v
pytest tests/test_conversions.py::TestTitleExtraction -v
pytest tests/test_conversions.py::TestRoundTrip -v
pytest tests/test_conversions.py::TestEdgeCases -v
pytest tests/test_conversions.py::TestBidirectionalIntegrity -v
pytest tests/test_conversions.py::TestStressTests -v
```

---

## Part 2: Formatting Elements Checklist

### 2.1 Basic Text Formatting

| Element | MD→HTML | HTML→MD | Round-trip |
|---------|---------|---------|------------|
| **Bold** (`**text**`) | ✓ | ✓ | ✓ |
| *Italic* (`*text*`) | ✓ | ✓ | ✓ |
| `Inline code` (backticks) | ✓ | ✓ | ✓ |
| ***Bold italic*** | ✓ | ✓ | ✓ |
| Underline (`<u>`) | N/A | Converts to plain | Expected |

**Test files:** `01_basic_formatting.md`, `01_basic_formatting.html`

### 2.2 Headers

| Element | MD→HTML | HTML→MD | Round-trip |
|---------|---------|---------|------------|
| H1 (`# Title`) | ✓ | ✓ | ✓ |
| H2 (`## Subtitle`) | ✓ | ✓ | ✓ |
| H3-H6 | ✓ | ✓ | ✓ |
| Headers with formatting | ✓ | ✓ | ✓ |

**Test files:** `02_headers.md`, `02_headers.html`

### 2.3 Lists

| Element | MD→HTML | HTML→MD | Round-trip |
|---------|---------|---------|------------|
| Unordered list (`- item`) | ✓ | ✓ | ✓ |
| Ordered list (`1. item`) | ✓ | ✓ | ✓ |
| Nested lists (2 levels) | ✓ | ✓ | ✓ |
| Nested lists (3+ levels) | ✓ | ✓ | ✓ |
| Mixed ul/ol nesting | ✓ | ✓ | ✓ |
| List items with formatting | ✓ | ✓ | ✓ |

**Test files:** `03_nested_lists.md`, `03_nested_lists.html`, `13_deeply_nested.html`

### 2.4 Links

| Element | MD→HTML | HTML→MD | Round-trip |
|---------|---------|---------|------------|
| Inline links `[text](url)` | ✓ | ✓ | ✓ |
| Bare URLs | ✓ | ✓ | ✓ |
| Links with special chars | ✓ | ✓ | ✓ |
| Links in lists | ✓ | ✓ | ✓ |
| Links in blockquotes | ✓ | ✓ | ✓ |

**Test files:** `04_links.md`, `04_links.html`

### 2.5 Code Blocks

| Element | MD→HTML | HTML→MD | Round-trip |
|---------|---------|---------|------------|
| Fenced code blocks (```) | ✓ | ✓ | ✓ |
| Code with language hint | ✓ | Language lost | Expected |
| Indented code blocks | ✓ | ✓ | ✓ |
| Code with special chars | ✓ | ✓ | ✓ |

**Test files:** `05_code_blocks.md`, `05_code_blocks.html`

### 2.6 Blockquotes

| Element | MD→HTML | HTML→MD | Round-trip |
|---------|---------|---------|------------|
| Single line (`> quote`) | ✓ | ✓ | ✓ |
| Multi-line quotes | ✓ | ✓ | ✓ |
| Nested blockquotes | Partial | Partial | Flattened |
| Quotes with formatting | ✓ | ✓ | ✓ |
| Quotes with links | ✓ | ✓ | ✓ |

**Test files:** `06_blockquotes.md`, `06_blockquotes.html`

### 2.7 Special Characters & Entities

| Element | MD→HTML | HTML→MD | Round-trip |
|---------|---------|---------|------------|
| HTML entities (`&amp;`, `&lt;`) | ✓ | ✓ | ✓ |
| Numeric entities (`&#60;`) | ✓ | ✓ | ✓ |
| Hex entities (`&#x3C;`) | ✓ | ✓ | ✓ |
| Typography (`—`, `'`, `"`) | ✓ | ✓ | ✓ |
| Math symbols (`×`, `÷`, `±`) | ✓ | ✓ | ✓ |
| Emoji (🍎, 📝) | ✓ | ✓ | ✓ |
| Unicode (中文, café) | ✓ | ✓ | ✓ |

**Test files:** `07_special_characters.md`, `07_special_characters.html`, `15_entity_heavy.html`

### 2.8 Whitespace Handling

| Element | MD→HTML | HTML→MD | Round-trip |
|---------|---------|---------|------------|
| Multiple blank lines | Collapsed | Collapsed | Normalized |
| Leading/trailing spaces | Trimmed | Trimmed | Normalized |
| Tabs | Preserved in code | Preserved | ✓ |
| Non-breaking spaces | ✓ | ✓ | ✓ |

**Test files:** `08_whitespace.md`, `08_whitespace.html`

### 2.9 Known Limitations (by design)

| Element | Behavior | Reason |
|---------|----------|--------|
| Tables | Rendered as text | Apple Notes doesn't support MD tables |
| Horizontal rules (`---`) | Rendered as text | Limited HTML support |
| Task lists (`- [ ]`) | Plain list items | Not supported in Apple Notes |
| Footnotes | Inline text | Not supported |
| Definition lists | Plain text | Not supported |

**Test files:** `11_tables.html`, `12_horizontal_rules.html`, `17_task_lists.html`

---

## Part 3: Visual Verification Procedure

### 3.1 Generate Visual Samples

```bash
python tests/generate_visual_samples.py
```

This creates:
- `tests/visual_samples/md_to_html/` - HTML files from markdown
- `tests/visual_samples/html_to_md/` - Markdown files from HTML
- `tests/visual_samples/visual_report.html` - Combined report

### 3.2 Visual Inspection Checklist

Open `tests/visual_samples/visual_report.html` in a browser and verify:

#### Text Formatting
- [ ] Bold text appears bold
- [ ] Italic text appears italicized
- [ ] Code spans have monospace font
- [ ] Combined formatting (bold+italic) renders correctly

#### Structure
- [ ] Headers are properly sized (H1 > H2 > H3...)
- [ ] Lists are indented correctly
- [ ] Nested lists show hierarchy
- [ ] Numbered lists increment correctly

#### Links
- [ ] Links are clickable
- [ ] Link text displays correctly
- [ ] URLs are not broken

#### Code Blocks
- [ ] Code blocks have distinct background
- [ ] Whitespace/indentation preserved
- [ ] Special characters not escaped incorrectly

#### Blockquotes
- [ ] Quotes have visual distinction (indent/border)
- [ ] Quote content is on same line as `>`
- [ ] Formatted text inside quotes renders

#### Special Content
- [ ] Emoji display correctly
- [ ] Unicode characters render
- [ ] HTML entities decoded (& not &amp;)

### 3.3 Real Apple Notes Testing

For comprehensive testing, perform actual sync:

```bash
# Export from Apple Notes
./bin/notes-bridge export-all --html > /tmp/notes_export.json

# Run sync in dry-run mode
unifier sync --generator pdf --dry-run

# Check a specific note conversion
unifier info
```

#### Create Test Notes in Apple Notes

1. Create note with each formatting type:
   - Bold, italic, underline
   - Bulleted and numbered lists
   - Nested lists (3 levels)
   - Links
   - Code (if supported)

2. Export and verify conversion:
   ```bash
   ./bin/notes-bridge export-note <note-id> --html
   ```

3. Compare HTML output to expected patterns in test fixtures

---

## Part 4: Edge Cases to Test

### 4.1 Boundary Conditions

| Test Case | How to Test |
|-----------|-------------|
| Empty note | Create note with only title |
| Very long note | 10,000+ characters |
| Many nested levels | 5+ levels of list nesting |
| Long single line | 1000+ char paragraph |
| Only whitespace content | Spaces/tabs/newlines only |

### 4.2 Character Encoding

| Test Case | How to Test |
|-----------|-------------|
| UTF-8 BOM | File starts with `\ufeff` |
| Mixed encodings | ASCII + Unicode in same note |
| RTL text | Arabic/Hebrew content |
| CJK characters | Chinese/Japanese/Korean |
| Zalgo text | Combining characters |

### 4.3 Malformed Input

| Test Case | Expected Behavior |
|-----------|-------------------|
| Unclosed HTML tags | Graceful handling |
| Invalid nesting | Best-effort conversion |
| Missing attributes | Skip problematic elements |
| Binary content | Skip or escape |

---

## Part 5: Regression Tests

### 5.1 Previously Fixed Bugs

These bugs were fixed and must not regress:

| Bug | Test | File Reference |
|-----|------|----------------|
| Blockquote content on wrong line | `TestHTMLToMarkdown::test_blockquotes` | `markdown.py:handle_endtag` |
| Nested lists not indented | `TestHTMLToMarkdown::test_nested_lists` | `markdown.py:handle_starttag` |
| Link spacing in blockquotes | `TestEdgeCases::test_links_in_blockquotes` | `markdown.py:handle_data` |
| UTF-8 BOM in title extraction | `TestTitleExtraction::test_bom_handling` | `markdown.py:extract_title_from_markdown` |
| Title loss in reverse sync | `TestRoundTrip` | `orchestrator.py` |
| Hash conflicts in edit detection | `TestBidirectionalIntegrity` | `state.py` |

### 5.2 Key Code Paths to Verify

```python
# HTML to Markdown (src/unifier/generators/markdown.py)
- HTMLToMarkdownParser.__init__()
- HTMLToMarkdownParser.handle_starttag()  # List/blockquote start
- HTMLToMarkdownParser.handle_endtag()    # List/blockquote end
- HTMLToMarkdownParser.handle_data()      # Text content
- extract_title_from_markdown()           # BOM handling

# Markdown to HTML (src/unifier/converters/markdown_to_html.py)
- markdown_to_apple_html()
- _process_line()
- _handle_list_item()
- _handle_code_block()
```

---

## Part 6: Update Testing Workflow

### When Apple Notes Updates

1. **Export sample notes** before and after update
   ```bash
   ./bin/notes-bridge export-all --html > before_update.json
   # ... update macOS/Notes ...
   ./bin/notes-bridge export-all --html > after_update.json
   diff before_update.json after_update.json
   ```

2. **Check HTML structure changes**
   - New tags introduced?
   - Attribute changes?
   - Entity encoding changes?

3. **Run full test suite**
   ```bash
   pytest tests/test_conversions.py -v
   ```

4. **Generate and inspect visual samples**
   ```bash
   python tests/generate_visual_samples.py
   open tests/visual_samples/visual_report.html
   ```

5. **Create new test cases** for any new HTML patterns found

### When Supernote Updates

1. **Check .note format compatibility**
   - Can existing .note files still be read?
   - Any new features to support?

2. **Test file sync**
   ```bash
   unifier sync --generator pdf --dry-run
   ```

3. **Verify on device**
   - Transfer test notes to Supernote
   - Open each note type
   - Check rendering fidelity

4. **Update database schema** if needed
   - Check `f_user_file` table structure
   - Verify sync registration works

---

## Part 7: Test File Reference

### Markdown Test Files (01-20)

| File | Tests |
|------|-------|
| `01_basic_formatting.md` | Bold, italic, code, combinations |
| `02_headers.md` | H1-H6, headers with formatting |
| `03_nested_lists.md` | ul/ol, 3-level nesting, mixed |
| `04_links.md` | Inline, bare URLs, special chars |
| `05_code_blocks.md` | Fenced, indented, with language |
| `06_blockquotes.md` | Single, multi-line, with formatting |
| `07_special_characters.md` | Entities, symbols, punctuation |
| `08_whitespace.md` | Blank lines, indentation, tabs |
| `09_complex_mixed.md` | Real-world combination |
| `10_utf8_encoding.md` | Unicode, emoji, international |
| `11_tables.md` | Markdown tables (limitation test) |
| `12_horizontal_rules.md` | `---`, `***`, `___` |
| `13_definition_lists.md` | Term: definition format |
| `14_footnotes.md` | `[^1]` style footnotes |
| `15_escape_sequences.md` | Backslash escapes |
| `16_autolinks.md` | `<url>` style links |
| `17_reference_links.md` | `[text][ref]` style |
| `18_images.md` | `![alt](url)` |
| `19_inline_html.md` | Raw HTML in markdown |
| `20_stress_test.md` | Large, complex document |

### HTML Test Files (01-20)

| File | Tests |
|------|-------|
| `01_basic_formatting.html` | `<b>`, `<i>`, `<code>` |
| `02_headers.html` | `<h1>`-`<h6>` |
| `03_nested_lists.html` | `<ul>`, `<ol>`, nesting |
| `04_links.html` | `<a href="">` |
| `05_code_blocks.html` | `<pre>`, `<code>` |
| `06_blockquotes.html` | `<blockquote>` |
| `07_special_characters.html` | Entity references |
| `08_whitespace.html` | `&nbsp;`, `<br>` |
| `09_complex_mixed.html` | Combined elements |
| `10_utf8_encoding.html` | Unicode content |
| `11_tables.html` | `<table>` (limitation) |
| `12_horizontal_rules.html` | `<hr>` |
| `13_deeply_nested.html` | 5-level nesting |
| `14_empty_elements.html` | Empty tags |
| `15_entity_heavy.html` | All entity types |
| `16_apple_specific.html` | Apple Notes patterns |
| `17_task_lists.html` | Checkbox items |
| `18_inline_styles.html` | `style=""` attributes |
| `19_malformed.html` | Invalid HTML |
| `20_apple_notes_real.html` | Real export sample |

---

## Part 8: Troubleshooting

### Common Issues

| Issue | Likely Cause | Solution |
|-------|--------------|----------|
| Test imports fail | Missing dependencies | `pip install -e ".[dev]"` |
| Swift bridge errors | Not compiled | `./scripts/build_swift.sh` |
| Encoding errors | BOM or invalid UTF-8 | Check file encoding |
| Visual samples empty | Missing fixtures | Run `pytest` first |

### Debug Commands

```bash
# Check Python environment
which python
python --version
pip list | grep -E "(click|rich|pydantic)"

# Test Swift bridge
./bin/notes-bridge list-folders

# Verbose test output
pytest tests/test_conversions.py -v --tb=long

# Run single test
pytest tests/test_conversions.py::TestHTMLToMarkdown::test_blockquotes -v
```

---

## Maintenance Notes

- **Last updated:** 2025-12-29
- **Test count:** 96 tests
- **Coverage:** HTML→MD, MD→HTML, round-trip, edge cases
- **Known limitations:** Tables, HR, task lists render as text

When adding new test cases:
1. Add fixture files to appropriate directory
2. Add test methods to `test_conversions.py`
3. Update this document's file reference tables
4. Run full suite to verify no regressions
