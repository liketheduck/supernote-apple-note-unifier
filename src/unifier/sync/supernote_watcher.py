"""
Supernote watcher for detecting .txt file changes.

Scans the Supernote filesystem for modified or deleted .txt files
that originated from Apple Notes sync.
"""

import hashlib
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..state import StateDatabase, NoteState

logger = logging.getLogger(__name__)


class ChangeType(Enum):
    """Type of change detected."""
    MODIFIED = "modified"
    DELETED = "deleted"


@dataclass
class ChangedFile:
    """Represents a detected change on Supernote."""
    path: Path
    change_type: ChangeType
    apple_note_id: str
    new_content_hash: str | None  # None if deleted
    new_modified_at: int | None   # mtime in ms, None if deleted
    previous_hash: str | None     # Previous known hash


class SupernoteWatcher:
    """
    Watches for changes to .txt files on Supernote.

    Only monitors files that were created by the forward sync
    (Apple Notes -> Supernote).
    """

    def __init__(self, apple_notes_dir: Path, state_db: StateDatabase):
        """
        Initialize the watcher.

        Args:
            apple_notes_dir: Path to Apple/ directory on Supernote
            state_db: State database for tracking sync state
        """
        self.apple_notes_dir = apple_notes_dir
        self.state_db = state_db

    def compute_content_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file content."""
        content = file_path.read_text(encoding='utf-8')
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get_file_mtime_ms(self, file_path: Path) -> int:
        """Get file modification time in milliseconds."""
        return int(file_path.stat().st_mtime * 1000)

    def scan_for_changes(self) -> list[ChangedFile]:
        """
        Scan for changes to .txt files.

        Returns:
            List of ChangedFile objects representing detected changes
        """
        changes: list[ChangedFile] = []

        # Get all tracked .txt files from state
        txt_states = self.state_db.get_all_txt_states()

        # Map output paths to states for quick lookup
        path_to_state: dict[str, NoteState] = {}
        for state in txt_states:
            if state and state.output_path:
                path_to_state[state.output_path] = state

        # Check each tracked file
        for output_path, state in path_to_state.items():
            file_path = Path(output_path)

            if not file_path.exists():
                # File was deleted on Supernote
                changes.append(ChangedFile(
                    path=file_path,
                    change_type=ChangeType.DELETED,
                    apple_note_id=state.apple_note_id,
                    new_content_hash=None,
                    new_modified_at=None,
                    previous_hash=state.supernote_content_hash,
                ))
                logger.info(f"Detected deletion: {file_path}")
                continue

            # Check if content changed
            try:
                current_hash = self.compute_content_hash(file_path)
                current_mtime = self.get_file_mtime_ms(file_path)

                # Compare with stored state
                previous_hash = state.supernote_content_hash

                if previous_hash and current_hash != previous_hash:
                    # Content changed
                    changes.append(ChangedFile(
                        path=file_path,
                        change_type=ChangeType.MODIFIED,
                        apple_note_id=state.apple_note_id,
                        new_content_hash=current_hash,
                        new_modified_at=current_mtime,
                        previous_hash=previous_hash,
                    ))
                    logger.info(f"Detected modification: {file_path}")

            except Exception as e:
                logger.error(f"Error checking file {file_path}: {e}")
                continue

        return changes

    def scan_for_new_files(self) -> list[Path]:
        """
        Scan for .txt files that aren't tracked yet.

        This can happen if files are manually added to the Apple/ directory.

        Returns:
            List of paths to untracked .txt files
        """
        untracked: list[Path] = []

        if not self.apple_notes_dir.exists():
            return untracked

        # Get all tracked output paths
        txt_states = self.state_db.get_all_txt_states()
        tracked_paths = {state.output_path for state in txt_states if state}

        # Scan filesystem
        for txt_file in self.apple_notes_dir.rglob("*.txt"):
            if str(txt_file) not in tracked_paths:
                untracked.append(txt_file)
                logger.info(f"Found untracked .txt file: {txt_file}")

        return untracked

    def get_apple_folder_path(self, txt_path: Path) -> str:
        """
        Extract Apple Notes folder path from Supernote .txt file path.

        Example:
            Input: /Volumes/.../Note/Apple/Work/Projects/note.txt
            Output: Work/Projects

        Args:
            txt_path: Full path to .txt file on Supernote

        Returns:
            Folder path relative to Apple Notes root (without Apple/ prefix)
        """
        try:
            # Get path relative to apple_notes_dir
            relative = txt_path.relative_to(self.apple_notes_dir)
            # Remove the filename to get just the folder path
            folder_path = relative.parent
            return str(folder_path) if str(folder_path) != "." else ""
        except ValueError:
            # Path is not relative to apple_notes_dir
            return ""

    def get_note_title_from_path(self, txt_path: Path) -> str:
        """
        Extract note title from .txt filename.

        Args:
            txt_path: Path to .txt file

        Returns:
            Title (filename without .txt extension)
        """
        return txt_path.stem
