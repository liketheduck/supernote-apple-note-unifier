"""
Configuration management for Supernote Apple Note Unifier.

Loads settings from environment variables with optional .env file support.
"""

import os
from pathlib import Path
from typing import Optional

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    # Look for .env files in project root (parent of src/)
    # .env.local takes precedence over .env
    project_root = Path(__file__).parent.parent.parent
    env_local_path = project_root / ".env.local"
    env_path = project_root / ".env"
    if env_local_path.exists():
        load_dotenv(env_local_path)
    elif env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # dotenv not installed, use environment variables only


def get_env(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """
    Get an environment variable with optional default.

    Args:
        key: Environment variable name
        default: Default value if not set
        required: If True, raise error when not set and no default

    Returns:
        The environment variable value or default

    Raises:
        ValueError: If required=True and variable is not set
    """
    value = os.environ.get(key, default)
    if required and not value:
        raise ValueError(
            f"Required environment variable {key} is not set. "
            f"Set it in your environment or create a .env file."
        )
    return value


def expand_path(path: str) -> Path:
    """Expand ~ and environment variables in a path."""
    return Path(os.path.expandvars(os.path.expanduser(path)))


# =============================================================================
# Database Configuration
# =============================================================================

def get_db_mode() -> str:
    """Get database connection mode: 'docker' or 'tcp'."""
    return get_env("SUPERNOTE_DB_MODE", "docker")


def get_db_password() -> str:
    """
    Get database password from environment.

    This is required for Personal Cloud sync functionality.
    """
    # Check both possible env var names for compatibility
    password = get_env("SUPERNOTE_DB_PASSWORD") or get_env("MYSQL_PASSWORD")
    if not password:
        raise ValueError(
            "Database password not set. "
            "Set SUPERNOTE_DB_PASSWORD in your environment or .env file."
        )
    return password


def get_db_host() -> str:
    """Get database host for TCP mode."""
    return get_env("SUPERNOTE_DB_HOST", "localhost")


def get_db_port() -> int:
    """Get database port for TCP mode."""
    return int(get_env("SUPERNOTE_DB_PORT", "3306"))


def get_db_user() -> str:
    """Get database username."""
    return get_env("SUPERNOTE_DB_USER", "supernote")


def get_db_name() -> str:
    """Get database name."""
    return get_env("SUPERNOTE_DB_NAME", "supernotedb")


def get_docker_container() -> str:
    """Get Docker container name for database access."""
    return get_env("SUPERNOTE_DOCKER_CONTAINER", "supernote-mariadb")


# =============================================================================
# Path Configuration
# =============================================================================

def get_supernote_mount_path() -> Path:
    """Get Supernote storage mount point."""
    path = get_env("SUPERNOTE_MOUNT_PATH", "/Volumes/Storage/Supernote")
    return expand_path(path)


def get_state_db_path() -> Path:
    """Get path to local state database."""
    path = get_env("UNIFIER_STATE_DB", "~/.local/share/supernote-unifier/state.db")
    return expand_path(path)


def get_backup_dir() -> Path:
    """Get path to backup directory."""
    path = get_env("UNIFIER_BACKUP_DIR", "~/.local/share/supernote-unifier/backups")
    return expand_path(path)


def get_log_dir() -> Path:
    """Get path to log directory."""
    path = get_env("UNIFIER_LOG_DIR", "~/.local/share/supernote-unifier/logs")
    return expand_path(path)


# =============================================================================
# Debug / Display
# =============================================================================

def print_config_summary() -> None:
    """Print current configuration (with password masked)."""
    print("Configuration:")
    print(f"  DB Mode: {get_db_mode()}")
    print(f"  Docker Container: {get_docker_container()}")
    print(f"  DB Host: {get_db_host()}")
    print(f"  DB Port: {get_db_port()}")
    print(f"  DB User: {get_db_user()}")
    print(f"  DB Name: {get_db_name()}")

    # Mask password in output
    try:
        get_db_password()
        print("  DB Password: ******** (set)")
    except ValueError:
        print("  DB Password: NOT SET")

    print(f"  Supernote Mount: {get_supernote_mount_path()}")
    print(f"  State DB: {get_state_db_path()}")
    print(f"  Backup Dir: {get_backup_dir()}")
    print(f"  Log Dir: {get_log_dir()}")
