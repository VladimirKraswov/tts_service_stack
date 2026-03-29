from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass(slots=True)
class SynthRequest:
    text: str
    voice_id: str | None = None
    lora_name: str | None = None
    language: str = 'ru'


@dataclass(slots=True)
class SynthChunk:
    wav_bytes: bytes
    seq_no: int
    text: str
    is_last: bool


class TTSEngine(ABC):
    @abstractmethod
    async def warmup(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def synthesize_stream(self, request: SynthRequest) -> AsyncIterator[SynthChunk]:
        raise NotImplementedError

    @abstractmethod
    async def synthesize_preview(self, request: SynthRequest) -> bytes:
        raise NotImplementedError
