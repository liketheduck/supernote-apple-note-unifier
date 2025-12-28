"""
Option A: Text rendered as strokes

This generator:
1. Renders text using a system font to a bitmap
2. Converts the bitmap to RATTA_RLE encoded stroke layer
3. Creates a .note file with the text appearing as ink strokes

For text-only notes, this is the default generator as it produces
smaller files and the content appears as if written on the device.

Note: This implementation renders text as a bitmap on the MAINLAYER,
which appears as ink/strokes. True vector stroke conversion would
require converting font glyphs to Supernote's path format.

STATUS: Implemented (bitmap-based)
"""

import hashlib
import io
import json
import logging
import random
import re
import string
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from supernotelib import NotebookBuilder
from supernotelib.parser import SupernoteXParser

from ..pdf_utils import PDFAttachment
from .base import BaseGenerator, GeneratorResult, GeneratorType, NoteContent

logger = logging.getLogger(__name__)


class StrokesGenerator(BaseGenerator):
    """Generate .note files with text rendered as strokes."""

    # Manta (A5X2/N5) page dimensions
    SUPERNOTE_WIDTH = 1920
    SUPERNOTE_HEIGHT = 2560

    # Typography settings
    FONT_SIZE = 42
    LINE_HEIGHT = 1.5
    MARGIN_TOP = 100
    MARGIN_LEFT = 80
    MARGIN_RIGHT = 80
    MARGIN_BOTTOM = 100

    # File format constants
    FILE_SIGNATURE = b'SN_FILE_VER_20230015'
    DEVICE_TYPE = 'N5'  # Manta

    # RATTA_RLE encoding constants (X2 series)
    COLORCODE_BLACK = 0x61
    COLORCODE_BACKGROUND = 0x62
    SPECIAL_LENGTH_MARKER = 0xff
    SPECIAL_LENGTH = 0x4000  # 16384 pixels

    def __init__(self, output_base: Path):
        super().__init__(output_base)
        self._font = None

    @property
    def generator_type(self) -> GeneratorType:
        return GeneratorType.STROKES

    def supports_formatting(self) -> bool:
        return False  # Basic text only for now

    def _get_font(self) -> ImageFont.FreeTypeFont:
        """Get a suitable font for text rendering."""
        if self._font is None:
            # Try common system fonts
            font_paths = [
                "/System/Library/Fonts/Helvetica.ttc",
                "/System/Library/Fonts/SFNSText.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/Library/Fonts/Arial.ttf",
            ]
            for path in font_paths:
                if Path(path).exists():
                    try:
                        self._font = ImageFont.truetype(path, self.FONT_SIZE)
                        break
                    except Exception:
                        continue

            if self._font is None:
                # Fall back to default
                self._font = ImageFont.load_default()

        return self._font

    def _get_full_text(self, content: NoteContent) -> str:
        """Get full text content including text extracted from PDF attachments."""
        text_parts = [content.plain_text]

        # Extract text from PDF attachments
        for attachment in content.attachments:
            if attachment.is_pdf and attachment.exported_path:
                pdf = PDFAttachment(attachment.exported_path, attachment.name)
                if pdf.exists and pdf.text:
                    text_parts.append(f"\n\n--- {attachment.name} ---\n\n{pdf.text}")
                    logger.debug(f"Extracted {len(pdf.text)} chars from {attachment.name}")

        return "\n".join(text_parts)

    def generate(self, content: NoteContent, relative_path: str) -> GeneratorResult:
        """Generate .note file with text as strokes."""
        try:
            output_path = self.output_base / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Get combined text
            full_text = self._get_full_text(content)

            # Render text to pages (list of PIL Images)
            pages = self._render_text_pages(content.title, full_text)

            if not pages:
                return GeneratorResult(
                    success=False,
                    output_path=None,
                    error="Failed to render any pages",
                    pages_created=0
                )

            # Create .note file
            note_bytes = self._create_note_file(pages, content)

            # Validate
            self._validate_note_file(note_bytes)

            # Write output
            output_path.write_bytes(note_bytes)

            return GeneratorResult(
                success=True,
                output_path=output_path,
                error=None,
                pages_created=len(pages)
            )
        except Exception as e:
            logger.exception(f"Failed to generate note: {content.title}")
            return GeneratorResult(
                success=False,
                output_path=None,
                error=str(e),
                pages_created=0
            )

    def _render_text_pages(self, title: str, text: str) -> list[Image.Image]:
        """Render text to multiple page images."""
        pages = []
        font = self._get_font()

        # Calculate text area dimensions
        text_width = self.SUPERNOTE_WIDTH - self.MARGIN_LEFT - self.MARGIN_RIGHT
        text_height = self.SUPERNOTE_HEIGHT - self.MARGIN_TOP - self.MARGIN_BOTTOM
        line_height = int(self.FONT_SIZE * self.LINE_HEIGHT)

        # Wrap text into lines
        lines = self._wrap_text(f"{title}\n\n{text}", font, text_width)

        # Split lines into pages
        lines_per_page = text_height // line_height
        page_lines = [lines[i:i + lines_per_page] for i in range(0, len(lines), lines_per_page)]

        for page_line_group in page_lines:
            # Create white background image
            img = Image.new('L', (self.SUPERNOTE_WIDTH, self.SUPERNOTE_HEIGHT), 255)
            draw = ImageDraw.Draw(img)

            # Draw each line
            y = self.MARGIN_TOP
            for line in page_line_group:
                draw.text((self.MARGIN_LEFT, y), line, font=font, fill=0)
                y += line_height

            pages.append(img)

        return pages if pages else [Image.new('L', (self.SUPERNOTE_WIDTH, self.SUPERNOTE_HEIGHT), 255)]

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        """Wrap text to fit within max_width."""
        lines = []

        for paragraph in text.split('\n'):
            if not paragraph.strip():
                lines.append('')
                continue

            words = paragraph.split()
            if not words:
                lines.append('')
                continue

            current_line = words[0]

            for word in words[1:]:
                test_line = f"{current_line} {word}"
                bbox = font.getbbox(test_line)
                width = bbox[2] - bbox[0] if bbox else 0

                if width <= max_width:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word

            lines.append(current_line)

        return lines

    def _image_to_rle(self, img: Image.Image) -> bytes:
        """Convert grayscale image to RATTA_RLE encoded data."""
        # Threshold image to black/white
        # Pixels < 128 become strokes (black), >= 128 become background
        pixels = list(img.getdata())

        rle_data = bytearray()
        current_color = None
        run_length = 0

        for pixel in pixels:
            # Determine color code
            color = self.COLORCODE_BLACK if pixel < 128 else self.COLORCODE_BACKGROUND

            if color == current_color:
                run_length += 1
                # Flush if we hit max run length
                if run_length == self.SPECIAL_LENGTH:
                    rle_data.extend([current_color, self.SPECIAL_LENGTH_MARKER])
                    run_length = 0
                    current_color = None
            else:
                # Flush previous run
                if current_color is not None and run_length > 0:
                    self._encode_run(rle_data, current_color, run_length)

                current_color = color
                run_length = 1

        # Flush final run
        if current_color is not None and run_length > 0:
            self._encode_run(rle_data, current_color, run_length)

        return bytes(rle_data)

    def _encode_run(self, rle_data: bytearray, color: int, length: int):
        """Encode a run of pixels into RATTA_RLE format."""
        while length > 0:
            if length >= self.SPECIAL_LENGTH:
                rle_data.extend([color, self.SPECIAL_LENGTH_MARKER])
                length -= self.SPECIAL_LENGTH
            elif length > 128:
                # Use two-byte length encoding
                # First byte: color, length high bits (with 0x80 flag)
                # Second byte: color (same), length low bits
                high = ((length - 1) >> 7) & 0x7f
                low = (length - 1) & 0x7f
                rle_data.extend([color, high | 0x80, color, low])
                length = 0
            else:
                # Single byte length (0-127 maps to 1-128)
                rle_data.extend([color, length - 1])
                length = 0

    def _create_note_file(self, pages: list[Image.Image], content: NoteContent) -> bytes:
        """Create .note file structure with rendered text pages."""
        builder = NotebookBuilder()

        file_id = self._generate_file_id()

        # 1. Pack type
        builder.append('__type__', b'note', skip_block_size=True)

        # 2. Pack signature
        builder.append('__signature__', self.FILE_SIGNATURE, skip_block_size=True)

        # 3. Pack header
        header = self._create_header(file_id, len(pages))
        header_block = self._construct_metadata_block(header)
        builder.append('__header__', header_block)

        # 4. Pack pages (no background styles needed - text is on MAINLAYER)
        for i, page_img in enumerate(pages):
            page_num = i + 1
            self._pack_page(builder, page_num, page_img)

        # 5. Pack footer
        self._pack_footer(builder)

        # 6. Pack tail
        builder.append('__tail__', b'tail', skip_block_size=True)

        # 7. Pack footer address
        footer_address = builder.get_block_address('__footer__')
        builder.append('__footer_address__', footer_address.to_bytes(4, 'little'), skip_block_size=True)

        return builder.build()

    def _generate_file_id(self) -> str:
        """Generate unique file ID in Supernote format."""
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M%S")
        millis = f"{now.microsecond // 1000:03d}"
        random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        return f"F{timestamp}{millis}{random_str}"

    def _generate_page_id(self) -> str:
        """Generate unique page ID in Supernote format."""
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M%S")
        millis = f"{now.microsecond // 1000:03d}"
        random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        return f"P{timestamp}{millis}{random_str}"

    def _create_header(self, file_id: str, total_pages: int) -> dict:
        """Create header metadata dictionary."""
        return {
            'MODULE_LABEL': 'none',
            'FILE_TYPE': 'NOTE',
            'APPLY_EQUIPMENT': self.DEVICE_TYPE,
            'FINALOPERATION_PAGE': str(total_pages),
            'FINALOPERATION_LAYER': '0',
            'DEVICE_DPI': '0',
            'SOFT_DPI': '0',
            'FILE_PARSE_TYPE': '0',
            'RATTA_ETMD': '0',
            'APP_VERSION': '0',
            'FILE_ID': file_id,
            'FILE_RECOGN_TYPE': '0',
            'FILE_RECOGN_LANGUAGE': 'en_US',
            'PDFSTYLE': 'none',
            'PDFSTYLEMD5': '0',
            'STYLEUSAGETYPE': '0',
            'HIGHLIGHTINFO': '0',
            'HORIZONTAL_CHECK': '0',
            'IS_OLD_APPLY_EQUIPMENT': '1',
            'ANTIALIASING_CONVERT': '2',
        }

    def _pack_page(self, builder: NotebookBuilder, page_num: int, page_img: Image.Image):
        """Pack a single page with rendered text."""
        page_id = self._generate_page_id()

        # Convert image to RLE encoded stroke data
        rle_data = self._image_to_rle(page_img)
        builder.append(f'PAGE{page_num}/MAINLAYER/LAYERBITMAP', rle_data)

        # MAINLAYER metadata
        mainlayer_metadata = {
            'LAYERTYPE': 'NOTE',
            'LAYERPROTOCOL': 'RATTA_RLE',
            'LAYERNAME': 'MAINLAYER',
            'LAYERPATH': '0',
            'LAYERBITMAP': str(builder.get_block_address(f'PAGE{page_num}/MAINLAYER/LAYERBITMAP')),
            'LAYERVECTORGRAPH': '0',
            'LAYERRECOGN': '0',
        }
        mainlayer_block = self._construct_metadata_block(mainlayer_metadata)
        builder.append(f'PAGE{page_num}/MAINLAYER/metadata', mainlayer_block)

        # Empty BGLAYER metadata (no background)
        bglayer_metadata = {
            'LAYERTYPE': 'NOTE',
            'LAYERPROTOCOL': 'BGLAYER',
            'LAYERNAME': 'BGLAYER',
            'LAYERPATH': '0',
            'LAYERBITMAP': '0',
            'LAYERVECTORGRAPH': '0',
            'LAYERRECOGN': '0',
        }
        bglayer_block = self._construct_metadata_block(bglayer_metadata)
        builder.append(f'PAGE{page_num}/BGLAYER/metadata', bglayer_block)

        # Layer info JSON
        layer_info = json.dumps([
            {"layerId": 3, "name": "Layer 3", "isBackgroundLayer": False,
             "isCurrentLayer": False, "isVisible": True, "isDeleted": True},
            {"layerId": 2, "name": "Layer 2", "isBackgroundLayer": False,
             "isCurrentLayer": False, "isVisible": True, "isDeleted": True},
            {"layerId": 1, "name": "Layer 1", "isBackgroundLayer": False,
             "isCurrentLayer": False, "isVisible": True, "isDeleted": True},
            {"layerId": 0, "name": "Main Layer", "isBackgroundLayer": False,
             "isCurrentLayer": True, "isVisible": True, "isDeleted": False},
            {"layerId": -1, "name": "Background Layer", "isBackgroundLayer": True,
             "isCurrentLayer": False, "isVisible": True, "isDeleted": False},
        ])

        # Page metadata (plain style - no background)
        page_metadata = {
            'PAGESTYLE': 'style_white',
            'PAGESTYLEMD5': '0',
            'LAYERINFO': layer_info,
            'LAYERSEQ': 'MAINLAYER,BGLAYER',
            'MAINLAYER': str(builder.get_block_address(f'PAGE{page_num}/MAINLAYER/metadata')),
            'LAYER1': '0',
            'LAYER2': '0',
            'LAYER3': '0',
            'BGLAYER': str(builder.get_block_address(f'PAGE{page_num}/BGLAYER/metadata')),
            'TOTALPATH': '0',
            'THUMBNAILTYPE': '0',
            'RECOGNSTATUS': '0',
            'RECOGNTEXT': '0',
            'RECOGNFILE': '0',
            'PAGEID': page_id,
            'ORIENTATION': '1000',
            'PAGETEXTBOX': '0',
        }
        page_block = self._construct_metadata_block(page_metadata)
        builder.append(f'PAGE{page_num}/metadata', page_block)

    def _pack_footer(self, builder: NotebookBuilder):
        """Pack footer with all block addresses."""
        footer = {}
        footer['FILE_FEATURE'] = builder.get_block_address('__header__')

        # Add page addresses
        for label in builder.get_labels():
            if re.match(r'PAGE\d+/metadata', label):
                address = builder.get_block_address(label)
                page_label = label[:-len('/metadata')]
                footer[page_label] = address

        # No cover
        footer['COVER_0'] = 0

        footer_block = self._construct_metadata_block(footer)
        builder.append('__footer__', footer_block)

    def _construct_metadata_block(self, info: dict) -> bytes:
        """Construct metadata block in Supernote format."""
        block_data = ''
        for k, v in info.items():
            if isinstance(v, list):
                for e in v:
                    block_data += f'<{k}:{e}>'
            else:
                block_data += f'<{k}:{v}>'
        return block_data.encode('utf-8')

    def _validate_note_file(self, note_bytes: bytes):
        """Validate the generated .note file."""
        try:
            stream = io.BytesIO(note_bytes)
            parser = SupernoteXParser()
            parser.parse_stream(stream)
        except Exception as e:
            raise ValueError(f"Generated .note file failed validation: {e}")
