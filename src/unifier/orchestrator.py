"""
Main orchestrator that coordinates all components.
"""

import hashlib
import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path

from .generators.base import (
    AttachmentInfo,
    BaseGenerator,
    ContentType,
    GeneratorType,
    NoteContent,
)
from .state import StateDatabase
from .supernote.paths import ensure_apple_notes_directory, sanitize_filename
from .supernote.sync import PersonalCloudSync

logger = logging.getLogger(__name__)


class Orchestrator:
    """Coordinates Apple Notes export and Supernote note generation."""

    def __init__(
        self,
        supernote_base: Path,
        state_db_path: Path,
        swift_bridge_path: Path,
        generator_type: GeneratorType = GeneratorType.AUTO
    ):
        self.supernote_base = supernote_base
        self.output_base = ensure_apple_notes_directory(supernote_base)
        self.state_db = StateDatabase(state_db_path)
        self.swift_bridge = swift_bridge_path
        self.generator_type = generator_type

        # Cache generators (lazy init)
        self._generators: dict[GeneratorType, BaseGenerator] = {}

        # Personal Cloud sync handler
        self.cloud_sync = PersonalCloudSync()

    def _get_generator(self, gen_type: GeneratorType) -> BaseGenerator:
        """Get or create a generator of the specified type."""
        if gen_type not in self._generators:
            from .generators.markdown import MarkdownGenerator
            from .generators.pdf_layer import PDFLayerGenerator
            from .generators.strokes import StrokesGenerator

            generator_classes = {
                GeneratorType.STROKES: StrokesGenerator,
                GeneratorType.TEXT: MarkdownGenerator,  # .txt with Markdown
                GeneratorType.PDF_LAYER: PDFLayerGenerator,
            }
            self._generators[gen_type] = generator_classes[gen_type](self.output_base)

        return self._generators[gen_type]

    def _select_generator_for_content(self, content: NoteContent) -> BaseGenerator:
        """Select appropriate generator based on content type and user preference."""
        if self.generator_type == GeneratorType.AUTO:
            # Auto-select based on content
            content_type = content.get_content_type()
            if content_type == ContentType.TEXT_ONLY:
                # Text-only notes use Markdown .txt files
                return self._get_generator(GeneratorType.TEXT)
            else:
                # Rich content (images, attachments, etc.) use PDF layer
                return self._get_generator(GeneratorType.PDF_LAYER)
        else:
            # User specified a generator type
            return self._get_generator(self.generator_type)

    def run(self, dry_run: bool = False, verbose: bool = False) -> dict:
        """
        Execute the reflection process.

        Returns:
            Summary dict with counts and any errors
        """
        # Verify Supernote volume is mounted
        if not self.supernote_base.exists():
            raise RuntimeError(
                f"Supernote volume not mounted: {self.supernote_base}"
            )

        # Export all notes from Apple Notes
        notes_data = self._export_apple_notes()

        # Process each note
        stats = {
            "total": len(notes_data.get("notes", [])),
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 0,
            "text_only": 0,
            "rich_content": 0,
            "errors": []
        }

        current_note_ids = set()

        for note in notes_data.get("notes", []):
            current_note_ids.add(note["id"])

            # Compute content hash
            content_hash = self._compute_hash(note)

            # Check if update needed
            existing_state = self.state_db.get_note_state(note["id"])
            if not self.state_db.needs_update(note["id"], content_hash):
                stats["skipped"] += 1
                continue

            # Parse attachments
            attachments = []
            for att in note.get("attachments", []):
                attachments.append(AttachmentInfo(
                    id=att.get("id", ""),
                    name=att.get("name", ""),
                    is_pdf=att.get("isPDF", False),
                    exported_path=att.get("exportedPath"),
                    content_identifier=att.get("contentIdentifier")
                ))

            # Prepare content
            content = NoteContent(
                title=note["name"],
                plain_text=note.get("bodyPlainText", ""),
                html=note.get("bodyHTML"),
                created_at=note.get("creationDate", ""),
                modified_at=note.get("modificationDate", ""),
                source_id=note["id"],
                attachments=attachments
            )

            # Track content type stats
            content_type = content.get_content_type()
            if content_type == ContentType.TEXT_ONLY:
                stats["text_only"] += 1
            else:
                stats["rich_content"] += 1

            # Select generator based on content and user preference
            generator = self._select_generator_for_content(content)

            # Determine output path
            relative_path = self._make_relative_path(note)

            if dry_run:
                gen_name = generator.generator_type.value
                content_desc = "text-only" if content_type == ContentType.TEXT_ONLY else "rich"
                print(f"Would generate ({gen_name}, {content_desc}): {relative_path}")
                if existing_state:
                    stats["updated"] += 1
                else:
                    stats["created"] += 1
                continue

            if verbose:
                gen_name = generator.generator_type.value
                logger.info(f"Generating {relative_path} with {gen_name} generator")

            # Generate .note file
            result = generator.generate(content, relative_path)

            if result.success:
                self.state_db.record_success(
                    note["id"],
                    note.get("folderPath", ""),
                    content_hash,
                    result.output_path,
                    generator.generator_type.value
                )

                # Register in Personal Cloud sync database
                if result.output_path:
                    sync_path = result.output_path.relative_to(self.output_base.parent)
                    # Parse Apple Notes modification date for database timestamp
                    modified_at_ms = self._parse_apple_date_to_ms(
                        note.get("modificationDate", "")
                    )
                    self.cloud_sync.register_file(
                        result.output_path, str(sync_path), modified_at_ms
                    )

                if existing_state:
                    stats["updated"] += 1
                else:
                    stats["created"] += 1
            else:
                self.state_db.record_failure(
                    note["id"],
                    note.get("folderPath", ""),
                    content_hash,
                    generator.generator_type.value,
                    result.error
                )
                stats["failed"] += 1
                stats["errors"].append({
                    "note": note["name"],
                    "error": result.error
                })

        # Handle orphaned notes (deleted from Apple Notes)
        if not dry_run:
            orphaned = self.state_db.get_orphaned_outputs(current_note_ids)
            for output_path in orphaned:
                # For safety, just log for now
                logger.info(f"Orphaned output (source deleted): {output_path}")

        return stats

    def _export_apple_notes(self) -> dict:
        """Call Swift bridge to export Apple Notes."""
        if not self.swift_bridge.exists():
            raise RuntimeError(
                f"Swift bridge not found at {self.swift_bridge}. "
                f"Build it first with: scripts/build_swift.sh"
            )

        result = subprocess.run(
            [str(self.swift_bridge), "export-all", "--html", "--attachments"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            try:
                error_data = json.loads(result.stderr)
                error_msg = error_data.get('error', error_msg)
            except (json.JSONDecodeError, TypeError):
                pass
            raise RuntimeError(f"Swift bridge failed: {error_msg}")

        return json.loads(result.stdout)

    def _compute_hash(self, note: dict) -> str:
        """Compute content hash for change detection."""
        content = f"{note.get('name', '')}|{note.get('bodyPlainText', '')}|{note.get('modificationDate', '')}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _make_relative_path(self, note: dict) -> str:
        """Convert Apple Notes folder path to output file path."""
        folder_path = note.get("folderPath", "").strip("/")
        safe_name = sanitize_filename(note["name"])
        if folder_path:
            return f"{folder_path}/{safe_name}.note"
        return f"{safe_name}.note"

    def _parse_apple_date_to_ms(self, date_str: str) -> int | None:
        """
        Parse Apple Notes date string to milliseconds since epoch.

        Args:
            date_str: Date like "Thursday, October 4, 2018 at 11:45:18 AM"

        Returns:
            Timestamp in milliseconds, or None if parsing fails
        """
        if not date_str:
            return None

        try:
            # Handle narrow non-breaking space (U+202F) before AM/PM
            date_str = date_str.replace('\u202f', ' ')

            formats = [
                "%A, %B %d, %Y at %I:%M:%S %p",  # Thursday, October 4, 2018 at 11:45:18 AM
                "%B %d, %Y at %I:%M:%S %p",      # October 4, 2018 at 11:45:18 AM
                "%A, %B %d, %Y at %H:%M:%S",     # 24-hour variant
                "%B %d, %Y at %H:%M:%S",         # 24-hour variant
            ]

            for fmt in formats:
                try:
                    parsed = datetime.strptime(date_str, fmt)
                    return int(parsed.timestamp() * 1000)
                except ValueError:
                    continue

            logger.warning(f"Could not parse Apple Notes date: {date_str}")
            return None

        except Exception as e:
            logger.warning(f"Error parsing date '{date_str}': {e}")
            return None
