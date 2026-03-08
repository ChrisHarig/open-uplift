from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

from open_uplift.models import MessageData, SessionData


class SessionProvider(ABC):
    """Base class for tool-specific session data readers."""

    @property
    @abstractmethod
    def tool_name(self) -> str: ...

    @property
    def scaffold_name(self) -> str:
        """Override to provide a different scaffold name than tool_name."""
        return self.tool_name

    @abstractmethod
    def discover_session_files(self) -> Iterator[Path]: ...

    @abstractmethod
    def parse_session(
        self, file_path: Path, from_offset: int = 0
    ) -> tuple[SessionData, list[MessageData], int]:
        """Parse a session file from the given byte offset.
        Returns (session_data, messages, new_byte_offset)."""
        ...
