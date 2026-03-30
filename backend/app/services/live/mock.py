from __future__ import annotations

import asyncio
import math
import struct
from typing import AsyncIterator

from app.core.config import get_settings
from app.services.live.base import (
    BufferedLiveStreamSession,
    LiveAudioChunk,
    LiveEngine,
    LiveStreamSession,
    LiveSynthesisRequest,
)


class MockLiveEngine(LiveEngine):
    def __init__(self) -> None:
        self.settings = get_settings()
        self._warm = False

    async def warmup(self) -> None:
        if self._warm:
            return
        await asyncio.sleep(0.02)
        self._warm = True

    async def open_session(self) -> LiveStreamSession:
        await self.warmup()
        session = BufferedLiveStreamSession(self.synthesize_segment)
        await session.start()
        return session

    async def synthesize_segment(self, request: LiveSynthesisRequest) -> AsyncIterator[LiveAudioChunk]:
        await self.warmup()

        sample_rate = self.settings.audio_sample_rate
        duration = min(0.9, max(0.16, len(request.text) / 55))
        frames = int(sample_rate * duration)
        base_freq = 320 + (sum(ord(char) for char in request.text) % 220)
        amplitude = 12000

        raw = []
        for i in range(frames):
            value = int(amplitude * math.sin(2 * math.pi * base_freq * (i / sample_rate)))
            raw.append(struct.pack('<h', value))
        pcm = b''.join(raw)

        bytes_per_ms = max(2, int(sample_rate * 2 / 1000))
        chunk_size = max(1600, bytes_per_ms * self.settings.live_pcm_chunk_ms)
        parts = [pcm[i:i + chunk_size] for i in range(0, len(pcm), chunk_size)]

        for seq_no, part in enumerate(parts):
            await asyncio.sleep(0.015)
            yield LiveAudioChunk(
                pcm_bytes=part,
                seq_no=seq_no,
                text=request.text,
                sample_rate=sample_rate,
                is_last=seq_no == len(parts) - 1,
            )