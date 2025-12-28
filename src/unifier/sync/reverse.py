"""
Reverse sync engine: Supernote -> Apple Notes.

Handles syncing changes made to .txt files on Supernote back to Apple Notes.
"""

import hashlib
import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..converters.markdown_to_html import markdown_to_apple_html, extract_title_from_markdown
from ..state import StateDatabase, SyncDirection
from .supernote_watcher import ChangedFile, ChangeType

logger = logging.getLogger(__name__)

ORIGINALS_FOLDER_NAME = "Originals (Supernote Sync)"


@dataclass
class ReverseSyncResult:
    """Result of a reverse sync operation."""
    success: bool
    apple_note_id: str
    action: str  # 'updated', 'deleted', 'backed_up', 'skipped'
    error: str | None = None
    original_backed_up: bool = False


class ReverseSyncEngine:
    """
    Engine for syncing Supernote changes back to Apple Notes.

    Safety mechanism:
    - Before modifying/deleting an Apple Note, the original is copied
      to an "Originals" folder that is NOT synced to Supernote.
    - This allows users to restore from originals if needed.
    """

    def __init__(
        self,
        swift_bridge_path: Path,
        state_db: StateDatabase,
    ):
        self.swift_bridge = swift_bridge_path
        self.state_db = state_db
        self._originals_folder_id: str | None = None

    def _run_swift_command(self, *args) -> dict:
        """Run a Swift bridge command and return JSON result."""
        cmd = [str(self.swift_bridge)] + list(args)

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            try:
                error_data = json.loads(result.stderr)
                error_msg = error_data.get('error', error_msg)
            except (json.JSONDecodeError, TypeError):
                pass
            raise RuntimeError(f"Swift bridge error: {error_msg}")

        return json.loads(result.stdout)

    def _ensure_originals_folder(self) -> str:
        """Ensure the Originals folder exists and return its ID."""
        if self._originals_folder_id:
            return self._originals_folder_id

        # Check if folder exists
        result = self._run_swift_command("get-folder-by-name", ORIGINALS_FOLDER_NAME)

        if result.get("found"):
            self._originals_folder_id = result["id"]
            return self._originals_folder_id

        # Create the folder
        result = self._run_swift_command("create-folder", ORIGINALS_FOLDER_NAME)
        self._originals_folder_id = result["id"]
        logger.info(f"Created Originals folder: {ORIGINALS_FOLDER_NAME}")
        return self._originals_folder_id

    def _get_apple_note_content(self, note_id: str) -> dict | None:
        """Get current Apple Note content."""
        try:
            return self._run_swift_command("export-note", note_id, "--html")
        except Exception as e:
            logger.error(f"Failed to get Apple Note {note_id}: {e}")
            return None

    def _backup_to_originals(self, note_id: str, reason: str) -> bool:
        """
        Create a backup copy of an Apple Note in the Originals folder.

        This creates a NEW note in Originals with the current content,
        preserving the original before we modify/delete it.
        """
        try:
            # Get current content
            note_data = self._get_apple_note_content(note_id)
            if not note_data:
                logger.warning(f"Could not get content for backup: {note_id}")
                return False

            original_html = note_data.get("bodyHTML", "")
            original_plaintext = note_data.get("bodyPlainText", "")
            note_name = note_data.get("name", "Untitled")

            # Ensure Originals folder exists
            originals_folder_id = self._ensure_originals_folder()

            # Create backup note with timestamp in name
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            backup_name = f"{note_name} (Original {timestamp})"

            # Add metadata to the backup body
            metadata_html = f"""
<div><b>Original Backup</b></div>
<div>Backed up: {timestamp}</div>
<div>Reason: {reason}</div>
<div>Original Note ID: {note_id}</div>
<div><br></div>
<div>--- Original Content Below ---</div>
<div><br></div>
{original_html}
"""

            # Write HTML to temp file for Swift bridge
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(metadata_html)
                temp_path = f.name

            try:
                result = self._run_swift_command(
                    "create-note",
                    "--name", backup_name,
                    "--html-file", temp_path,
                    "--folder-id", originals_folder_id,
                )

                backup_note_id = result.get("id")

                # Record in state database
                self.state_db.record_original(
                    apple_note_id=note_id,
                    original_content=original_plaintext,
                    original_html=original_html,
                    reason=reason,
                    backup_folder_note_id=backup_note_id,
                )

                logger.info(f"Backed up note '{note_name}' to Originals folder")
                return True

            finally:
                Path(temp_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Failed to backup note {note_id}: {e}")
            return False

    def _compute_content_hash(self, content: str) -> str:
        """Compute hash of content for loop detection."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def sync_modified_file(self, change: ChangedFile) -> ReverseSyncResult:
        """
        Sync a modified .txt file back to Apple Notes.

        1. Read new content from Supernote
        2. Backup original Apple Note to Originals folder
        3. Convert Markdown to Apple HTML
        4. Update the Apple Note
        """
        try:
            # Read new content
            if not change.path.exists():
                return ReverseSyncResult(
                    success=False,
                    apple_note_id=change.apple_note_id,
                    action='skipped',
                    error="File no longer exists",
                )

            new_content = change.path.read_text(encoding='utf-8')
            new_hash = self._compute_content_hash(new_content)

            # Check for echo (content we wrote during forward sync)
            if self.state_db.is_echo_from_supernote(change.apple_note_id, new_hash):
                logger.debug(f"Skipping echo from forward sync: {change.path}")
                return ReverseSyncResult(
                    success=True,
                    apple_note_id=change.apple_note_id,
                    action='skipped',
                    error="Echo from forward sync",
                )

            # Backup original to Originals folder
            backup_success = self._backup_to_originals(
                change.apple_note_id,
                reason=f"Modified on Supernote: {change.path.name}"
            )

            # Convert Markdown to HTML
            title, body_markdown = extract_title_from_markdown(new_content)
            html_body = markdown_to_apple_html(body_markdown)

            # Write HTML to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(html_body)
                temp_path = f.name

            try:
                # Update Apple Note
                self._run_swift_command(
                    "update-note",
                    change.apple_note_id,
                    "--html-file", temp_path,
                )

                # Update state to prevent loop
                html_hash = self._compute_content_hash(html_body)
                self.state_db.update_apple_written_hash(
                    change.apple_note_id,
                    html_hash,
                )

                # Also update Supernote state to current
                self.state_db.update_supernote_state(
                    change.apple_note_id,
                    new_hash,
                    change.new_modified_at or 0,
                )

                logger.info(f"Synced changes from Supernote to Apple Note: {title}")

                return ReverseSyncResult(
                    success=True,
                    apple_note_id=change.apple_note_id,
                    action='updated',
                    original_backed_up=backup_success,
                )

            finally:
                Path(temp_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Failed to sync modified file {change.path}: {e}")
            return ReverseSyncResult(
                success=False,
                apple_note_id=change.apple_note_id,
                action='failed',
                error=str(e),
            )

    def sync_deleted_file(self, change: ChangedFile) -> ReverseSyncResult:
        """
        Handle a deleted .txt file on Supernote.

        1. Backup original Apple Note to Originals folder
        2. Delete the Apple Note
        """
        try:
            # Backup original first
            backup_success = self._backup_to_originals(
                change.apple_note_id,
                reason=f"Deleted on Supernote: {change.path.name}"
            )

            # Delete the Apple Note
            self._run_swift_command("delete-note", change.apple_note_id)

            logger.info(f"Deleted Apple Note (backed up to Originals): {change.apple_note_id}")

            return ReverseSyncResult(
                success=True,
                apple_note_id=change.apple_note_id,
                action='deleted',
                original_backed_up=backup_success,
            )

        except Exception as e:
            logger.error(f"Failed to handle deleted file {change.path}: {e}")
            return ReverseSyncResult(
                success=False,
                apple_note_id=change.apple_note_id,
                action='failed',
                error=str(e),
            )

    def process_change(self, change: ChangedFile) -> ReverseSyncResult:
        """Process a single change from Supernote."""
        if change.change_type == ChangeType.MODIFIED:
            return self.sync_modified_file(change)
        elif change.change_type == ChangeType.DELETED:
            return self.sync_deleted_file(change)
        else:
            return ReverseSyncResult(
                success=False,
                apple_note_id=change.apple_note_id,
                action='skipped',
                error=f"Unknown change type: {change.change_type}",
            )

    def create_apple_note_from_txt(
        self,
        txt_path: Path,
        apple_folder_path: str,
    ) -> ReverseSyncResult:
        """
        Create a new Apple Note from a .txt file on Supernote.

        This handles new .txt files that were manually created on Supernote.

        Args:
            txt_path: Full path to .txt file on Supernote
            apple_folder_path: Target folder path in Apple Notes (e.g., "Work/Projects")

        Returns:
            ReverseSyncResult with the new note ID
        """
        try:
            if not txt_path.exists():
                return ReverseSyncResult(
                    success=False,
                    apple_note_id="",
                    action='failed',
                    error=f"File not found: {txt_path}",
                )

            # Read content
            content = txt_path.read_text(encoding='utf-8')
            content_hash = self._compute_content_hash(content)

            # Extract title and convert to HTML
            title, body_markdown = extract_title_from_markdown(content)
            html_body = markdown_to_apple_html(body_markdown)

            # If title is empty, use filename
            if not title or title == "Untitled":
                title = txt_path.stem

            # Write HTML to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(html_body)
                temp_path = f.name

            try:
                # Create Apple Note
                if apple_folder_path:
                    result = self._run_swift_command(
                        "create-note",
                        "--name", title,
                        "--html-file", temp_path,
                        "--folder-name", apple_folder_path.split("/")[-1],  # Use last folder name
                    )
                else:
                    result = self._run_swift_command(
                        "create-note",
                        "--name", title,
                        "--html-file", temp_path,
                    )

                new_note_id = result.get("id", "")

                if new_note_id:
                    # Record in state database for future tracking
                    html_hash = self._compute_content_hash(html_body)
                    self.state_db.update_apple_written_hash(new_note_id, html_hash)

                    logger.info(f"Created Apple Note '{title}' from Supernote .txt")

                    return ReverseSyncResult(
                        success=True,
                        apple_note_id=new_note_id,
                        action='created',
                    )
                else:
                    return ReverseSyncResult(
                        success=False,
                        apple_note_id="",
                        action='failed',
                        error="No note ID returned",
                    )

            finally:
                Path(temp_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Failed to create Apple Note from {txt_path}: {e}")
            return ReverseSyncResult(
                success=False,
                apple_note_id="",
                action='failed',
                error=str(e),
            )
