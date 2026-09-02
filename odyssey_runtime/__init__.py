"""Thin external runtime boundary for the Odyssey Core application."""

from .composition import RuntimeComposition, build_runtime_from_environment
from .serialization import application_result_to_response

__all__ = [
    "RuntimeComposition",
    "application_result_to_response",
    "build_runtime_from_environment",
]
