"""
Supernote .note file format handling.

This module provides utilities for creating and manipulating .note files.
Based on research from supernote-tool and supernote-ocr-enhancer.
"""

import io
import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import supernotelib as sn
    import supernotelib.manipulator as manip
    import supernotelib.parser as parser
    SUPERNOTELIB_AVAILABLE = True
except ImportError:
    SUPERNOTELIB_AVAILABLE = False

from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class PageInfo:
    """Information about a single page in a .note file."""
    page_number: int
    width: int
    height: int
    has_content: bool


@dataclass
class NoteFileInfo:
    """Information about a .note file."""
    path: Path
    total_pages: int
    is_realtime_recognition: bool
    file_type: str


def check_supernotelib():
    """Check if supernotelib is available."""
    if not SUPERNOTELIB_AVAILABLE:
        raise ImportError(
            "supernotelib is required for .note file operations. "
            "Install it with: pip install supernotelib"
        )


def load_notebook(note_path: Path):
    """Load a .note file."""
    check_supernotelib()
    return sn.load_notebook(str(note_path))


def get_notebook_info(note_path: Path) -> NoteFileInfo:
    """Get metadata about a .note file."""
    notebook = load_notebook(note_path)
    return NoteFileInfo(
        path=note_path,
        total_pages=len(notebook.pages),
        is_realtime_recognition=notebook.is_realtime_recognition(),
        file_type=notebook.type if hasattr(notebook, 'type') else 'unknown'
    )


def extract_page_as_image(notebook, page_number: int) -> Image.Image:
    """Extract a single page as a PIL Image."""
    check_supernotelib()
    converter = sn.converter.ImageConverter(notebook)
    return converter.convert(page_number)


def extract_page_as_png(notebook, page_number: int) -> bytes:
    """Extract a single page as PNG bytes."""
    img = extract_page_as_image(notebook, page_number)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def create_recognition_data(lines: list[list[dict]]) -> bytes:
    """
    Create Supernote recognition data format.

    The format is base64-encoded JSON:
    {
        "elements": [
            {"type": "Raw Content"},
            {"type": "Text", "label": "line text", "words": [...]},
            ...
        ],
        "type": "Text"
    }

    Args:
        lines: List of lines, where each line is a list of word dicts:
               [{"text": "word", "bbox": [left, top, right, bottom]}, ...]

    Returns:
        Base64-encoded recognition data bytes
    """
    # Supernote coordinate scaling factor
    SUPERNOTE_SCALE_FACTOR = 11.9

    elements = [{"type": "Raw Content"}]

    for line in lines:
        words = []
        line_text_parts = []

        for i, word_info in enumerate(line):
            text = word_info["text"].strip()
            if not text:
                continue

            line_text_parts.append(text)

            left, top, right, bottom = word_info["bbox"]

            # Convert to Supernote's scaled coordinate system
            x = float(left) / SUPERNOTE_SCALE_FACTOR
            y = float(top) / SUPERNOTE_SCALE_FACTOR
            width = float(right - left) / SUPERNOTE_SCALE_FACTOR
            height = float(bottom - top) / SUPERNOTE_SCALE_FACTOR

            words.append({
                "bounding-box": {
                    "x": round(x, 2),
                    "y": round(y, 2),
                    "width": round(width, 2),
                    "height": round(height, 2)
                },
                "label": text
            })

            # Add space after each word (except last in line)
            if i < len(line) - 1:
                words.append({"label": " "})

        if words:
            line_text = " ".join(line_text_parts)
            elements.append({
                "type": "Text",
                "label": line_text,
                "words": words
            })

    recogn_data = {
        "elements": elements,
        "type": "Text"
    }

    json_str = json.dumps(recogn_data, ensure_ascii=False)
    return base64.b64encode(json_str.encode('utf-8'))


def get_existing_ocr_text(notebook, page_number: int) -> Optional[str]:
    """Get existing OCR text from a page, if any."""
    if page_number >= len(notebook.pages):
        return None

    page = notebook.pages[page_number]
    recogn_text = page.get_recogn_text()

    if not recogn_text or recogn_text == 'None':
        return None

    try:
        decoded = base64.b64decode(recogn_text).decode('utf-8')
        data = json.loads(decoded)
        # Extract all text labels
        texts = []
        for elem in data.get('elements', []):
            if elem.get('type') == 'Text' and 'label' in elem:
                texts.append(elem['label'])
        return "\n".join(texts)
    except Exception:
        return None
