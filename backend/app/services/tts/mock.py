from __future__ import annotations

import asyncio
import io
import math
import struct
import wave
from typing import AsyncIterator

from app.services.tts.base import SynthChunk, SynthRequest, TTSEngine


class MockTTSEngine(TTSEngine):
    def __init__(self) -> None:
        self._is_warm = False

    async def warmup(self) -> None:
        if self._is_warm:
            return
        await asyncio.sleep(0.02)
        self._is_warm = True

    async def synthesize_stream(self, request: SynthRequest) -> AsyncIterator[SynthChunk]:
        await self.warmup()
        words = request.text.split()
        segments = [' '.join(words[i:i + 8]) for i in range(0, max(len(words), 1), 8)] or [request.text]
        for index, segment in enumerate(segments):
            await asyncio.sleep(0.03)
            yield SynthChunk(
                wav_bytes=self._generate_tone_wav(segment, duration=min(0.45, max(0.12, len(segment) / 90))),
                seq_no=index,
                text=segment,
                is_last=index == len(segments) - 1,
            )

    async def synthesize_preview(self, request: SynthRequest) -> bytes:
        await self.warmup()
        duration = min(2.2, max(0.35, len(request.text) / 65))
        return self._generate_tone_wav(request.text, duration=duration)

    def _generate_tone_wav(self, seed_text: str, duration: float) -> bytes:
        sample_rate = 24000
        frames = int(sample_rate * duration)
        base_freq = 320 + (sum(ord(char) for char in seed_text) % 220)
        amplitude = 12000
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            for i in range(frames):
                envelope = 1.0
                if i < sample_rate * 0.01:
                    envelope = i / (sample_rate * 0.01)
                elif i > frames - sample_rate * 0.02:
                    envelope = max(0.0, (frames - i) / (sample_rate * 0.02))
                value = int(amplitude * envelope * math.sin(2 * math.pi * base_freq * (i / sample_rate)))
                wav_file.writeframesraw(struct.pack('<h', value))
        return buffer.getvalue()
