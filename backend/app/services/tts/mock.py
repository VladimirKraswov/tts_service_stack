from __future__ import annotations

import asyncio
import io
import math
import struct
import wave
from typing import AsyncIterator

from app.core.config import get_settings
from app.services.tts.base import SynthChunk, SynthRequest, TTSEngine


class MockTTSEngine(TTSEngine):
    def __init__(self) -> None:
        self.settings = get_settings()
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
            # Yield raw PCM (S16LE) for streaming
            yield SynthChunk(
                wav_bytes=self._generate_tone_raw_pcm(segment, duration=min(0.45, max(0.12, len(segment) / 90))),
                seq_no=index,
                text=segment,
                is_last=index == len(segments) - 1,
            )

    async def synthesize_preview(self, request: SynthRequest) -> bytes:
        await self.warmup()
        duration = min(2.2, max(0.35, len(request.text) / 65))
        # Keep WAV for preview (standard <audio> compatibility)
        pcm = self._generate_tone_raw_pcm(request.text, duration=duration)
        return self._pcm_to_wav(pcm)

    def _generate_tone_raw_pcm(self, seed_text: str, duration: float) -> bytes:
        sample_rate = self.settings.audio_sample_rate
        frames = int(sample_rate * duration)
        base_freq = 320 + (sum(ord(char) for char in seed_text) % 220)
        amplitude = 12000
        raw_data = []
        for i in range(frames):
            envelope = 1.0
            if i < sample_rate * 0.01:
                envelope = i / (sample_rate * 0.01)
            elif i > frames - sample_rate * 0.02:
                envelope = max(0.0, (frames - i) / (sample_rate * 0.02))
            value = int(amplitude * envelope * math.sin(2 * math.pi * base_freq * (i / sample_rate)))
            raw_data.append(struct.pack('<h', value))
        return b''.join(raw_data)

    def _pcm_to_wav(self, pcm_data: bytes, sample_rate: int | None = None) -> bytes:
        sr = sample_rate or self.settings.audio_sample_rate
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sr)
            wav_file.writeframes(pcm_data)
        return buffer.getvalue()
