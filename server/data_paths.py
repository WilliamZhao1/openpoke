"""Resolve the configured root for persistent application data."""

from pathlib import Path

from .config import get_settings


def get_data_dir() -> Path:
    """Return the startup-configured data root without creating it.

    Relative paths are resolved against the process working directory. Set
    OPENPOKE_DATA_DIR before importing application services and restart the
    backend after changing it; existing stores retain their original paths.
    """
    return get_settings().data_dir.expanduser().resolve()
