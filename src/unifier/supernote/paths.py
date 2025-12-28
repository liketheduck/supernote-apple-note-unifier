"""Path management for Supernote filesystem."""

from pathlib import Path

# Default paths
DEFAULT_SUPERNOTE_BASE = Path("/Volumes/Storage/Supernote")
DEFAULT_DATA_PATH = DEFAULT_SUPERNOTE_BASE / "data"


def get_user_data_path(supernote_base: Path = DEFAULT_SUPERNOTE_BASE) -> Path | None:
    """
    Find the user's data directory in Supernote filesystem.

    Returns the path like: /Volumes/Storage/Supernote/data/{email}/Supernote
    """
    data_path = supernote_base / "data"
    if not data_path.exists():
        return None

    # Find user directory (email-based)
    for item in data_path.iterdir():
        if item.is_dir() and "@" in item.name:
            user_supernote_path = item / "Supernote"
            if user_supernote_path.exists():
                return user_supernote_path

    return None


def get_note_directory(supernote_base: Path = DEFAULT_SUPERNOTE_BASE) -> Path | None:
    """
    Get the Note directory where .note files are stored.

    Returns path like: /Volumes/Storage/Supernote/data/{email}/Supernote/Note
    """
    user_path = get_user_data_path(supernote_base)
    if user_path:
        note_path = user_path / "Note"
        if note_path.exists():
            return note_path
    return None


def ensure_apple_notes_directory(supernote_base: Path = DEFAULT_SUPERNOTE_BASE) -> Path:
    """
    Ensure the Apple Notes directory exists in Supernote.

    Creates: /Volumes/Storage/Supernote/data/{email}/Supernote/Note/Apple

    Returns the path to the Apple notes directory.
    """
    note_dir = get_note_directory(supernote_base)
    if not note_dir:
        raise RuntimeError(
            f"Could not find Supernote Note directory. "
            f"Ensure {supernote_base} is mounted and contains user data."
        )

    apple_dir = note_dir / "Apple"
    apple_dir.mkdir(exist_ok=True)
    return apple_dir


def verify_supernote_mounted(supernote_base: Path = DEFAULT_SUPERNOTE_BASE) -> bool:
    """Check if the Supernote volume is mounted and accessible."""
    return supernote_base.exists() and supernote_base.is_dir()


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """
    Make a filename safe for the filesystem.

    - Removes/replaces problematic characters
    - Truncates to max_length
    """
    unsafe = '<>:"/\\|?*'
    result = name
    for char in unsafe:
        result = result.replace(char, '_')

    # Remove leading/trailing whitespace and dots
    result = result.strip().strip('.')

    # Truncate if too long
    if len(result) > max_length:
        result = result[:max_length]

    return result
