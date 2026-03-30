from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

import numpy as np

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PromptProfile:
    name: str
    wav_path: Path
    prompt_text: str


class CosyVoiceRuntime:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._model = None
        self._sample_rate = self.settings.audio_sample_rate
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max(1, self.settings.cosyvoice_max_concurrent))

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    async def warmup(self) -> None:
        await self._ensure_model()

    async def stream_zero_shot(
        self,
        *,
        text: str,
        voice_id: str | None = None,
    ) -> AsyncIterator[tuple[bytes, int]]:
        await self._ensure_model()
        profile = self._resolve_prompt_profile(voice_id)

        async with self._semaphore:
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[object] = asyncio.Queue()
            done = object()

            def worker() -> None:
                try:
                    assert self._model is not None
                    for item in self._model.inference_zero_shot(
                        text,
                        profile.prompt_text,
                        str(profile.wav_path),
                        stream=self.settings.cosyvoice_stream,
                        speed=self.settings.cosyvoice_speed,
                        text_frontend=self.settings.cosyvoice_text_frontend,
                    ):
                        pcm_bytes = self._speech_to_pcm16le(item['tts_speech'])
                        loop.call_soon_threadsafe(queue.put_nowait, pcm_bytes)
                except Exception as exc:  # pragma: no cover
                    logger.exception('CosyVoice stream worker failed')
                    loop.call_soon_threadsafe(queue.put_nowait, exc)
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, done)

            threading.Thread(
                target=worker,
                daemon=True,
                name='cosyvoice2-stream-worker',
            ).start()

            seq_count = 0
            while True:
                item = await queue.get()
                if item is done:
                    break
                if isinstance(item, Exception):
                    raise RuntimeError(f'CosyVoice inference failed: {item}') from item
                if not isinstance(item, (bytes, bytearray)):
                    raise RuntimeError(f'Unexpected CosyVoice stream payload type: {type(item)}')

                seq_count += 1
                yield bytes(item), self._sample_rate

    async def _ensure_model(self) -> None:
        if self._model is not None:
            return

        async with self._lock:
            if self._model is not None:
                return

            try:
                from cosyvoice.cli.cosyvoice import AutoModel
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(
                    'Failed to import CosyVoice. Check Docker image and PYTHONPATH.'
                ) from exc

            logger.info(
                'Loading CosyVoice model model_dir=%s fp16=%s load_jit=%s load_trt=%s load_vllm=%s',
                self.settings.cosyvoice_model_dir,
                self.settings.cosyvoice_fp16,
                self.settings.cosyvoice_load_jit,
                self.settings.cosyvoice_load_trt,
                self.settings.cosyvoice_load_vllm,
            )

            self._model = AutoModel(
                model_dir=str(self.settings.cosyvoice_model_dir),
                load_jit=self.settings.cosyvoice_load_jit,
                load_trt=self.settings.cosyvoice_load_trt,
                load_vllm=self.settings.cosyvoice_load_vllm,
                fp16=self.settings.cosyvoice_fp16,
            )
            self._sample_rate = int(getattr(self._model, 'sample_rate', self.settings.audio_sample_rate))

            logger.info('CosyVoice model loaded sample_rate=%s', self._sample_rate)

    def _resolve_prompt_profile(self, requested_name: str | None) -> PromptProfile:
        candidates: list[str] = []
        if requested_name:
            candidates.append(requested_name)
        default_name = self.settings.cosyvoice_default_prompt_name.strip()
        if default_name and default_name not in candidates:
            candidates.append(default_name)

        for name in candidates:
            profile = self._load_profile(name)
            if profile is not None:
                return profile

        raise RuntimeError(
            'CosyVoice prompt profile not found. '
            f'Create {self.settings.cosyvoice_prompt_dir / "default.wav"} and '
            f'{self.settings.cosyvoice_prompt_dir / "default.txt"} '
            'or pass a matching voice_id profile name.'
        )

    def _load_profile(self, name: str) -> PromptProfile | None:
        prompt_dir = self.settings.cosyvoice_prompt_dir

        direct_wav = prompt_dir / f'{name}.wav'
        direct_txt = prompt_dir / f'{name}.txt'
        if direct_wav.exists() and direct_txt.exists():
            return PromptProfile(
                name=name,
                wav_path=direct_wav,
                prompt_text=direct_txt.read_text(encoding='utf-8').strip(),
            )

        nested_dir = prompt_dir / name
        nested_wav = nested_dir / 'prompt.wav'
        nested_txt = nested_dir / 'prompt.txt'
        if nested_wav.exists() and nested_txt.exists():
            return PromptProfile(
                name=name,
                wav_path=nested_wav,
                prompt_text=nested_txt.read_text(encoding='utf-8').strip(),
            )

        return None

    def _speech_to_pcm16le(self, speech) -> bytes:
        if hasattr(speech, 'detach'):
            array = speech.detach().cpu().float().numpy()
        else:
            array = np.asarray(speech, dtype=np.float32)

        array = np.asarray(array, dtype=np.float32)
        array = np.squeeze(array)

        if array.ndim == 0:
            array = array.reshape(1)
        elif array.ndim > 1:
            array = array.reshape(-1)

        array = np.clip(array, -1.0, 1.0)
        pcm16 = (array * 32767.0).astype('<i2')
        return pcm16.tobytes()


_runtime: CosyVoiceRuntime | None = None


def get_cosyvoice_runtime() -> CosyVoiceRuntime:
    global _runtime
    if _runtime is None:
        _runtime = CosyVoiceRuntime()
    return _runtime