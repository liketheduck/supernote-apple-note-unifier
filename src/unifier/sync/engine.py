"""
Bidirectional sync engine.

Coordinates forward (Apple -> Supernote) and reverse (Supernote -> Apple) sync.
"""

import hashlib
import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..state import StateDatabase, SyncDirection
from ..supernote.paths import ensure_apple_notes_directory
from .supernote_watcher import SupernoteWatcher, ChangeType
from .reverse import ReverseSyncEngine, ORIGINALS_FOLDER_NAME

logger = logging.getLogger(__name__)


@dataclass
class BidirectionalSyncStats:
    """Statistics for a bidirectional sync run."""
    # Forward sync stats (Apple -> Supernote)
    forward_total: int = 0
    forward_created: int = 0
    forward_updated: int = 0
    forward_skipped: int = 0
    forward_failed: int = 0

    # Reverse sync stats (Supernote -> Apple)
    reverse_modified: int = 0
    reverse_deleted: int = 0
    reverse_created: int = 0  # New .txt files from Supernote
    reverse_skipped: int = 0
    reverse_failed: int = 0
    originals_backed_up: int = 0

    # Conflict stats
    conflicts_detected: int = 0
    conflicts_resolved_apple_wins: int = 0

    errors: list[dict] = field(default_factory=list)


