from __future__ import annotations

from typing import AsyncIterator

from app.services.cosyvoice_runtime import get_cosyvoice_runtime
from app.services.live.base import LiveAudioChunk, LiveEngine, LiveSynthesisRequest


class CosyVoice2LiveEngine(LiveEngine):
    def __init__(self) -> None:
        self.runtime = get_cosyvoice_runtime()

    async def warmup(self) -> None:
        await self.runtime.warmup()

    async def synthesize_segment(self, request: LiveSynthesisRequest) -> AsyncIterator[LiveAudioChunk]:
        seq_no = 0
        last_chunk: bytes | None = None
        sample_rate = self.runtime.sample_rate

        async for pcm_bytes, sr in self.runtime.stream_zero_shot(
            text=request.text,
            voice_id=request.voice_id,
        ):
            sample_rate = sr
            if last_chunk is None:
                last_chunk = pcm_bytes
                continue

            yield LiveAudioChunk(
                pcm_bytes=last_chunk,
                seq_no=seq_no,
                text=request.text,
                sample_rate=sample_rate,
                is_last=False,
            )
            seq_no += 1
            last_chunk = pcm_bytes

        if last_chunk is not None:
            yield LiveAudioChunk(
                pcm_bytes=last_chunk,
                seq_no=seq_no,
                text=request.text,
                sample_rate=sample_rate,
                is_last=True,
            )