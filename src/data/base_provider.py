"""Abstract data-source interface. Every provider must implement this."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass(frozen=True)
class Tick:
    asset: str
    timestamp: float
    price: float
    source: str = "unknown"


class DataProvider(ABC):
    """Async data feed. Subclasses yield Tick objects."""

    name: str = "base"

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def subscribe(self, assets: list[str]) -> None: ...

    @abstractmethod
    async def stream(self) -> AsyncIterator[Tick]:
        """Yield Tick objects forever. Must auto-recover from drops."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...
