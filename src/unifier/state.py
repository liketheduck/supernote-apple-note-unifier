"""
State tracking for note synchronization.

Tracks:
- Which Apple Notes have been processed
- Content hashes to detect changes (both directions)
- Generation timestamps
- Output file locations
- Sync direction for loop prevention
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


class SyncDirection(Enum):
    """Direction of last sync operation."""
    TO_SUPERNOTE = "to_supernote"
    FROM_SUPERNOTE = "from_supernote"


@dataclass
class NoteState:
    """State record for a processed note."""
    apple_note_id: str
    apple_folder_path: str
    content_hash: str  # Hash of Apple Note content
    last_processed: datetime
    output_path: str
    generator_type: str
    success: bool
    error: str | None
    # Bidirectional sync fields
    supernote_content_hash: str | None = None  # Hash of .txt on Supernote
    supernote_modified_at: int | None = None   # mtime of .txt (epoch ms)
    last_sync_direction: SyncDirection | None = None
    apple_written_hash: str | None = None  # Hash we wrote TO Apple (loop detection)
    is_locked: bool = False  # True if note is locked in Apple Notes (no reverse sync)


class StateDatabase:
    """SQLite-based state tracking."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS note_state (
        apple_note_id TEXT PRIMARY KEY,
        apple_folder_path TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        last_processed TEXT NOT NULL,
        output_path TEXT NOT NULL,
        generator_type TEXT NOT NULL,
        success INTEGER NOT NULL,
        error TEXT,
        -- Bidirectional sync columns
        supernote_content_hash TEXT,
        supernote_modified_at INTEGER,
        last_sync_direction TEXT,
        apple_written_hash TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_folder_path ON note_state(apple_folder_path);
    CREATE INDEX IF NOT EXISTS idx_content_hash ON note_state(content_hash);
    CREATE INDEX IF NOT EXISTS idx_output_path ON note_state(output_path);

    CREATE TABLE IF NOT EXISTS sync_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        notes_processed INTEGER DEFAULT 0,
        notes_created INTEGER DEFAULT 0,
        notes_updated INTEGER DEFAULT 0,
        notes_failed INTEGER DEFAULT 0,
        generator_type TEXT NOT NULL,
        direction TEXT DEFAULT 'to_supernote'
    );

    CREATE TABLE IF NOT EXISTS originals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        apple_note_id TEXT NOT NULL,
        backup_folder_note_id TEXT,
        original_content TEXT NOT NULL,
        original_html TEXT,
        backed_up_at TEXT NOT NULL,
        reason TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_originals_note ON originals(apple_note_id);
    """

    MIGRATIONS = [
        # Migration 1: Add bidirectional sync columns
        """
        ALTER TABLE note_state ADD COLUMN supernote_content_hash TEXT;
        """,
        """
        ALTER TABLE note_state ADD COLUMN supernote_modified_at INTEGER;
        """,
        """
        ALTER TABLE note_state ADD COLUMN last_sync_direction TEXT;
        """,
        """
        ALTER TABLE note_state ADD COLUMN apple_written_hash TEXT;
        """,
        # Migration 2: Add locked note tracking
        """
        ALTER TABLE note_state ADD COLUMN is_locked INTEGER DEFAULT 0;
        """,
    ]

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._run_migrations()

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(self.SCHEMA)

    def _run_migrations(self):
        """Run schema migrations for existing databases."""
        with self._connect() as conn:
            # Check if bidirectional columns exist
            cursor = conn.execute("PRAGMA table_info(note_state)")
            columns = {row[1] for row in cursor.fetchall()}

            for migration in self.MIGRATIONS:
                # Extract column name from ALTER TABLE statement
                if "ADD COLUMN" in migration:
                    col_name = migration.split("ADD COLUMN")[1].strip().split()[0]
                    if col_name not in columns:
                        try:
                            conn.execute(migration)
                        except sqlite3.OperationalError:
                            pass  # Column already exists

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def get_note_state(self, apple_note_id: str) -> NoteState | None:
        """Get state for a specific note."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM note_state WHERE apple_note_id = ?",
                (apple_note_id,)
            ).fetchone()
            if row:
                direction = None
                if row["last_sync_direction"]:
                    try:
                        direction = SyncDirection(row["last_sync_direction"])
                    except ValueError:
                        pass
                # Handle is_locked column (may not exist in older databases before migration)
                is_locked = False
                try:
                    is_locked = bool(row["is_locked"])
                except (IndexError, KeyError):
                    pass

                return NoteState(
                    apple_note_id=row["apple_note_id"],
                    apple_folder_path=row["apple_folder_path"],
                    content_hash=row["content_hash"],
                    last_processed=datetime.fromisoformat(row["last_processed"]),
                    output_path=row["output_path"],
                    generator_type=row["generator_type"],
                    success=bool(row["success"]),
                    error=row["error"],
                    supernote_content_hash=row["supernote_content_hash"],
                    supernote_modified_at=row["supernote_modified_at"],
                    last_sync_direction=direction,
                    apple_written_hash=row["apple_written_hash"],
                    is_locked=is_locked,
                )
        return None

    def get_state_by_output_path(self, output_path: str) -> NoteState | None:
        """Get state for a note by its Supernote output path."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM note_state WHERE output_path = ?",
                (output_path,)
            ).fetchone()
            if row:
                return self.get_note_state(row["apple_note_id"])
        return None

    def get_all_txt_states(self) -> list[NoteState]:
        """Get all states for .txt files (text-only notes)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT apple_note_id FROM note_state WHERE output_path LIKE '%.txt' AND success = 1"
            ).fetchall()
            return [self.get_note_state(row["apple_note_id"]) for row in rows if row]

    def needs_update(self, apple_note_id: str, content_hash: str) -> bool:
        """Check if note needs to be regenerated."""
        state = self.get_note_state(apple_note_id)
        if state is None:
            return True  # Never processed
        return state.content_hash != content_hash

    def record_success(
        self,
        apple_note_id: str,
        apple_folder_path: str,
        content_hash: str,
        output_path: Path,
        generator_type: str,
        supernote_content_hash: str | None = None,
        direction: SyncDirection = SyncDirection.TO_SUPERNOTE,
        is_locked: bool = False,
    ):
        """Record successful note generation."""
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO note_state
                (apple_note_id, apple_folder_path, content_hash, last_processed,
                 output_path, generator_type, success, error,
                 supernote_content_hash, last_sync_direction, is_locked)
                VALUES (?, ?, ?, ?, ?, ?, 1, NULL, ?, ?, ?)
            """, (
                apple_note_id,
                apple_folder_path,
                content_hash,
                datetime.now().isoformat(),
                str(output_path),
                generator_type,
                supernote_content_hash,
                direction.value,
                1 if is_locked else 0,
            ))

    def record_failure(
        self,
        apple_note_id: str,
        apple_folder_path: str,
        content_hash: str,
        generator_type: str,
        error: str
    ):
        """Record failed note generation."""
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO note_state
                (apple_note_id, apple_folder_path, content_hash, last_processed,
                 output_path, generator_type, success, error)
                VALUES (?, ?, ?, ?, '', ?, 0, ?)
            """, (
                apple_note_id,
                apple_folder_path,
                content_hash,
                datetime.now().isoformat(),
                generator_type,
                error
            ))

    def get_orphaned_outputs(self, current_note_ids: set[str]) -> list[str]:
        """Find output files for notes that no longer exist in Apple Notes."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT apple_note_id, output_path FROM note_state WHERE success = 1"
            ).fetchall()
            return [
                row['output_path']
                for row in rows
                if row['apple_note_id'] not in current_note_ids
            ]

    def get_statistics(self) -> dict:
        """Get processing statistics."""
        with self._connect() as conn:
            stats = {}

            row = conn.execute("SELECT COUNT(*) as total FROM note_state").fetchone()
            stats['total_files'] = row['total']

            row = conn.execute(
                "SELECT COUNT(*) as count FROM note_state WHERE success = 1"
            ).fetchone()
            stats['successful'] = row['count']

            row = conn.execute(
                "SELECT COUNT(*) as count FROM note_state WHERE success = 0"
            ).fetchone()
            stats['failed'] = row['count']

            return stats

    def update_supernote_state(
        self,
        apple_note_id: str,
        supernote_content_hash: str,
        supernote_modified_at: int,
    ):
        """Update Supernote-side state after forward sync."""
        with self._connect() as conn:
            conn.execute("""
                UPDATE note_state
                SET supernote_content_hash = ?,
                    supernote_modified_at = ?,
                    last_sync_direction = ?
                WHERE apple_note_id = ?
            """, (
                supernote_content_hash,
                supernote_modified_at,
                SyncDirection.TO_SUPERNOTE.value,
                apple_note_id,
            ))

    def update_apple_written_hash(self, apple_note_id: str, apple_written_hash: str):
        """Record the hash we wrote to Apple Notes (for loop detection)."""
        with self._connect() as conn:
            conn.execute("""
                UPDATE note_state
                SET apple_written_hash = ?,
                    last_sync_direction = ?
                WHERE apple_note_id = ?
            """, (
                apple_written_hash,
                SyncDirection.FROM_SUPERNOTE.value,
                apple_note_id,
            ))

    def update_content_hash_after_reverse_sync(
        self,
        apple_note_id: str,
        new_content_hash: str,
    ):
        """Update content_hash after reverse sync to prevent false conflicts.

        After reverse sync modifies an Apple Note, we need to update the stored
        content_hash to match the new Apple Note content. Otherwise, the next
        sync will see (current_hash != old_stored_hash) and trigger a false conflict.
        """
        with self._connect() as conn:
            conn.execute("""
                UPDATE note_state
                SET content_hash = ?,
                    last_sync_direction = ?
                WHERE apple_note_id = ?
            """, (
                new_content_hash,
                SyncDirection.FROM_SUPERNOTE.value,
                apple_note_id,
            ))

    def record_original(
        self,
        apple_note_id: str,
        original_content: str,
        original_html: str | None,
        reason: str,
        backup_folder_note_id: str | None = None,
    ):
        """Record original Apple Note content before overwriting."""
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO originals
                (apple_note_id, backup_folder_note_id, original_content, original_html,
                 backed_up_at, reason)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                apple_note_id,
                backup_folder_note_id,
                original_content,
                original_html,
                datetime.now().isoformat(),
                reason,
            ))

    def get_originals(self, apple_note_id: str) -> list[dict]:
        """Get backup history for a note."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM originals
                WHERE apple_note_id = ?
                ORDER BY backed_up_at DESC
            """, (apple_note_id,)).fetchall()
            return [dict(row) for row in rows]

    def is_echo_from_apple(self, apple_note_id: str, apple_content_hash: str) -> bool:
        """Check if Apple Note change is an echo of our reverse sync."""
        state = self.get_note_state(apple_note_id)
        if not state:
            return False
        # If the current Apple content matches what we wrote, it's an echo
        return state.apple_written_hash == apple_content_hash

    def is_echo_from_supernote(self, apple_note_id: str, supernote_content_hash: str) -> bool:
        """Check if Supernote change is an echo of our forward sync."""
        state = self.get_note_state(apple_note_id)
        if not state:
            return False
        # If the current Supernote content matches what we wrote, it's an echo
        return state.supernote_content_hash == supernote_content_hash
