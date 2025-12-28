"""Base generator interface for .note file creation."""

import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class GeneratorType(Enum):
    """Available generator types."""
    STROKES = "strokes"       # Option A: text as vector strokes (.note format)
    TEXT = "text"             # Option B: Markdown .txt file (for text-only notes)
    PDF_LAYER = "pdf"         # Option C: PDF as background layer (for rich content)
    AUTO = "auto"             # Automatically select based on content


class ContentType(Enum):
    """Type of note content."""
    TEXT_ONLY = "text_only"   # Plain text, URLs (no images/attachments)
    RICH = "rich"             # Images, attachments, drawings, etc.


@dataclass
class AttachmentInfo:
    """Information about an attachment."""
    id: str
    name: str
    is_pdf: bool
    exported_path: str | None = None
    content_identifier: str | None = None


@dataclass
class NoteContent:
    """Represents content to be converted to .note format."""
    title: str
    plain_text: str
    html: str | None
    created_at: str
    modified_at: str
    source_id: str  # Apple Notes ID for tracking
    attachments: list[AttachmentInfo] = field(default_factory=list)

    def get_content_type(self) -> ContentType:
        """Detect if note is text-only or has rich content."""
        # Check for real file attachments (PDFs, images, etc.)
        # Exclude URL previews which show up as attachments but aren't real files
        real_attachments = [
            a for a in self.attachments
            if a.is_pdf or a.exported_path  # Has an actual file path
        ]
        if real_attachments:
            return ContentType.RICH

        # Check HTML for rich content indicators
        if self.html:
            # Check for embedded images (not URL previews)
            # Apple Notes uses <img> for actual images
            if re.search(r'<img\s+[^>]*src\s*=\s*["\'](?!https?://)[^"\']+["\']', self.html):
                return ContentType.RICH

            # Check for drawings/handwriting (Apple Notes stores these specially)
            if re.search(r'<object\s+[^>]*type\s*=\s*["\'].*drawing', self.html, re.IGNORECASE):
                return ContentType.RICH

            # Check for embedded objects/attachments
            if re.search(r'<object\s+[^>]*type\s*=\s*["\']application/', self.html):
                return ContentType.RICH

            # Check for Apple's attachment markers
            if 'data-apple-inline-attachment' in self.html:
                return ContentType.RICH

        return ContentType.TEXT_ONLY


@dataclass
class GeneratorResult:
    """Result of note generation."""
    success: bool
    output_path: Path | None
    error: str | None
    pages_created: int


class BaseGenerator(ABC):
    """Abstract base class for .note file generators."""

    # Manta page dimensions (pixels)
    PAGE_WIDTH = 1920
    PAGE_HEIGHT = 2560

    # Margins
    MARGIN_TOP = 100
    MARGIN_LEFT = 80
    MARGIN_RIGHT = 80
    MARGIN_BOTTOM = 100

    def __init__(self, output_base: Path):
        self.output_base = output_base

    @abstractmethod
    def generate(self, content: NoteContent, relative_path: str) -> GeneratorResult:
        """
        Generate a .note file from the given content.

        Args:
            content: The note content to convert
            relative_path: Path relative to output_base (e.g., "Work/Projects/note.note")

        Returns:
            GeneratorResult with success status and output path
        """
        pass

    @abstractmethod
    def supports_formatting(self) -> bool:
        """Whether this generator preserves HTML formatting."""
        pass

    @property
    @abstractmethod
    def generator_type(self) -> GeneratorType:
        """The type of this generator."""
        pass

    def _set_file_timestamp(self, file_path: Path, modified_at: str) -> None:
        """
        Set file modification timestamp to match Apple Notes date.

        Args:
            file_path: Path to the file to update
            modified_at: Apple Notes date string like "Thursday, October 4, 2018 at 11:45:18 AM"
        """
        if not modified_at or not file_path.exists():
            return

        try:
            # Try various Apple Notes date formats
            # Format: "Thursday, October 4, 2018 at 11:45:18 AM"
            # Also handles narrow non-breaking space (U+202F) before AM/PM
            date_str = modified_at.replace('\u202f', ' ')

            # Try formats with and without weekday
            formats = [
                "%A, %B %d, %Y at %I:%M:%S %p",  # Thursday, October 4, 2018 at 11:45:18 AM
                "%B %d, %Y at %I:%M:%S %p",      # October 4, 2018 at 11:45:18 AM
                "%A, %B %d, %Y at %H:%M:%S",     # 24-hour variant
                "%B %d, %Y at %H:%M:%S",         # 24-hour variant
            ]

            parsed_date = None
            for fmt in formats:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue

            if parsed_date:
                timestamp = parsed_date.timestamp()
                os.utime(file_path, (timestamp, timestamp))
                logger.debug(f"Set timestamp on {file_path.name} to {parsed_date}")
            else:
                logger.warning(f"Could not parse date: {modified_at}")

        except Exception as e:
            logger.warning(f"Failed to set timestamp on {file_path}: {e}")
