"""
Sync handler for Supernote Personal Cloud.

Handles registration of new files in the MariaDB database so they appear on the device.
"""

import hashlib
import logging
import random
import subprocess
import time
from pathlib import Path
from typing import Optional

from unifier import config

logger = logging.getLogger(__name__)


def compute_file_md5(file_path: Path) -> str:
    """Compute MD5 hash of a file."""
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()


def generate_snowflake_id() -> int:
    """
    Generate a snowflake-style ID for database entries.

    Format: (timestamp_ms - epoch) << 22 | random_bits
    Uses a custom epoch similar to Supernote's implementation.
    """
    # Supernote epoch (approximate - 2020-01-01)
    epoch_ms = 1577836800000
    timestamp_ms = int(time.time() * 1000)

    # 22 bits for random/sequence
    random_bits = random.getrandbits(22)

    snowflake = ((timestamp_ms - epoch_ms) << 22) | random_bits
    return snowflake


def escape_sql(value: str) -> str:
    """Escape single quotes for SQL strings."""
    return value.replace("'", "''")


class PersonalCloudSync:
    """
    Sync handler for Supernote Personal Cloud (self-hosted).

    Registers new files in the MariaDB database so they sync to the device.

    Configuration is loaded from environment variables (see .env.example):
    - SUPERNOTE_DOCKER_CONTAINER: Docker container name (default: supernote-mariadb)
    - SUPERNOTE_DB_NAME: Database name (default: supernotedb)
    - SUPERNOTE_DB_USER: Database username (default: supernote)
    - SUPERNOTE_DB_PASSWORD: Database password (required)
    """

    def __init__(
        self,
        container_name: Optional[str] = None,
        database_name: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        # Use config module for defaults, allow override via constructor
        self.container_name = container_name or config.get_docker_container()
        self.database_name = database_name or config.get_db_name()
        self.username = username or config.get_db_user()

        # Password: use provided value, or get from config (which may raise)
        if password:
            self.password = password
        else:
            try:
                self.password = config.get_db_password()
            except ValueError:
                # Allow initialization without password for is_available() checks
                self.password = ""

        # Cache for directory IDs
        self._directory_cache: dict[str, int] = {}
        self._user_id: Optional[int] = None

    def is_available(self) -> bool:
        """Check if MariaDB container is running."""
        try:
            result = subprocess.run(
                ["docker", "exec", self.container_name, "mysqladmin", "ping",
                 f"-u{self.username}", f"-p{self.password}"],
                capture_output=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"Personal Cloud database not available: {e}")
            return False

    def _run_query(self, query: str, fetch: bool = False) -> Optional[str]:
        """Run a SQL query against the database."""
        cmd = [
            "docker", "exec", self.container_name, "mysql",
            f"-u{self.username}", f"-p{self.password}", self.database_name,
            "-N", "-e", query
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error(f"Query failed: {result.stderr}")
                return None
            return result.stdout.strip() if fetch else ""
        except Exception as e:
            logger.error(f"Query error: {e}")
            return None

    def _get_user_id(self) -> Optional[int]:
        """Get the user ID from existing files."""
        if self._user_id:
            return self._user_id

        query = """
            SELECT user_id FROM f_user_file
            WHERE is_active = 'Y' AND user_id > 0
            LIMIT 1;
        """
        result = self._run_query(query, fetch=True)
        if result:
            self._user_id = int(result)
            return self._user_id
        return None

    def _get_note_directory_id(self) -> Optional[int]:
        """Get the ID of the 'Note' directory."""
        query = """
            SELECT id FROM f_user_file
            WHERE file_name = 'Note' AND is_folder = 'Y' AND is_active = 'Y'
            LIMIT 1;
        """
        result = self._run_query(query, fetch=True)
        return int(result) if result else None

    def _get_or_create_directory(self, dir_name: str, parent_id: int) -> Optional[int]:
        """Get or create a directory entry."""
        cache_key = f"{parent_id}/{dir_name}"
        if cache_key in self._directory_cache:
            return self._directory_cache[cache_key]

        # Check if exists
        query = f"""
            SELECT id FROM f_user_file
            WHERE file_name = '{escape_sql(dir_name)}'
              AND directory_id = {parent_id}
              AND is_folder = 'Y'
              AND is_active = 'Y'
            LIMIT 1;
        """
        result = self._run_query(query, fetch=True)

        if result:
            dir_id = int(result)
            self._directory_cache[cache_key] = dir_id
            return dir_id

        # Create directory
        user_id = self._get_user_id()
        if not user_id:
            logger.error("Could not determine user_id")
            return None

        new_id = generate_snowflake_id()
        now_ms = int(time.time() * 1000)

        insert = f"""
            INSERT INTO f_user_file (
                id, user_id, directory_id, file_name, size, md5,
                is_folder, is_active, create_time, update_time,
                terminal_file_edit_time
            ) VALUES (
                {new_id}, {user_id}, {parent_id}, '{escape_sql(dir_name)}', 0, '',
                'Y', 'Y', NOW(), NOW(), {now_ms}
            );
        """

        if self._run_query(insert) is not None:
            logger.info(f"Created directory: {dir_name} (id={new_id})")
            self._directory_cache[cache_key] = new_id
            return new_id

        return None

    def _ensure_path_exists(self, relative_path: str, note_dir_id: int) -> Optional[int]:
        """
        Ensure all directories in a path exist and return the final directory ID.

        Args:
            relative_path: Path like "Apple/Recipes/file.txt"
            note_dir_id: ID of the Note directory

        Returns:
            ID of the parent directory for the file
        """
        parts = Path(relative_path).parts[:-1]  # Exclude filename

        current_id = note_dir_id
        for part in parts:
            dir_id = self._get_or_create_directory(part, current_id)
            if not dir_id:
                return None
            current_id = dir_id

        return current_id

    def _file_exists(self, file_name: str, directory_id: int) -> Optional[int]:
        """Check if a file already exists and return its ID."""
        query = f"""
            SELECT id FROM f_user_file
            WHERE file_name = '{escape_sql(file_name)}'
              AND directory_id = {directory_id}
              AND is_folder = 'N'
              AND is_active = 'Y'
            LIMIT 1;
        """
        result = self._run_query(query, fetch=True)
        return int(result) if result else None

    def register_file(
        self, file_path: Path, relative_path: str, modified_at_ms: Optional[int] = None
    ) -> bool:
        """
        Register a new file in the sync database.

        Args:
            file_path: Absolute path to the file on disk
            relative_path: Path relative to Note directory (e.g., "Apple/Recipes/Soup.txt")
            modified_at_ms: Timestamp in milliseconds for terminal_file_edit_time.
                           If None, uses current time.

        Returns:
            True if successful
        """
        if not self.is_available():
            logger.warning("Personal Cloud database not available")
            return False

        if not file_path.exists():
            logger.error(f"File does not exist: {file_path}")
            return False

        # Get Note directory ID
        note_dir_id = self._get_note_directory_id()
        if not note_dir_id:
            logger.error("Could not find Note directory in database")
            return False

        # Ensure parent directories exist
        parent_id = self._ensure_path_exists(relative_path, note_dir_id)
        if not parent_id:
            logger.error(f"Could not create directory structure for: {relative_path}")
            return False

        # Get file info
        file_name = Path(relative_path).name
        file_size = file_path.stat().st_size
        file_md5 = compute_file_md5(file_path)
        # Use provided timestamp or fall back to current time
        timestamp_ms = modified_at_ms if modified_at_ms else int(time.time() * 1000)

        # Check if file already exists
        existing_id = self._file_exists(file_name, parent_id)

        if existing_id:
            # Update existing file
            update = f"""
                UPDATE f_user_file
                SET size = {file_size},
                    md5 = '{file_md5}',
                    terminal_file_edit_time = {timestamp_ms},
                    update_time = NOW()
                WHERE id = {existing_id};
            """
            if self._run_query(update) is not None:
                logger.debug(f"Updated file in sync database: {file_name}")
                return True
            return False

        # Create new file entry
        user_id = self._get_user_id()
        if not user_id:
            logger.error("Could not determine user_id")
            return False

        new_id = generate_snowflake_id()

        insert = f"""
            INSERT INTO f_user_file (
                id, user_id, directory_id, file_name, size, md5,
                is_folder, is_active, create_time, update_time,
                terminal_file_edit_time
            ) VALUES (
                {new_id}, {user_id}, {parent_id}, '{escape_sql(file_name)}', {file_size}, '{file_md5}',
                'N', 'Y', NOW(), NOW(), {timestamp_ms}
            );
        """

        if self._run_query(insert) is not None:
            logger.debug(f"Registered new file: {file_name} (id={new_id})")
            return True

        return False
