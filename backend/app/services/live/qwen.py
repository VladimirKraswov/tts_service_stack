from __future__ import annotations

import io
import wave
from typing import AsyncIterator

from app.core.config import get_settings
from app.services.live.base import (
    BufferedLiveStreamSession,
    LiveAudioChunk,
    LiveEngine,
    LiveStreamSession,
    LiveSynthesisRequest,
)
from app.services.qwen_runtime import QwenSynthesisRequest, get_qwen_runtime


class QwenLiveEngine(LiveEngine):
    def __init__(self) -> None:
        self.settings = get_settings()
        self.runtime = get_qwen_runtime()

    async def warmup(self) -> None:
        await self.runtime.warmup()

    async def open_session(self) -> LiveStreamSession:
        await self.warmup()
        session = BufferedLiveStreamSession(self.synthesize_segment)
        await session.start()
        return session

    async def synthesize_segment(self, request: LiveSynthesisRequest) -> AsyncIterator[LiveAudioChunk]:
        wav_bytes, sample_rate = await self.runtime.generate_wav_bytes(
            QwenSynthesisRequest(
                text=request.text,
                voice_id=request.voice_id,
                lora_name=request.lora_name,
                language=request.language,
            )
        )

        with wave.open(io.BytesIO(wav_bytes), 'rb') as wav_file:
            pcm = wav_file.readframes(wav_file.getnframes())

        bytes_per_ms = max(2, int(sample_rate * 2 / 1000))
        chunk_size = max(1600, bytes_per_ms * self.settings.live_pcm_chunk_ms)
        parts = [pcm[i:i + chunk_size] for i in range(0, len(pcm), chunk_size)]

        for seq_no, part in enumerate(parts):
            yield LiveAudioChunk(
                pcm_bytes=part,
                seq_no=seq_no,
                text=request.text,
                sample_rate=sample_rate,
                is_last=seq_no == len(parts) - 1,
            )