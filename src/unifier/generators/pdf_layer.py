"""
Option C: PDF as background layer

This generator:
1. Renders Apple Note content to PDF
2. Appends any PDF attachments as additional pages
3. Converts PDF pages to PNG images
4. Creates a .note file with PNGs as background layers
5. Content is visible but not editable as text

Pros:
- Preserves all formatting, images, etc.
- Most visually accurate
- PDF attachments become additional pages

Cons:
- Not searchable on device
- Cannot edit text
- Larger file size

STATUS: Implemented
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

from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from supernotelib import NotebookBuilder
from supernotelib.parser import SupernoteXParser

from .base import BaseGenerator, GeneratorResult, GeneratorType, NoteContent

logger = logging.getLogger(__name__)


class PDFLayerGenerator(BaseGenerator):
    """Generate .note files with PDF background layer."""

    # Manta (A5X2/N5) page dimensions
    SUPERNOTE_WIDTH = 1920
    SUPERNOTE_HEIGHT = 2560

    # PDF rendering size (aspect ratio for A4-like documents)
    PAGE_WIDTH_MM = 157
    PAGE_HEIGHT_MM = 210

    # File format constants
    FILE_SIGNATURE = b'SN_FILE_VER_20230015'
    DEVICE_TYPE = 'N5'  # Manta

    # RATTA_RLE encoding constants
    COLORCODE_BACKGROUND = 0x62
    SPECIAL_LENGTH_MARKER = 0xff
    SPECIAL_LENGTH = 0x4000  # 16384 pixels per marker

    def __init__(self, output_base: Path):
        super().__init__(output_base)
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    def _setup_styles(self):
        """Configure PDF styles to match Apple Notes appearance."""
        self.styles.add(ParagraphStyle(
            name='NoteBody',
            parent=self.styles['Normal'],
            fontSize=11,
            leading=14,
            spaceAfter=6,
        ))
        self.styles.add(ParagraphStyle(
            name='NoteTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            leading=22,
            spaceAfter=12,
        ))

    @property
    def generator_type(self) -> GeneratorType:
        return GeneratorType.PDF_LAYER

    def supports_formatting(self) -> bool:
        return True

    def generate(self, content: NoteContent, relative_path: str) -> GeneratorResult:
        """Generate .note file with PDF background."""
        try:
            output_path = self.output_base / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Generate PDF from note content
            content_pdf_bytes = self._render_pdf(content)

            # Merge with PDF attachments if any
            pdf_bytes = self._merge_with_attachments(content_pdf_bytes, content.attachments)

            # Convert PDF to PNG images
            png_pages = self._pdf_to_pngs(pdf_bytes)

            if not png_pages:
                return GeneratorResult(
                    success=False,
                    output_path=None,
                    error="Failed to render any PDF pages",
                    pages_created=0
                )

            # Create .note file with PNG backgrounds
            note_bytes = self._create_note_file(png_pages, content)

            # Validate the generated file
            self._validate_note_file(note_bytes)

            # Write output
            output_path.write_bytes(note_bytes)

            # Preserve Apple Notes modification timestamp
            self._set_file_timestamp(output_path, content.modified_at)

            return GeneratorResult(
                success=True,
                output_path=output_path,
                error=None,
                pages_created=len(png_pages)
            )
        except Exception as e:
            logger.exception(f"Failed to generate note: {content.title}")
            return GeneratorResult(
                success=False,
                output_path=None,
                error=str(e),
                pages_created=0
            )

    def _merge_with_attachments(self, content_pdf: bytes, attachments: list) -> bytes:
        """Merge note content PDF with any PDF attachments."""
        pdf_attachments = [
            a for a in attachments
            if a.is_pdf and a.exported_path and Path(a.exported_path).exists()
        ]

        if not pdf_attachments:
            return content_pdf

        writer = PdfWriter()

        content_reader = PdfReader(io.BytesIO(content_pdf))
        for page in content_reader.pages:
            writer.add_page(page)

        for attachment in pdf_attachments:
            try:
                attachment_reader = PdfReader(attachment.exported_path)
                for page in attachment_reader.pages:
                    writer.add_page(page)
                logger.debug(f"Merged {len(attachment_reader.pages)} pages from {attachment.name}")
            except Exception as e:
                logger.warning(f"Failed to merge attachment {attachment.name}: {e}")

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()

    def _render_pdf(self, content: NoteContent) -> bytes:
        """Render note content to PDF bytes."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=(self.PAGE_WIDTH_MM * mm, self.PAGE_HEIGHT_MM * mm),
            topMargin=15 * mm,
            bottomMargin=15 * mm,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
        )

        story = []

        # Title
        story.append(Paragraph(self._escape_html(content.title), self.styles['NoteTitle']))
        story.append(Spacer(1, 6 * mm))

        # Body
        if content.html:
            paragraphs = self._html_to_paragraphs(content.html)
            story.extend(paragraphs)
        else:
            for para in content.plain_text.split('\n\n'):
                if para.strip():
                    story.append(Paragraph(
                        self._escape_html(para),
                        self.styles['NoteBody']
                    ))

        doc.build(story)
        return buffer.getvalue()

    def _escape_html(self, text: str) -> str:
        """Escape text for safe HTML rendering."""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;'))

    def _html_to_paragraphs(self, html: str) -> list:
        """Convert HTML to ReportLab paragraphs."""
        import html as html_module

        # Remove script and style elements
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)

        # Convert br and p tags to newlines
        html = re.sub(r'<br\s*/?>', '\n', html)
        html = re.sub(r'</p>', '\n\n', html)
        html = re.sub(r'<p[^>]*>', '', html)

        # Remove remaining HTML tags
        text = re.sub(r'<[^>]+>', '', html)
        text = html_module.unescape(text)

        paragraphs = []
        for para in text.split('\n\n'):
            para = para.strip()
            if para:
                paragraphs.append(Paragraph(
                    self._escape_html(para),
                    self.styles['NoteBody']
                ))

        return paragraphs

    def _pdf_to_pngs(self, pdf_bytes: bytes) -> list[bytes]:
        """Convert PDF pages to PNG images sized for Supernote."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            # Fall back to pdf2image if PyMuPDF not available
            return self._pdf_to_pngs_fallback(pdf_bytes)

        png_pages = []
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)

            # Calculate zoom to fit Supernote dimensions
            zoom_x = self.SUPERNOTE_WIDTH / page.rect.width
            zoom_y = self.SUPERNOTE_HEIGHT / page.rect.height
            zoom = min(zoom_x, zoom_y)

            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            # Create PIL Image and resize to exact dimensions
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img = self._fit_to_supernote_size(img)

            # Convert to PNG bytes
            png_buffer = io.BytesIO()
            img.save(png_buffer, format='PNG')
            png_pages.append(png_buffer.getvalue())

        doc.close()
        return png_pages

    def _pdf_to_pngs_fallback(self, pdf_bytes: bytes) -> list[bytes]:
        """Fallback PDF to PNG conversion using pypdf and reportlab."""
        # Use pypdf to count pages, then render each page
        reader = PdfReader(io.BytesIO(pdf_bytes))
        num_pages = len(reader.pages)

        png_pages = []
        for i in range(num_pages):
            # Create a white background image
            img = Image.new('RGB', (self.SUPERNOTE_WIDTH, self.SUPERNOTE_HEIGHT), 'white')

            # Note: This fallback doesn't render PDF content - just creates blank pages
            # For full PDF rendering, PyMuPDF (fitz) is required
            logger.warning(f"Using fallback renderer - page {i+1} will be blank. Install pymupdf for full PDF rendering.")

            png_buffer = io.BytesIO()
            img.save(png_buffer, format='PNG')
            png_pages.append(png_buffer.getvalue())

        return png_pages

    def _fit_to_supernote_size(self, img: Image.Image) -> Image.Image:
        """Resize and pad image to exact Supernote dimensions."""
        target_w, target_h = self.SUPERNOTE_WIDTH, self.SUPERNOTE_HEIGHT

        # Calculate scaling to fit within target while maintaining aspect ratio
        scale = min(target_w / img.width, target_h / img.height)
        new_w = int(img.width * scale)
        new_h = int(img.height * scale)

        # Resize
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Create white background and paste centered
        result = Image.new('RGB', (target_w, target_h), 'white')
        paste_x = (target_w - new_w) // 2
        paste_y = (target_h - new_h) // 2
        result.paste(img, (paste_x, paste_y))

        return result

    def _create_note_file(self, png_pages: list[bytes], content: NoteContent) -> bytes:
        """Create .note file structure with PNG backgrounds."""
        builder = NotebookBuilder()

        # Generate unique file ID
        file_id = self._generate_file_id()

        # 1. Pack type
        builder.append('__type__', b'note', skip_block_size=True)

        # 2. Pack signature
        builder.append('__signature__', self.FILE_SIGNATURE, skip_block_size=True)

        # 3. Pack header
        header = self._create_header(file_id, len(png_pages))
        header_block = self._construct_metadata_block(header)
        builder.append('__header__', header_block)

        # 4. Pack backgrounds (one per page, but shared if identical)
        style_hashes = {}
        for i, png_data in enumerate(png_pages):
            style_name = f"user_applenote_page{i+1}"
            style_hash = hashlib.md5(style_name.encode()).hexdigest()
            style_hashes[i] = (style_name, style_hash)
            builder.append(f'STYLE_{style_name}{style_hash}', png_data)

        # 5. Pack pages
        for i, png_data in enumerate(png_pages):
            page_num = i + 1
            style_name, style_hash = style_hashes[i]
            self._pack_page(builder, page_num, style_name, style_hash)

        # 6. Pack footer
        self._pack_footer(builder)

        # 7. Pack tail
        builder.append('__tail__', b'tail', skip_block_size=True)

        # 8. Pack footer address
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

    def _pack_page(self, builder: NotebookBuilder, page_num: int, style_name: str, style_hash: str):
        """Pack a single page with its layers."""
        page_id = self._generate_page_id()

        # Create empty MAINLAYER (all transparent - no strokes)
        empty_layer = self._create_empty_layer()
        builder.append(f'PAGE{page_num}/MAINLAYER/LAYERBITMAP', empty_layer)

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

        # BGLAYER metadata (points to the style/background PNG)
        bglayer_metadata = {
            'LAYERTYPE': 'NOTE',
            'LAYERPROTOCOL': 'BGLAYER',
            'LAYERNAME': 'BGLAYER',
            'LAYERPATH': '0',
            'LAYERBITMAP': str(builder.get_block_address(f'STYLE_{style_name}{style_hash}')),
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

        # Page metadata
        page_metadata = {
            'PAGESTYLE': f'user_{style_name.replace("user_", "")}',
            'PAGESTYLEMD5': style_hash,
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

    def _create_empty_layer(self) -> bytes:
        """Create empty RATTA_RLE encoded layer (all transparent)."""
        total_pixels = self.SUPERNOTE_WIDTH * self.SUPERNOTE_HEIGHT
        num_markers = total_pixels // self.SPECIAL_LENGTH

        # Each pair is (color=0x62/background, length=0xff/16384)
        return bytes([self.COLORCODE_BACKGROUND, self.SPECIAL_LENGTH_MARKER] * num_markers)

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

        # Add style addresses
        for label in builder.get_labels():
            if label.startswith('STYLE_'):
                footer[label] = builder.get_block_address(label)

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
