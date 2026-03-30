from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
import logging
from pathlib import Path
import sys
from typing import AsyncIterator

import numpy as np

from app.core.config import get_settings
from app.services.live.base import LiveAudioChunk, LiveEngine, LiveSynthesisRequest

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass(slots=True)
class PromptBundle:
    speaker_id: str
    prompt_wav: Path
    prompt_text: str


class CosyVoice2LiveEngine(LiveEngine):
    def __init__(self) -> None:
        self.settings = get_settings()
        self._model = None
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(1)
        self._cached_speakers: set[str] = set()

    async def warmup(self) -> None:
        await self._ensure_model()
        try:
            await asyncio.to_thread(self._warmup_default_speaker_sync)
        except Exception:
            logger.exception('CosyVoice2 warmup speaker cache failed')

    async def synthesize_segment(self, request: LiveSynthesisRequest) -> AsyncIterator[LiveAudioChunk]:
        await self._ensure_model()

        async with self._semaphore:
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[LiveAudioChunk | Exception | object] = asyncio.Queue()
            sentinel = object()

            def worker() -> None:
                pending_chunk: LiveAudioChunk | None = None
                try:
                    for chunk in self._run_inference_sync(request):
                        if pending_chunk is not None:
                            asyncio.run_coroutine_threadsafe(queue.put(pending_chunk), loop).result()
                        pending_chunk = chunk

                    if pending_chunk is not None:
                        pending_chunk.is_last = True
                        asyncio.run_coroutine_threadsafe(queue.put(pending_chunk), loop).result()
                except Exception as exc:  # pragma: no cover
                    asyncio.run_coroutine_threadsafe(queue.put(exc), loop).result()
                finally:
                    asyncio.run_coroutine_threadsafe(queue.put(sentinel), loop).result()

            producer_task = asyncio.create_task(asyncio.to_thread(worker), name='cosyvoice2-producer')

            try:
                while True:
                    item = await queue.get()
                    if item is sentinel:
                        break
                    if isinstance(item, Exception):
                        raise item
                    yield item
            finally:
                producer_task.cancel()
                with suppress(Exception):
                    await producer_task

    async def _ensure_model(self) -> None:
        if self._model is not None:
            return

        async with self._lock:
            if self._model is not None:
                return

            self._prepare_import_paths()

            try:
                from cosyvoice.cli.cosyvoice import AutoModel
            except Exception as exc:
                raise RuntimeError(
                    'CosyVoice is not installed in the API container. '
                    'Install the official CosyVoice repo and expose COSYVOICE_ROOT/PYTHONPATH.'
                ) from exc

            logger.info(
                'Loading CosyVoice2 model_dir=%s fp16=%s load_jit=%s load_trt=%s load_vllm=%s',
                self.settings.cosyvoice_model_dir,
                self.settings.cosyvoice_fp16,
                self.settings.cosyvoice_load_jit,
                self.settings.cosyvoice_load_trt,
                self.settings.cosyvoice_load_vllm,
            )

            self._model = await asyncio.to_thread(
                AutoModel,
                model_dir=self.settings.cosyvoice_model_dir,
                load_jit=self.settings.cosyvoice_load_jit,
                load_trt=self.settings.cosyvoice_load_trt,
                load_vllm=self.settings.cosyvoice_load_vllm,
                fp16=self.settings.cosyvoice_fp16,
            )

            logger.info(
                'CosyVoice2 model ready sample_rate=%s',
                getattr(self._model, 'sample_rate', 'unknown'),
            )

    def _prepare_import_paths(self) -> None:
        if self.settings.cosyvoice_root is None:
            return

        root = str(self.settings.cosyvoice_root)
        matcha = str(self.settings.cosyvoice_root / 'third_party' / 'Matcha-TTS')

        if root not in sys.path:
            sys.path.append(root)
        if matcha not in sys.path:
            sys.path.append(matcha)

    def _warmup_default_speaker_sync(self) -> None:
        if self._model is None:
            return

        try:
            bundle = self._resolve_prompt_bundle(None)
        except Exception:
            logger.warning('CosyVoice2 default prompt is not configured; live voice fallback will be unavailable')
            return

        self._ensure_speaker_cached_sync(bundle)

    def _run_inference_sync(self, request: LiveSynthesisRequest) -> list[LiveAudioChunk]:
        if self._model is None:
            raise RuntimeError('CosyVoice2 model is not loaded')

        bundle = self._resolve_prompt_bundle(request.voice_id)
        self._ensure_speaker_cached_sync(bundle)

        logger.info(
            'CosyVoice2 synth start speaker_id=%s chars=%s stream=%s speed=%s',
            bundle.speaker_id,
            len(request.text),
            self.settings.cosyvoice_stream,
            self.settings.cosyvoice_speed,
        )

        generator = self._model.inference_zero_shot(
            request.text,
            '',
            '',
            zero_shot_spk_id=bundle.speaker_id,
            stream=self.settings.cosyvoice_stream,
            speed=self.settings.cosyvoice_speed,
            text_frontend=self.settings.cosyvoice_text_frontend,
        )

        sample_rate = int(getattr(self._model, 'sample_rate', self.settings.audio_sample_rate))
        chunks: list[LiveAudioChunk] = []

        for seq_no, model_output in enumerate(generator):
            speech = model_output['tts_speech']
            pcm_bytes = self._tensor_to_pcm_bytes(speech)

            chunks.append(
                LiveAudioChunk(
                    pcm_bytes=pcm_bytes,
                    seq_no=seq_no,
                    text=request.text,
                    sample_rate=sample_rate,
                    mime='audio/l16',
                    is_last=False,
                )
            )

        logger.info('CosyVoice2 synth done speaker_id=%s chunks=%s', bundle.speaker_id, len(chunks))
        return chunks

    def _tensor_to_pcm_bytes(self, speech) -> bytes:
        audio = speech.detach().float().cpu().squeeze().numpy()
        audio = np.clip(audio, -1.0, 1.0)
        return (audio * 32767.0).astype('<i2').tobytes()

    def _ensure_speaker_cached_sync(self, bundle: PromptBundle) -> None:
        if bundle.speaker_id in self._cached_speakers:
            return

        if self._model is None:
            raise RuntimeError('CosyVoice2 model is not loaded')

        if not hasattr(self._model, 'add_zero_shot_spk'):
            raise RuntimeError('Loaded CosyVoice model does not support add_zero_shot_spk')

        logger.info('CosyVoice2 cache speaker speaker_id=%s wav=%s', bundle.speaker_id, bundle.prompt_wav)

        ok = self._model.add_zero_shot_spk(
            bundle.prompt_text,
            str(bundle.prompt_wav),
            bundle.speaker_id,
        )
        if ok is not True:
            raise RuntimeError(f'Failed to cache CosyVoice speaker "{bundle.speaker_id}"')

        self._cached_speakers.add(bundle.speaker_id)

    def _resolve_prompt_bundle(self, voice_id: str | None) -> PromptBundle:
        prompt_dir = self.settings.cosyvoice_prompt_dir_resolved
        speaker_id = (voice_id or 'default').strip() or 'default'

        per_voice_audio = self._find_audio_file(prompt_dir, speaker_id)
        per_voice_text = prompt_dir / f'{speaker_id}.txt'
        if per_voice_audio is not None and per_voice_text.exists():
            text = per_voice_text.read_text(encoding='utf-8').strip()
            if not text:
                raise RuntimeError(f'Empty CosyVoice prompt text file: {per_voice_text}')
            return PromptBundle(
                speaker_id=speaker_id,
                prompt_wav=per_voice_audio,
                prompt_text=text,
            )

        default_wav = self.settings.cosyvoice_default_prompt_wav
        default_text = (self.settings.cosyvoice_default_prompt_text or '').strip()

        if default_wav is None:
            fallback_audio = self._find_audio_file(prompt_dir, 'default')
            if fallback_audio is not None:
                default_wav = fallback_audio

        if not default_text:
            fallback_text_file = prompt_dir / 'default.txt'
            if fallback_text_file.exists():
                default_text = fallback_text_file.read_text(encoding='utf-8').strip()

        if default_wav is None or not Path(default_wav).exists():
            raise RuntimeError(
                'CosyVoice live prompt wav is not configured. '
                'Set COSYVOICE_DEFAULT_PROMPT_WAV or place default.wav in the prompt dir.'
            )
        if not default_text:
            raise RuntimeError(
                'CosyVoice live prompt text is not configured. '
                'Set COSYVOICE_DEFAULT_PROMPT_TEXT or place default.txt in the prompt dir.'
            )

        return PromptBundle(
            speaker_id='default',
            prompt_wav=Path(default_wav),
            prompt_text=default_text,
        )

    def _find_audio_file(self, folder: Path, stem: str) -> Path | None:
        for ext in ('.wav', '.flac', '.mp3', '.m4a'):
            candidate = folder / f'{stem}{ext}'
            if candidate.exists():
                return candidate
        return None