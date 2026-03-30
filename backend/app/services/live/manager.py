from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field

from fastapi import WebSocket

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.live.base import LiveAudioChunk, LiveEngine, LiveStreamSession, LiveSynthesisRequest
from app.services.live.preprocessor import LiveTextPreprocessor
from app.services.live.session_buffer import BufferedSegment, LiveTextBuffer

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass(slots=True)
class SessionContext:
    session_id: str
    websocket: WebSocket
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    buffer: LiveTextBuffer = field(default_factory=LiveTextBuffer)
    stream_session: LiveStreamSession | None = None
    audio_task: asyncio.Task[None] | None = None
    idle_task: asyncio.Task[None] | None = None


class LiveSessionManager:
    def __init__(self, live_engine: LiveEngine, preprocessor: LiveTextPreprocessor) -> None:
        self.live_engine = live_engine
        self.preprocessor = preprocessor
        self.sessions: dict[str, SessionContext] = {}

    async def startup(self) -> None:
        await self.live_engine.warmup()

    async def shutdown(self) -> None:
        for session_id in list(self.sessions.keys()):
            await self.disconnect(session_id)

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        ctx = SessionContext(session_id=session_id, websocket=websocket)

        try:
            ctx.stream_session = await self.live_engine.open_session()
            ctx.audio_task = asyncio.create_task(self._audio_loop(ctx), name=f'live-audio-{session_id}')
            self.sessions[session_id] = ctx

            await self._send_json(
                ctx,
                {
                    'type': 'session.ready',
                    'session_id': session_id,
                    'mode': 'live',
                    'streaming': True,
                },
            )
            await self._send_buffer_state(ctx)
        except Exception:
            if ctx.audio_task is not None:
                ctx.audio_task.cancel()
                try:
                    await ctx.audio_task
                except asyncio.CancelledError:
                    pass
            if ctx.stream_session is not None:
                try:
                    await ctx.stream_session.close()
                except Exception:
                    logger.exception('Failed to close stream session after connect failure')
            raise

    async def disconnect(self, session_id: str) -> None:
        ctx = self.sessions.pop(session_id, None)
        if ctx is None:
            return

        for task in [ctx.idle_task, ctx.audio_task]:
            if task is not None:
                task.cancel()

        for task in [ctx.idle_task, ctx.audio_task]:
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if ctx.stream_session is not None:
            try:
                await ctx.stream_session.close()
            except Exception:
                logger.exception('Failed to close live stream session session=%s', session_id)

    async def append_text(
        self,
        session_id: str,
        text: str,
        *,
        dictionary_id: int | None,
        voice_id: str | None,
        lora_name: str | None,
        language: str | None,
        flush: bool = False,
    ) -> None:
        ctx = self._get_ctx(session_id)

        segments = ctx.buffer.append(
            text,
            dictionary_id=dictionary_id,
            voice_id=voice_id,
            lora_name=lora_name,
            language=language,
            flush=flush,
        )

        if segments:
            await self._stream_segments(ctx, segments)

        await self._send_buffer_state(ctx)

        if flush:
            await self._cancel_idle_task(ctx)
            if ctx.stream_session is not None:
                await ctx.stream_session.flush()
                await self._send_json(ctx, {'type': 'buffer.flushed', 'reason': 'explicit'})
        else:
            self._restart_idle_task(ctx)

    async def flush(self, session_id: str) -> None:
        ctx = self._get_ctx(session_id)
        await self._cancel_idle_task(ctx)

        segments = ctx.buffer.flush()
        if segments:
            await self._stream_segments(ctx, segments)

        if ctx.stream_session is not None:
            await ctx.stream_session.flush()

        await self._send_json(ctx, {'type': 'buffer.flushed'})
        await self._send_buffer_state(ctx)

    async def clear_buffer(self, session_id: str) -> None:
        ctx = self._get_ctx(session_id)
        await self._cancel_idle_task(ctx)

        ctx.buffer.clear()
        if ctx.stream_session is not None:
            await ctx.stream_session.clear()

        await self._send_json(ctx, {'type': 'buffer.cleared'})
        await self._send_buffer_state(ctx)

    async def enqueue_once(
        self,
        session_id: str,
        text: str,
        *,
        dictionary_id: int | None,
        voice_id: str | None,
        lora_name: str | None,
        language: str | None,
    ) -> None:
        await self.append_text(
            session_id,
            text,
            dictionary_id=dictionary_id,
            voice_id=voice_id,
            lora_name=lora_name,
            language=language,
            flush=True,
        )

    async def _audio_loop(self, ctx: SessionContext) -> None:
        if ctx.stream_session is None:
            return

        try:
            async for audio in ctx.stream_session.audio_chunks():
                await self._send_audio_chunk(ctx, audio)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception('Live audio loop failed session=%s', ctx.session_id)
            await self._send_json(
                ctx,
                {
                    'type': 'job.error',
                    'error': str(exc),
                },
            )

    async def _stream_segments(self, ctx: SessionContext, segments: list[BufferedSegment]) -> None:
        if ctx.stream_session is None:
            raise RuntimeError('Live stream session is not initialized')

        for segment in segments:
            with SessionLocal() as db:
                processed_text = self.preprocessor.process(
                    db=db,
                    text=segment.text,
                    dictionary_id=segment.dictionary_id,
                )

            request = LiveSynthesisRequest(
                text=processed_text,
                voice_id=segment.voice_id,
                lora_name=segment.lora_name,
                language=segment.language,
            )

            await ctx.stream_session.send_text(processed_text, request)

            await self._send_json(
                ctx,
                {
                    'type': 'segment.accepted',
                    'segment_id': segment.segment_id,
                    'raw_text': segment.text,
                    'processed_text': processed_text,
                },
            )

    def _restart_idle_task(self, ctx: SessionContext) -> None:
        if ctx.idle_task:
            ctx.idle_task.cancel()
        ctx.idle_task = asyncio.create_task(self._idle_flush_later(ctx.session_id), name=f'idle-flush-{ctx.session_id}')

    async def _cancel_idle_task(self, ctx: SessionContext) -> None:
        if ctx.idle_task is None:
            return
        ctx.idle_task.cancel()
        try:
            await ctx.idle_task
        except asyncio.CancelledError:
            pass
        finally:
            ctx.idle_task = None

    async def _idle_flush_later(self, session_id: str) -> None:
        try:
            await asyncio.sleep(settings.live_buffer_idle_ms / 1000.0)
        except asyncio.CancelledError:
            raise

        ctx = self.sessions.get(session_id)
        if ctx is None:
            return

        if not ctx.buffer.idle_flush_due():
            return

        segments = ctx.buffer.flush()
        if segments:
            await self._stream_segments(ctx, segments)

        if ctx.stream_session is not None:
            await ctx.stream_session.flush()

        await self._send_json(ctx, {'type': 'buffer.flushed', 'reason': 'idle'})
        await self._send_buffer_state(ctx)

    async def _send_buffer_state(self, ctx: SessionContext) -> None:
        snapshot = ctx.buffer.snapshot()
        await self._send_json(
            ctx,
            {
                'type': 'buffer.updated',
                **snapshot,
            },
        )

    async def _send_audio_chunk(self, ctx: SessionContext, audio: LiveAudioChunk) -> None:
        await self._send_json(
            ctx,
            {
                'type': 'audio.chunk',
                'segment_id': 'realtime',
                'seq_no': audio.seq_no,
                'text': audio.text,
                'audio_b64': base64.b64encode(audio.pcm_bytes).decode('ascii'),
                'sample_rate': audio.sample_rate,
                'mime': audio.mime,
                'is_last': audio.is_last,
            },
        )

    async def _send_json(self, ctx: SessionContext, payload: dict) -> None:
        async with ctx.send_lock:
            await ctx.websocket.send_json(payload)

    def _get_ctx(self, session_id: str) -> SessionContext:
        ctx = self.sessions.get(session_id)
        if ctx is None:
            raise KeyError(f'Live session "{session_id}" is not connected')
        return ctx