from __future__ import annotations

import asyncio
import io
import logging
import wave
from typing import AsyncIterator

import numpy as np
import soundfile as sf

from app.core.config import get_settings
from app.services.tts.base import SynthChunk, SynthRequest, TTSEngine

logger = logging.getLogger(__name__)


VOICE_ALIASES = {
    'system-neutral': 'Ryan',
    'system-warm': 'Serena',
    'qwen-ryan': 'Ryan',
    'qwen-aiden': 'Aiden',
    'qwen-vivian': 'Vivian',
    'qwen-serena': 'Serena',
    'qwen-uncle-fu': 'Uncle_Fu',
    'qwen-dylan': 'Dylan',
    'qwen-eric': 'Eric',
    'qwen-ono-anna': 'Ono_Anna',
    'qwen-sohee': 'Sohee',
}

STYLE_ALIASES = {
    'tech-lora-v1': 'Четко, спокойно, размеренно, как технический диктор. Английские термины произноси разборчиво.',
    'calm-lora-v1': 'Очень спокойно и мягко, без спешки.',
    'energetic-lora-v1': 'Живой и энергичный темп, но без крика.',
}

LANGUAGE_ALIASES = {
    'ru': 'Russian',
    'en': 'English',
    'zh': 'Chinese',
    'ja': 'Japanese',
    'ko': 'Korean',
    'de': 'German',
    'fr': 'French',
    'pt': 'Portuguese',
    'es': 'Spanish',
    'it': 'Italian',
}


class QwenTTSEngine(TTSEngine):
    def __init__(self) -> None:
        self.settings = get_settings()
        self._model = None
        self._sample_rate = 24000
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max(1, self.settings.qwen_max_concurrent))
        self._is_warm = False

    async def warmup(self) -> None:
        await self._ensure_model()
        self._is_warm = True

    async def synthesize_stream(self, request: SynthRequest) -> AsyncIterator[SynthChunk]:
        wav_bytes = await self._generate_wav_bytes(request)
        parts = self._split_wav_bytes(wav_bytes, target_ms=320)
        for seq_no, part in enumerate(parts):
            yield SynthChunk(
                wav_bytes=part,
                seq_no=seq_no,
                text=request.text,
                is_last=seq_no == len(parts) - 1,
            )

    async def synthesize_preview(self, request: SynthRequest) -> bytes:
        return await self._generate_wav_bytes(request)

    async def _generate_wav_bytes(self, request: SynthRequest) -> bytes:
        await self._ensure_model()
        async with self._semaphore:
            return await asyncio.to_thread(self._generate_wav_bytes_sync, request)

    async def _ensure_model(self) -> None:
        if self._model is not None:
            return
        async with self._lock:
            if self._model is not None:
                return

            from qwen_tts import Qwen3TTSModel
            import torch

            dtype_map = {
                'bfloat16': torch.bfloat16,
                'float16': torch.float16,
                'float32': torch.float32,
            }
            dtype = dtype_map.get(self.settings.qwen_dtype.lower(), torch.bfloat16)

            logger.info(
                'Loading Qwen3-TTS model=%s device=%s dtype=%s attn=%s',
                self.settings.qwen_model_name,
                self.settings.qwen_device,
                self.settings.qwen_dtype,
                self.settings.qwen_attn_implementation,
            )

            self._model = Qwen3TTSModel.from_pretrained(
                self.settings.qwen_model_name,
                device_map=self.settings.qwen_device,
                dtype=dtype,
                attn_implementation=self.settings.qwen_attn_implementation,
            )

            supported = []
            try:
                supported = list(self._model.get_supported_speakers())
            except Exception:
                logger.warning('Could not fetch supported speakers from qwen-tts model')
            if supported:
                logger.info('Qwen speakers available: %s', ', '.join(supported))

    def _generate_wav_bytes_sync(self, request: SynthRequest) -> bytes:
        speaker = VOICE_ALIASES.get(request.voice_id or '', request.voice_id or 'Ryan')
        speaker = speaker.lower().replace(' ', '_')

        language = LANGUAGE_ALIASES.get(
            (request.language or 'ru').lower(),
            request.language or 'Russian',
        )

        instruct = STYLE_ALIASES.get(request.lora_name or '', self.settings.qwen_preview_style)

        logger.info(
            'Qwen synth start speaker=%s language=%s chars=%s lora=%s',
            speaker,
            language,
            len(request.text),
            request.lora_name,
        )

        try:
            wavs, sr = self._model.generate_custom_voice(
                text=request.text.strip(),
                language=language,
                speaker=speaker,
                instruct=instruct.strip() if instruct else None,
                non_streaming_mode=True,
                max_new_tokens=2048,
            )
        except Exception:
            logger.exception('Qwen generate_custom_voice failed')
            raise

        self._sample_rate = int(sr)

        if isinstance(wavs, np.ndarray):
            audio = wavs[0] if wavs.ndim > 1 else wavs
        elif isinstance(wavs, list):
            if not wavs:
                raise RuntimeError('Qwen returned empty wav list')
            audio = wavs[0]
        else:
            logger.error('Unexpected Qwen output type: %s', type(wavs))
            raise TypeError(f'Unexpected wavs type: {type(wavs)}')

        if isinstance(audio, list):
            audio = np.asarray(audio, dtype=np.float32)
        elif not isinstance(audio, np.ndarray):
            audio = np.asarray(audio, dtype=np.float32)

        audio = audio.astype(np.float32, copy=False)

        if audio.ndim > 1:
            audio = np.mean(audio, axis=-1).astype(np.float32)

        logger.info('Qwen synth done sr=%s samples=%s', sr, audio.shape[0] if audio.ndim else 0)

        buffer = io.BytesIO()
        sf.write(buffer, audio, sr, format='WAV', subtype='PCM_16')
        return buffer.getvalue()

    def _split_wav_bytes(self, wav_bytes: bytes, target_ms: int = 320) -> list[bytes]:
        with wave.open(io.BytesIO(wav_bytes), 'rb') as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())

        bytes_per_frame = channels * sample_width
        frames_per_part = max(1, int(sample_rate * (target_ms / 1000.0)))
        chunk_size = frames_per_part * bytes_per_frame

        parts: list[bytes] = []
        for start in range(0, len(frames), chunk_size):
            raw = frames[start:start + chunk_size]
            out = io.BytesIO()
            with wave.open(out, 'wb') as wav_out:
                wav_out.setnchannels(channels)
                wav_out.setsampwidth(sample_width)
                wav_out.setframerate(sample_rate)
                wav_out.writeframes(raw)
            parts.append(out.getvalue())
        return parts or [wav_bytes]
