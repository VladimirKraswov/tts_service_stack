from __future__ import annotations

import asyncio
import inspect
import io
import logging
from dataclasses import dataclass

import numpy as np
import soundfile as sf

from app.core.config import get_settings

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


@dataclass(slots=True)
class QwenSynthesisRequest:
    text: str
    voice_id: str | None = None
    lora_name: str | None = None
    language: str = 'ru'


class QwenRuntime:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._model = None
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max(1, self.settings.qwen_max_concurrent))
        self._supported_speakers: dict[str, str] = {}
        self._supported_languages: dict[str, str] = {}
        self._instruction_kwarg: str | None = None
        self._active_attn_implementation: str | None = None

    async def warmup(self) -> None:
        await self._ensure_model()

    async def generate_wav_bytes(self, request: QwenSynthesisRequest) -> tuple[bytes, int]:
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
                import torch
            except Exception as exc:
                raise RuntimeError(f'Failed to import Qwen runtime dependencies: {exc}') from exc

            dtype_map = {
                'bfloat16': torch.bfloat16,
                'float16': torch.float16,
                'float32': torch.float32,
            }
            dtype = dtype_map.get(self.settings.qwen_dtype.lower(), torch.bfloat16)

            requested_attn = (self.settings.qwen_attn_implementation or 'sdpa').strip()

            logger.info(
                'Loading Qwen3-TTS model=%s device=%s dtype=%s attn=%s',
                self.settings.qwen_model_name,
                self.settings.qwen_device,
                self.settings.qwen_dtype,
                requested_attn,
            )

            self._model, self._active_attn_implementation = self._load_model_with_fallback(
                model_cls=Qwen3TTSModel,
                dtype=dtype,
                requested_attn=requested_attn,
            )

            logger.info(
                'Qwen3-TTS model loaded successfully with attn=%s',
                self._active_attn_implementation,
            )

            try:
                speakers = list(self._model.get_supported_speakers())
                self._supported_speakers = {_normalize_name(speaker): speaker for speaker in speakers}
                if speakers:
                    logger.info('Qwen speakers available: %s', ', '.join(speakers))
            except Exception:
                logger.warning('Could not fetch supported speakers from qwen-tts model')

            try:
                languages = list(self._model.get_supported_languages())
                self._supported_languages = {_normalize_name(language): language for language in languages}
                if languages:
                    logger.info('Qwen languages available: %s', ', '.join(languages))
            except Exception:
                logger.warning('Could not fetch supported languages from qwen-tts model')

            try:
                signature = inspect.signature(self._model.generate_custom_voice)
                params = signature.parameters
                if 'instruct' in params:
                    self._instruction_kwarg = 'instruct'
                elif 'instruction' in params:
                    self._instruction_kwarg = 'instruction'
            except Exception:
                self._instruction_kwarg = 'instruct'

    def _load_model_with_fallback(self, model_cls, dtype, requested_attn: str):
        attempts: list[str] = []
        for item in [requested_attn, 'sdpa', 'eager']:
            if item and item not in attempts:
                attempts.append(item)

        last_exc: Exception | None = None

        for attn_impl in attempts:
            try:
                logger.info('Trying Qwen load with attn=%s', attn_impl)
                model = model_cls.from_pretrained(
                    self.settings.qwen_model_name,
                    device_map=self.settings.qwen_device,
                    dtype=dtype,
                    attn_implementation=attn_impl,
                )
                return model, attn_impl
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    'Qwen load failed with attn=%s: %s',
                    attn_impl,
                    exc,
                )

        raise RuntimeError(
            f'Failed to load Qwen model "{self.settings.qwen_model_name}" '
            f'on device "{self.settings.qwen_device}" with attempts {attempts}: {last_exc}'
        ) from last_exc

    def _resolve_speaker(self, voice_id: str | None) -> str:
        requested = VOICE_ALIASES.get(voice_id or '', voice_id or 'Ryan')
        if not self._supported_speakers:
            return requested
        return self._supported_speakers.get(_normalize_name(requested), requested)

    def _resolve_language(self, language: str | None) -> str:
        requested = LANGUAGE_ALIASES.get((language or 'ru').lower(), language or 'Russian')
        if not self._supported_languages:
            return requested
        return self._supported_languages.get(_normalize_name(requested), requested)

    def _generate_wav_bytes_sync(self, request: QwenSynthesisRequest) -> tuple[bytes, int]:
        if self._model is None:
            raise RuntimeError('Qwen model is not loaded')

        speaker = self._resolve_speaker(request.voice_id)
        language = self._resolve_language(request.language)
        instruct_text = STYLE_ALIASES.get(request.lora_name or '', self.settings.qwen_preview_style)

        logger.info(
            'Qwen synth start speaker=%s language=%s chars=%s lora=%s attn=%s',
            speaker,
            language,
            len(request.text),
            request.lora_name,
            self._active_attn_implementation,
        )

        kwargs = {
            'text': request.text.strip(),
            'language': language,
            'speaker': speaker,
            'max_new_tokens': 2048,
        }

        if instruct_text and self._instruction_kwarg:
            kwargs[self._instruction_kwarg] = instruct_text.strip()

        wavs, sr = self._model.generate_custom_voice(**kwargs)

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
        return buffer.getvalue(), int(sr)


_runtime: QwenRuntime | None = None


def get_qwen_runtime() -> QwenRuntime:
    global _runtime
    if _runtime is None:
        _runtime = QwenRuntime()
    return _runtime