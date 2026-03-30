from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import websockets

from app.core.config import get_settings
from app.services.live.base import LiveAudioChunk, LiveEngine, LiveStreamSession, LiveSynthesisRequest

logger = logging.getLogger(__name__)
settings = get_settings()

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
    'tech-lora-v1': 'Speak clearly, calmly, and precisely like a technical narrator.',
    'calm-lora-v1': 'Speak very calmly and softly.',
    'energetic-lora-v1': 'Speak energetically, but without shouting.',
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


@dataclass(slots=True)
class _AudioDeltaEvent:
    pcm_bytes: bytes


@dataclass(slots=True)
class _AudioDoneEvent:
    pass


@dataclass(slots=True)
class _ErrorEvent:
    message: str


@dataclass(slots=True)
class _ClosedEvent:
    pass


class QwenRealtimeSession(LiveStreamSession):
    def __init__(self) -> None:
        self._ws: Any | None = None
        self._recv_task: asyncio.Task[None] | None = None
        self._events: asyncio.Queue[_AudioDeltaEvent | _AudioDoneEvent | _ErrorEvent | _ClosedEvent] = asyncio.Queue()
        self._send_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        self._closed = False
        self._current_signature: tuple[str, str, str, str] | None = None

        self._session_created = asyncio.Event()
        self._session_updated = asyncio.Event()
        self._session_finished = asyncio.Event()

    async def start(self) -> None:
        if self._ws is not None:
            return

        if not settings.qwen_realtime_ws_url:
            raise RuntimeError('QWEN_REALTIME_WS_URL is not configured')
        if not settings.qwen_realtime_api_key:
            raise RuntimeError('QWEN_REALTIME_API_KEY is not configured')

        url = self._build_ws_url(
            base_url=settings.qwen_realtime_ws_url,
            model=settings.qwen_realtime_model,
        )

        self._ws = await websockets.connect(
            url,
            additional_headers={
                'Authorization': f'Bearer {settings.qwen_realtime_api_key}',
            },
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        )
        self._recv_task = asyncio.create_task(self._recv_loop(), name='qwen-realtime-recv')

        await asyncio.wait_for(self._session_created.wait(), timeout=10)

    async def send_text(self, text: str, request: LiveSynthesisRequest) -> None:
        if self._closed:
            raise RuntimeError('Realtime session is closed')
        if not text.strip():
            return

        await self.start()

        async with self._state_lock:
            signature = self._signature(request)
            if signature != self._current_signature:
                await self._update_session(request)
                self._current_signature = signature

            await self._send_json({
                'type': 'input_text_buffer.append',
                'text': text,
            })

    async def flush(self) -> None:
        if self._closed or self._ws is None:
            return

        await self._send_json({
            'type': 'input_text_buffer.commit',
        })

    async def clear(self) -> None:
        if self._closed or self._ws is None:
            return

        await self._send_json({
            'type': 'input_text_buffer.clear',
        })

    async def audio_chunks(self) -> AsyncIterator[LiveAudioChunk]:
        seq_no = 0

        while True:
            event = await self._events.get()

            if isinstance(event, _AudioDeltaEvent):
                yield LiveAudioChunk(
                    pcm_bytes=event.pcm_bytes,
                    seq_no=seq_no,
                    text='',
                    sample_rate=settings.qwen_realtime_sample_rate,
                    mime='audio/l16',
                    is_last=False,
                )
                seq_no += 1
                continue

            if isinstance(event, _AudioDoneEvent):
                # frontend ignores empty audio_b64, but this marks boundary for consumers
                yield LiveAudioChunk(
                    pcm_bytes=b'',
                    seq_no=seq_no,
                    text='',
                    sample_rate=settings.qwen_realtime_sample_rate,
                    mime='audio/l16',
                    is_last=True,
                )
                seq_no = 0
                continue

            if isinstance(event, _ErrorEvent):
                raise RuntimeError(event.message)

            if isinstance(event, _ClosedEvent):
                return

    async def close(self) -> None:
        if self._closed:
            return

        self._closed = True

        try:
            if self._ws is not None:
                try:
                    await self._send_json({'type': 'session.finish'})
                    try:
                        await asyncio.wait_for(self._session_finished.wait(), timeout=3)
                    except asyncio.TimeoutError:
                        pass
                except Exception:
                    pass

                try:
                    await self._ws.close()
                except Exception:
                    pass
        finally:
            if self._recv_task is not None:
                self._recv_task.cancel()
                try:
                    await self._recv_task
                except asyncio.CancelledError:
                    pass
            await self._events.put(_ClosedEvent())

    def _signature(self, request: LiveSynthesisRequest) -> tuple[str, str, str, str]:
        voice = VOICE_ALIASES.get(request.voice_id or '', request.voice_id or 'Ryan')
        language = LANGUAGE_ALIASES.get((request.language or 'ru').lower(), request.language or 'Russian')

        instructions = ''
        model_name = (settings.qwen_realtime_model or '').lower()
        if 'instruct' in model_name:
            instructions = STYLE_ALIASES.get(request.lora_name or '', '')

        return (
            settings.qwen_realtime_model,
            voice,
            language,
            instructions,
        )

    async def _update_session(self, request: LiveSynthesisRequest) -> None:
        voice = VOICE_ALIASES.get(request.voice_id or '', request.voice_id or 'Ryan')
        language = LANGUAGE_ALIASES.get((request.language or 'ru').lower(), request.language or 'Russian')

        session_payload: dict[str, Any] = {
            'mode': settings.qwen_realtime_mode,
            'voice': voice,
            'language_type': language,
            'response_format': settings.qwen_realtime_format,
            'sample_rate': settings.qwen_realtime_sample_rate,
        }

        model_name = (settings.qwen_realtime_model or '').lower()
        if 'instruct' in model_name:
            instructions = STYLE_ALIASES.get(request.lora_name or '', '')
            if instructions:
                session_payload['instructions'] = instructions
                session_payload['optimize_instructions'] = True
        elif request.lora_name:
            logger.info(
                'Ignoring live style "%s" because realtime model "%s" does not support instruction control',
                request.lora_name,
                settings.qwen_realtime_model,
            )

        self._session_updated.clear()
        await self._send_json({
            'type': 'session.update',
            'session': session_payload,
        })
        await asyncio.wait_for(self._session_updated.wait(), timeout=10)

    async def _send_json(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            raise RuntimeError('Realtime websocket is not connected')

        payload = {
            **payload,
            'event_id': payload.get('event_id') or f'event_{int(asyncio.get_running_loop().time() * 1000)}',
        }

        async with self._send_lock:
            await self._ws.send(json.dumps(payload, ensure_ascii=False))

    async def _recv_loop(self) -> None:
        assert self._ws is not None

        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    # The documented TTS realtime flow uses JSON events with base64 audio deltas.
                    continue

                data = json.loads(raw)
                event_type = data.get('type')

                if event_type == 'session.created':
                    self._session_created.set()
                    logger.info('Qwen realtime session.created')
                    continue

                if event_type == 'session.updated':
                    self._session_updated.set()
                    logger.info('Qwen realtime session.updated')
                    continue

                if event_type == 'session.finished':
                    self._session_finished.set()
                    logger.info('Qwen realtime session.finished')
                    continue

                if event_type == 'input_text_buffer.committed':
                    logger.debug('Qwen realtime input_text_buffer.committed')
                    continue

                if event_type == 'input_text_buffer.cleared':
                    logger.debug('Qwen realtime input_text_buffer.cleared')
                    continue

                if event_type == 'response.created':
                    logger.debug('Qwen realtime response.created')
                    continue

                if event_type == 'response.output_item.added':
                    logger.debug('Qwen realtime response.output_item.added')
                    continue

                if event_type == 'response.content_part.added':
                    logger.debug('Qwen realtime response.content_part.added')
                    continue

                if event_type == 'response.audio.delta':
                    delta_b64 = data.get('delta')
                    if isinstance(delta_b64, str) and delta_b64:
                        pcm = base64.b64decode(delta_b64)
                        await self._events.put(_AudioDeltaEvent(pcm_bytes=pcm))
                    continue

                if event_type == 'response.audio.done':
                    await self._events.put(_AudioDoneEvent())
                    continue

                if event_type == 'response.done':
                    logger.debug('Qwen realtime response.done')
                    continue

                if event_type in {'error', 'response.error'}:
                    await self._events.put(_ErrorEvent(self._extract_error_message(data)))
                    continue

                logger.debug('Qwen realtime event=%s payload=%s', event_type, data)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception('Qwen realtime recv loop failed')
            await self._events.put(_ErrorEvent(str(exc)))

    @staticmethod
    def _extract_error_message(payload: dict[str, Any]) -> str:
        error = payload.get('error')
        if isinstance(error, dict):
            message = error.get('message') or error.get('code')
            if message:
                return str(message)
        if isinstance(error, str):
            return error
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _build_ws_url(base_url: str, model: str | None) -> str:
        parsed = urlparse(base_url)
        query = parse_qs(parsed.query, keep_blank_values=True)

        if model:
            query['model'] = [model]

        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


class QwenRealtimeLiveEngine(LiveEngine):
    async def warmup(self) -> None:
        # Cloud realtime backend has no local model warmup.
        return None

    async def open_session(self) -> LiveStreamSession:
        session = QwenRealtimeSession()
        await session.start()
        return session

    async def synthesize_segment(self, request: LiveSynthesisRequest) -> AsyncIterator[LiveAudioChunk]:
        """
        Compatibility path for single-request use.
        The main application uses open_session() and keeps the session persistent.
        """
        session = QwenRealtimeSession()
        await session.start()
        try:
            await session.send_text(request.text, request)
            await session.flush()
            async for chunk in session.audio_chunks():
                yield chunk
        finally:
            await session.close()