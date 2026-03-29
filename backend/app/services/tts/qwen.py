from __future__ import annotations

import asyncio
import inspect
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
    'auto': 'Auto',
}


def _normalize_name(value: str) -> str:
    return value.strip().lower().replace(' ', '_')


class QwenTTSEngine(TTSEngine):
    def __init__(self) -> None:
        self.settings = get_settings()
        self._model = None
        self._sample_rate = 24000
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max(1, self.settings.qwen_max_concurrent))
        self._is_warm = False
        self._supported_speakers: dict[str, str] = {}
        self._supported_languages: dict[str, str] = {}
        self._instruction_kwarg: str | None = None

    async def warmup(self) -> None:
        await self._ensure_model()
        self._is_warm = True

    async def synthesize_stream(self, request: SynthRequest) -> AsyncIterator[SynthChunk]:
        wav_bytes = await self._generate_wav_bytes(request)

        with wave.open(io.BytesIO(wav_bytes), 'rb') as wav_file:
            frames = wav_file.readframes(wav_file.getnframes())

        chunk_size = 3200  # ~66 ms for 24kHz S16 mono
        parts = [frames[i:i + chunk_size] for i in range(0, len(frames), chunk_size)]

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

            try:
                from qwen_tts import Qwen3TTSModel
            except Exception as exc:
                raise RuntimeError(
                    'Python package "qwen-tts" is not available in the API container.'
                ) from exc

            try:
                import torch
            except Exception as exc:
                raise RuntimeError('PyTorch is not available in the API container.') from exc

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

            try:
                self._model = Qwen3TTSModel.from_pretrained(
                    self.settings.qwen_model_name,
                    device_map=self.settings.qwen_device,
                    dtype=dtype,
                    attn_implementation=self.settings.qwen_attn_implementation,
                )
            except Exception as exc:
                raise RuntimeError(
                    f'Failed to load Qwen model "{self.settings.qwen_model_name}" on device '
                    f'"{self.settings.qwen_device}": {exc}'
                ) from exc

            try:
                speakers = list(self._model.get_supported_speakers())
                self._supported_speakers = {
                    _normalize_name(speaker): speaker for speaker in speakers
                }
                if speakers:
                    logger.info('Qwen speakers available: %s', ', '.join(speakers))
            except Exception:
                logger.warning('Could not fetch supported speakers from qwen-tts model')
                self._supported_speakers = {}

            try:
                languages = list(self._model.get_supported_languages())
                self._supported_languages = {
                    _normalize_name(language): language for language in languages
                }
                if languages:
                    logger.info('Qwen languages available: %s', ', '.join(languages))
            except Exception:
                logger.warning('Could not fetch supported languages from qwen-tts model')
                self._supported_languages = {}

            try:
                signature = inspect.signature(self._model.generate_custom_voice)
                params = signature.parameters
                if 'instruct' in params:
                    self._instruction_kwarg = 'instruct'
                elif 'instruction' in params:
                    self._instruction_kwarg = 'instruction'
                else:
                    self._instruction_kwarg = None
            except Exception:
                self._instruction_kwarg = 'instruct'

    def _resolve_speaker(self, voice_id: str | None) -> str:
        requested = VOICE_ALIASES.get(voice_id or '', voice_id or 'Ryan')
        if not self._supported_speakers:
            return requested

        normalized = _normalize_name(requested)
        matched = self._supported_speakers.get(normalized)
        if matched:
            return matched

        fallback = self._supported_speakers.get('ryan')
        if fallback:
            logger.warning(
                'Requested speaker "%s" is not supported by loaded model. Fallback to "%s".',
                requested,
                fallback,
            )
            return fallback

        return requested

    def _resolve_language(self, language: str | None) -> str:
        requested = LANGUAGE_ALIASES.get((language or 'ru').lower(), language or 'Russian')
        if not self._supported_languages:
            return requested

        normalized = _normalize_name(requested)
        matched = self._supported_languages.get(normalized)
        if matched:
            return matched

        auto = self._supported_languages.get('auto')
        if auto:
            logger.warning(
                'Requested language "%s" is not supported by loaded model. Fallback to "%s".',
                requested,
                auto,
            )
            return auto

        return requested

    def _generate_wav_bytes_sync(self, request: SynthRequest) -> bytes:
        if self._model is None:
            raise RuntimeError('Qwen model is not loaded.')

        speaker = self._resolve_speaker(request.voice_id)
        language = self._resolve_language(request.language)
        instruct_text = STYLE_ALIASES.get(request.lora_name or '', self.settings.qwen_preview_style)

        logger.info(
            'Qwen synth start speaker=%s language=%s chars=%s lora=%s',
            speaker,
            language,
            len(request.text),
            request.lora_name,
        )

        kwargs = {
            'text': request.text.strip(),
            'language': language,
            'speaker': speaker,
            'max_new_tokens': 2048,
        }

        if instruct_text and self._instruction_kwarg:
            kwargs[self._instruction_kwarg] = instruct_text.strip()

        try:
            wavs, sr = self._model.generate_custom_voice(**kwargs)
        except Exception as exc:
            logger.exception('Qwen generate_custom_voice failed')
            raise RuntimeError(
                f'Qwen synth failed for speaker="{speaker}", language="{language}": {exc}'
            ) from exc

        self._sample_rate = int(sr)

        if isinstance(wavs, np.ndarray):
            audio = wavs[0] if wavs.ndim > 1 else wavs
        elif isinstance(wavs, list):
            if not wavs:
                raise RuntimeError('Qwen returned empty wav list')
            audio = wavs[0]
        else:
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