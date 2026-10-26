"""Safe raw-text storage primitives for Odyssey Core."""

from .repository import (
    InvalidNotePath,
    NoteAlreadyExistsError,
    NoteContentConflictError,
    NoteUnavailableError,
    VaultAccessError,
    VaultRepository,
)

__all__ = [
    "InvalidNotePath",
    "NoteAlreadyExistsError",
    "NoteContentConflictError",
    "NoteUnavailableError",
    "VaultAccessError",
    "VaultRepository",
]
