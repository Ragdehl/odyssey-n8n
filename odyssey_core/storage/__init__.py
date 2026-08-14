"""Safe raw-text storage primitives for Odyssey Core."""

from .repository import (
    InvalidNotePath,
    NoteAlreadyExistsError,
    NoteUnavailableError,
    VaultAccessError,
    VaultRepository,
)

__all__ = [
    "InvalidNotePath",
    "NoteAlreadyExistsError",
    "NoteUnavailableError",
    "VaultAccessError",
    "VaultRepository",
]
