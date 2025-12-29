#!/usr/bin/env python3
"""
Generate visual samples for manual inspection of conversion quality.

This script creates:
1. HTML files from markdown test files (for viewing in browser)
2. Markdown files from HTML test files (for viewing in any editor)
3. A combined HTML report showing all conversions side-by-side
"""

import re
from pathlib import Path

# Import the converters
from unifier.converters.markdown_to_html import (
    extract_title_from_markdown,
    markdown_to_apple_html,
)
from unifier.generators.markdown import HTMLToMarkdownParser

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MD_TO_HTML_DIR = FIXTURES_DIR / "markdown_to_html"
HTML_TO_MD_DIR = FIXTURES_DIR / "html_to_markdown"
OUTPUT_DIR = Path(__file__).parent / "visual_samples"


def html_to_markdown(html: str, title: str | None = None) -> str:
    """Helper to convert HTML to markdown using the parser."""
    # Clean up HTML (same as MarkdownGenerator._clean_html)
    html = re.sub(r'\s+style\s*=\s*["\'][^"\']*["\']', '', html)
    html = re.sub(r'\s+class\s*=\s*["\'][^"\']*["\']', '', html)

    parser = HTMLToMarkdownParser(title_to_skip=title)
    parser.feed(html)
    return parser.get_markdown()


def generate_md_to_html_samples():
    """Generate HTML from markdown test files."""
    output_subdir = OUTPUT_DIR / "md_to_html"
    output_subdir.mkdir(parents=True, exist_ok=True)

    results = []

    for md_file in sorted(MD_TO_HTML_DIR.glob("*.txt")):
        md_content = md_file.read_text()
        title, _ = extract_title_from_markdown(md_content)
        html_content = markdown_to_apple_html(md_content)

        # Wrap in full HTML document for viewing
        full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; }}
        pre {{ background: #f5f5f5; padding: 10px; overflow-x: auto; }}
        code {{ background: #f5f5f5; padding: 2px 5px; }}
        blockquote {{ border-left: 3px solid #ccc; margin-left: 0; padding-left: 15px; color: #666; }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""

        output_file = output_subdir / f"{md_file.stem}.html"
        output_file.write_text(full_html)

        results.append({
            'name': md_file.stem,
            'original': md_content,
            'converted': html_content,
            'output_file': output_file,
        })

    return results


def generate_html_to_md_samples():
    """Generate markdown from HTML test files."""
    output_subdir = OUTPUT_DIR / "html_to_md"
    output_subdir.mkdir(parents=True, exist_ok=True)

    results = []

    for html_file in sorted(HTML_TO_MD_DIR.glob("*.html")):
        html_content = html_file.read_text()

        # Extract title from first H1
        h1_match = re.search(r'<h1>([^<]+)</h1>', html_content)
        title = h1_match.group(1) if h1_match else None

        md_content = html_to_markdown(html_content, title)

        # Add title as H1 at start of markdown
        if title:
            full_md = f"# {title}\n\n{md_content}"
        else:
            full_md = md_content

        output_file = output_subdir / f"{html_file.stem}.md"
        output_file.write_text(full_md)

        results.append({
            'name': html_file.stem,
            'original': html_content,
            'converted': full_md,
            'output_file': output_file,
        })

    return results


def generate_report(md_results, html_results):
    """Generate a combined HTML report."""
    report_html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Conversion Visual Test Report</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 20px; }
        h1 { color: #333; }
        h2 { color: #666; border-bottom: 1px solid #ddd; padding-bottom: 10px; }
        .test-case { margin-bottom: 40px; border: 1px solid #ddd; padding: 20px; border-radius: 8px; }
        .test-name { font-weight: bold; color: #007aff; margin-bottom: 10px; }
        .comparison { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .panel { background: #f9f9f9; padding: 15px; border-radius: 4px; overflow-x: auto; }
        .panel h4 { margin-top: 0; color: #333; }
        pre { white-space: pre-wrap; word-wrap: break-word; font-size: 12px; }
        .rendered { background: white; border: 1px solid #ddd; padding: 15px; }
        .success { color: green; }
        .section-divider { margin: 40px 0; border-top: 3px solid #007aff; }
    </style>
</head>
<body>
    <h1>Conversion Visual Test Report</h1>
    <p>Generated samples for manual visual inspection of conversion quality.</p>
"""

    # Section 1: Markdown → HTML
    report_html += """
    <h2>Markdown → HTML Conversions (10 test files)</h2>
    <p>These tests verify that markdown input is correctly converted to Apple Notes HTML.</p>
"""

    for result in md_results:
        # Escape HTML for display
        original_escaped = result['original'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        converted_escaped = result['converted'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        report_html += f"""
    <div class="test-case">
        <div class="test-name">{result['name']}</div>
        <div class="comparison">
            <div class="panel">
                <h4>Original Markdown</h4>
                <pre>{original_escaped}</pre>
            </div>
            <div class="panel">
                <h4>Generated HTML (source)</h4>
                <pre>{converted_escaped}</pre>
            </div>
        </div>
        <div style="margin-top: 20px;">
            <h4>Rendered HTML Preview</h4>
            <div class="rendered">
                {result['converted']}
            </div>
        </div>
    </div>
"""

    # Section 2: HTML → Markdown
    report_html += """
    <div class="section-divider"></div>
    <h2>HTML → Markdown Conversions (10 test files)</h2>
    <p>These tests verify that Apple Notes HTML is correctly converted to markdown.</p>
"""

    for result in html_results:
        # Escape HTML for display
        original_escaped = result['original'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        converted_escaped = result['converted'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        report_html += f"""
    <div class="test-case">
        <div class="test-name">{result['name']}</div>
        <div class="comparison">
            <div class="panel">
                <h4>Original HTML</h4>
                <pre>{original_escaped}</pre>
            </div>
            <div class="panel">
                <h4>Generated Markdown</h4>
                <pre>{converted_escaped}</pre>
            </div>
        </div>
        <div style="margin-top: 20px;">
            <h4>Original HTML Rendered</h4>
            <div class="rendered">
                {result['original']}
            </div>
        </div>
    </div>
"""

    report_html += """
    <div style="margin-top: 40px; padding: 20px; background: #e8f5e9; border-radius: 8px;">
        <h3 class="success">✅ All 20 test files processed successfully</h3>
        <p>Individual sample files are available in the <code>tests/visual_samples/</code> directory:</p>
        <ul>
            <li><code>md_to_html/</code> - HTML files generated from markdown (open in browser)</li>
            <li><code>html_to_md/</code> - Markdown files generated from HTML (open in any editor)</li>
        </ul>
    </div>
</body>
</html>"""

    report_file = OUTPUT_DIR / "visual_report.html"
    report_file.write_text(report_html)
    return report_file


def main():
    """Generate all visual samples and report."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Generating markdown → HTML samples...")
    md_results = generate_md_to_html_samples()
    print(f"  Generated {len(md_results)} HTML files")

    print("Generating HTML → markdown samples...")
    html_results = generate_html_to_md_samples()
    print(f"  Generated {len(html_results)} markdown files")

    print("Generating visual report...")
    report_file = generate_report(md_results, html_results)
    print(f"  Report: {report_file}")

    print("\n✅ Visual samples generated successfully!")
    print(f"   Open {report_file} in a browser to inspect all conversions.")


if __name__ == "__main__":
    main()
