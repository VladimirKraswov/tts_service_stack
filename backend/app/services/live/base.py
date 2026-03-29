from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass(slots=True)
class LiveSynthesisRequest:
    text: str
    voice_id: str | None = None
    lora_name: str | None = None
    language: str = 'ru'


@dataclass(slots=True)
class LiveAudioChunk:
    pcm_bytes: bytes
    seq_no: int
    text: str
    sample_rate: int
    mime: str = 'audio/l16'
    is_last: bool = False


class LiveEngine(ABC):
    @abstractmethod
    async def warmup(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def synthesize_segment(self, request: LiveSynthesisRequest) -> AsyncIterator[LiveAudioChunk]:
        raise NotImplementedError