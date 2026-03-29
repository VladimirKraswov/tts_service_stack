from __future__ import annotations

import asyncio
import io
import math
import struct
import wave

from app.core.config import get_settings
from app.services.preview.base import PreviewEngine, PreviewRequest


class MockPreviewEngine(PreviewEngine):
    def __init__(self) -> None:
        self.settings = get_settings()
        self._warm = False

    async def warmup(self) -> None:
        if self._warm:
            return
        await asyncio.sleep(0.02)
        self._warm = True

    async def synthesize(self, request: PreviewRequest) -> bytes:
        await self.warmup()
        duration = min(2.2, max(0.35, len(request.text) / 65))
        pcm = self._generate_pcm(request.text, duration)
        return self._pcm_to_wav(pcm)

    def _generate_pcm(self, seed_text: str, duration: float) -> bytes:
        sample_rate = self.settings.audio_sample_rate
        frames = int(sample_rate * duration)
        base_freq = 320 + (sum(ord(char) for char in seed_text) % 220)
        amplitude = 12000
        raw = []
        for i in range(frames):
            value = int(amplitude * math.sin(2 * math.pi * base_freq * (i / sample_rate)))
            raw.append(struct.pack('<h', value))
        return b''.join(raw)

    def _pcm_to_wav(self, pcm_data: bytes) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.settings.audio_sample_rate)
            wav_file.writeframes(pcm_data)
        return buffer.getvalue()