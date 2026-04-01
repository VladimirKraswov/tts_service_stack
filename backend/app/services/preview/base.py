from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class PreviewRequest:
    text: str
    voice_id: str | None = None
    lora_name: str | None = None
    language: str = 'ru'
    reading_mode: str = 'narration'
    speaking_rate: str | None = None
    paragraph_pause_ms: int = 500


class PreviewEngine(ABC):
    @abstractmethod
    async def warmup(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def synthesize(self, request: PreviewRequest) -> bytes:
        raise NotImplementedError