class BidirectionalSyncEngine:
    """
    Main engine for bidirectional sync between Apple Notes and Supernote.

    Conflict resolution: Apple wins by default.
    - If both Apple and Supernote changed since last sync, Apple version takes precedence.
    - The Supernote change is lost (but could be recovered from Supernote file backup).
    """

    def __init__(
        self,
        supernote_base: Path,
        state_db_path: Path,
        swift_bridge_path: Path,
        backup_dir: Path | None = None,
    ):
        self.supernote_base = supernote_base
        self.output_base = ensure_apple_notes_directory(supernote_base)
        self.state_db = StateDatabase(state_db_path)
        self.swift_bridge = swift_bridge_path
        self.backup_dir = backup_dir or (Path.home() / ".local/share/supernote-unifier/backups")

        # Initialize components
        self.watcher = SupernoteWatcher(self.output_base, self.state_db)
        self.reverse_engine = ReverseSyncEngine(swift_bridge_path, self.state_db)

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

    def create_backup(self) -> str | None:
        """
        Create a full backup of Apple Notes before sync.

        Returns:
            Path to backup file, or None if backup failed
        """
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            result = self._run_swift_command("backup-all", "--output-dir", str(self.backup_dir))
            backup_path = result.get("backupPath")
            logger.info(f"Created backup: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return None

    def _compute_content_hash(self, note: dict) -> str:
        """Compute content hash for a note."""
        content = f"{note.get('name', '')}|{note.get('bodyPlainText', '')}|{note.get('modificationDate', '')}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _should_exclude_folder(self, folder_path: str) -> bool:
        """Check if a folder should be excluded from sync."""
        excluded = {
            ORIGINALS_FOLDER_NAME.lower(),
            "recently deleted",
        }
        return folder_path.lower() in excluded

    def run_reverse_sync(
        self,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> BidirectionalSyncStats:
        """
        Run reverse sync only (Supernote -> Apple Notes).

        Returns:
            Sync statistics
        """
        stats = BidirectionalSyncStats()

        # Scan for changes on Supernote (existing tracked files)
        changes = self.watcher.scan_for_changes()
        logger.info(f"Found {len(changes)} changes on Supernote")

        for change in changes:
            if dry_run:
                action = "delete" if change.change_type == ChangeType.DELETED else "update"
                print(f"Would {action} Apple Note: {change.apple_note_id} (from {change.path.name})")
                if change.change_type == ChangeType.DELETED:
                    stats.reverse_deleted += 1
                else:
                    stats.reverse_modified += 1
                continue

            # Check for conflict (both sides changed)
            state = self.state_db.get_note_state(change.apple_note_id)
            if state:
                # Get current Apple Note
                try:
                    apple_note = self._run_swift_command(
                        "export-note", change.apple_note_id, "--html"
                    )
                    current_apple_hash = self._compute_content_hash(apple_note)

                    # If Apple changed since last sync AND Supernote changed
                    if current_apple_hash != state.content_hash:
                        stats.conflicts_detected += 1
                        stats.conflicts_resolved_apple_wins += 1
                        logger.info(
                            f"Conflict detected for {change.path.name}: "
                            f"Apple wins (default behavior)"
                        )
                        # Skip reverse sync - forward sync will push Apple version
                        stats.reverse_skipped += 1
                        continue

                except Exception as e:
                    logger.warning(f"Could not check for conflict: {e}")

            # Process the change
            result = self.reverse_engine.process_change(change)

            if result.success:
                if result.action == 'updated':
                    stats.reverse_modified += 1
                elif result.action == 'deleted':
                    stats.reverse_deleted += 1
                elif result.action == 'skipped':
                    stats.reverse_skipped += 1

                if result.original_backed_up:
                    stats.originals_backed_up += 1
            else:
                stats.reverse_failed += 1
                stats.errors.append({
                    "file": str(change.path),
                    "apple_note_id": change.apple_note_id,
                    "error": result.error,
                })

        # Scan for NEW .txt files on Supernote (not yet tracked)
        new_files = self.watcher.scan_for_new_files()
        logger.info(f"Found {len(new_files)} new .txt files on Supernote")

        for txt_path in new_files:
            # Get the Apple folder path from the Supernote path
            apple_folder_path = self.watcher.get_apple_folder_path(txt_path)

            if dry_run:
                print(f"Would create Apple Note: {txt_path.stem} in folder '{apple_folder_path or 'Notes'}'")
                stats.reverse_created += 1
                continue

            # Create the Apple Note
            result = self.reverse_engine.create_apple_note_from_txt(txt_path, apple_folder_path)

            if result.success:
                stats.reverse_created += 1
                logger.info(f"Created Apple Note from new Supernote file: {txt_path.name}")
            else:
                stats.reverse_failed += 1
                stats.errors.append({
                    "file": str(txt_path),
                    "error": result.error,
                })

        return stats

    def run_forward_sync(
        self,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> BidirectionalSyncStats:
        """
        Run forward sync only (Apple Notes -> Supernote).

        This is a wrapper around the existing Orchestrator logic.

        Returns:
            Sync statistics
        """
        from ..orchestrator import Orchestrator
        from ..generators.base import GeneratorType

        stats = BidirectionalSyncStats()

        orchestrator = Orchestrator(
            supernote_base=self.supernote_base,
            state_db_path=self.state_db.db_path,
            swift_bridge_path=self.swift_bridge,
            generator_type=GeneratorType.AUTO,
        )

        result = orchestrator.run(dry_run=dry_run, verbose=verbose)

        stats.forward_total = result.get("total", 0)
        stats.forward_created = result.get("created", 0)
        stats.forward_updated = result.get("updated", 0)
        stats.forward_skipped = result.get("skipped", 0)
        stats.forward_failed = result.get("failed", 0)
        stats.errors.extend(result.get("errors", []))

        return stats

    def run_bidirectional(
        self,
        dry_run: bool = False,
        verbose: bool = False,
        create_backup: bool = True,
    ) -> BidirectionalSyncStats:
        """
        Run full bidirectional sync.

        Order of operations:
        1. Create backup (if enabled)
        2. Reverse sync: Supernote -> Apple Notes
        3. Forward sync: Apple Notes -> Supernote

        Reverse runs first so that Supernote changes are captured before
        forward sync potentially overwrites them.

        Args:
            dry_run: If True, don't make changes
            verbose: If True, verbose logging
            create_backup: If True, create Apple Notes backup first

        Returns:
            Combined sync statistics
        """
        stats = BidirectionalSyncStats()

        # Step 1: Create backup
        if create_backup and not dry_run:
            backup_path = self.create_backup()
            if not backup_path:
                logger.warning("Backup failed, but continuing with sync")

        # Step 2: Reverse sync (Supernote -> Apple)
        logger.info("Starting reverse sync (Supernote -> Apple Notes)...")
        reverse_stats = self.run_reverse_sync(dry_run=dry_run, verbose=verbose)

        stats.reverse_modified = reverse_stats.reverse_modified
        stats.reverse_deleted = reverse_stats.reverse_deleted
        stats.reverse_skipped = reverse_stats.reverse_skipped
        stats.reverse_failed = reverse_stats.reverse_failed
        stats.originals_backed_up = reverse_stats.originals_backed_up
        stats.conflicts_detected = reverse_stats.conflicts_detected
        stats.conflicts_resolved_apple_wins = reverse_stats.conflicts_resolved_apple_wins
        stats.errors.extend(reverse_stats.errors)

        # Step 3: Forward sync (Apple -> Supernote)
        logger.info("Starting forward sync (Apple Notes -> Supernote)...")
        forward_stats = self.run_forward_sync(dry_run=dry_run, verbose=verbose)

        stats.forward_total = forward_stats.forward_total
        stats.forward_created = forward_stats.forward_created
        stats.forward_updated = forward_stats.forward_updated
        stats.forward_skipped = forward_stats.forward_skipped
        stats.forward_failed = forward_stats.forward_failed
        stats.errors.extend(forward_stats.errors)

        return stats

    def update_supernote_hashes(self):
        """
        Update stored hashes for all .txt files on Supernote.

        Call this after forward sync to record current state.
        """
        txt_states = self.state_db.get_all_txt_states()

        for state in txt_states:
            if not state or not state.output_path:
                continue

            file_path = Path(state.output_path)
            if not file_path.exists():
                continue

            try:
                content_hash = self.watcher.compute_content_hash(file_path)
                modified_at = self.watcher.get_file_mtime_ms(file_path)

                self.state_db.update_supernote_state(
                    state.apple_note_id,
                    content_hash,
                    modified_at,
                )
            except Exception as e:
                logger.warning(f"Failed to update hash for {file_path}: {e}")
