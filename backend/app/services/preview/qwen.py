from __future__ import annotations

from app.services.preview.base import PreviewEngine, PreviewRequest
from app.services.qwen_runtime import QwenSynthesisRequest, get_qwen_runtime


class QwenPreviewEngine(PreviewEngine):
    def __init__(self) -> None:
        self.runtime = get_qwen_runtime()

    async def warmup(self) -> None:
        await self.runtime.warmup()

    async def synthesize(self, request: PreviewRequest) -> bytes:
        wav_bytes, _ = await self.runtime.generate_wav_bytes(
            QwenSynthesisRequest(
                text=request.text,
                voice_id=request.voice_id,
                lora_name=request.lora_name,
                language=request.language,
            )
        )
        return wav_bytes