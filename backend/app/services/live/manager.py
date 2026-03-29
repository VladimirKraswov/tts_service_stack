from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass, field

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.live.base import LiveEngine, LiveSynthesisRequest
from app.services.live.session_buffer import BufferedSegment, LiveTextBuffer
from app.services.preprocessor import TechnicalPreprocessor

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SessionContext:
    session_id: str
    websocket: WebSocket
    queue: asyncio.Queue[BufferedSegment] = field(default_factory=asyncio.Queue)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    buffer: LiveTextBuffer = field(default_factory=LiveTextBuffer)
    consumer_task: asyncio.Task[None] | None = None
    idle_task: asyncio.Task[None] | None = None


class LiveSessionManager:
    def __init__(self, live_engine: LiveEngine, preprocessor: TechnicalPreprocessor) -> None:
        self.live_engine = live_engine
        self.preprocessor = preprocessor
        self.sessions: dict[str, SessionContext] = {}

    async def startup(self) -> None:
        await self.live_engine.warmup()

    async def shutdown(self) -> None:
        for session_id in list(self.sessions.keys()):
            await self.disconnect(session_id)

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()

        ctx = SessionContext(session_id=session_id, websocket=websocket)
        ctx.consumer_task = asyncio.create_task(self._consumer_loop(ctx), name=f'live-consumer-{session_id}')
        self.sessions[session_id] = ctx

        await self._send_json(
            ctx,
            {
                'type': 'session.ready',
                'session_id': session_id,
                'mode': 'live',
            },
        )
        await self._send_buffer_state(ctx)

    async def disconnect(self, session_id: str) -> None:
        ctx = self.sessions.pop(session_id, None)
        if ctx is None:
            return

        if ctx.idle_task:
            ctx.idle_task.cancel()
        if ctx.consumer_task:
            ctx.consumer_task.cancel()

        tasks = [task for task in [ctx.idle_task, ctx.consumer_task] if task is not None]
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

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
            await self._enqueue_segments(ctx, segments)

        await self._send_buffer_state(ctx)

        if flush:
            await self._cancel_idle_task(ctx)
        else:
            self._restart_idle_task(ctx)

    async def flush(self, session_id: str) -> None:
        ctx = self._get_ctx(session_id)
        await self._cancel_idle_task(ctx)

        segments = ctx.buffer.flush()
        if segments:
            await self._enqueue_segments(ctx, segments)

        await self._send_json(ctx, {'type': 'buffer.flushed'})
        await self._send_buffer_state(ctx)

    async def clear_buffer(self, session_id: str) -> None:
        ctx = self._get_ctx(session_id)
        await self._cancel_idle_task(ctx)
        ctx.buffer.clear()
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

    async def _consumer_loop(self, ctx: SessionContext) -> None:
        while True:
            segment = await ctx.queue.get()
            started_at = time.perf_counter()
            first_audio_sent = False

            try:
                with SessionLocal() as db:
                    processed = self.preprocessor.process(
                        db=db,
                        text=segment.text,
                        dictionary_id=segment.dictionary_id,
                    )

                await self._send_json(
                    ctx,
                    {
                        'type': 'segment.started',
                        'segment_id': segment.segment_id,
                        'raw_text': segment.text,
                        'processed_text': processed.processed_text,
                    },
                )

                async for audio in self.live_engine.synthesize_segment(
                    LiveSynthesisRequest(
                        text=processed.processed_text,
                        voice_id=segment.voice_id,
                        lora_name=segment.lora_name,
                        language=segment.language,
                    )
                ):
                    if not first_audio_sent:
                        first_audio_sent = True
                        await self._send_json(
                            ctx,
                            {
                                'type': 'metrics.first_audio',
                                'segment_id': segment.segment_id,
                                'latency_ms': round((time.perf_counter() - started_at) * 1000, 2),
                            },
                        )

                    await self._send_json(
                        ctx,
                        {
                            'type': 'audio.chunk',
                            'segment_id': segment.segment_id,
                            'seq_no': audio.seq_no,
                            'text': audio.text,
                            'audio_b64': base64.b64encode(audio.pcm_bytes).decode('ascii'),
                            'sample_rate': audio.sample_rate,
                            'mime': audio.mime,
                            'is_last': audio.is_last,
                        },
                    )

                await self._send_json(
                    ctx,
                    {
                        'type': 'segment.done',
                        'segment_id': segment.segment_id,
                        'total_ms': round((time.perf_counter() - started_at) * 1000, 2),
                    },
                )

            except Exception as exc:
                logger.exception('Live segment synthesis failed session=%s', ctx.session_id)
                await self._send_json(
                    ctx,
                    {
                        'type': 'job.error',
                        'segment_id': segment.segment_id,
                        'error': str(exc),
                    },
                )
            finally:
                ctx.queue.task_done()

    async def _enqueue_segments(self, ctx: SessionContext, segments: list[BufferedSegment]) -> None:
        for segment in segments:
            await ctx.queue.put(segment)
            await self._send_json(
                ctx,
                {
                    'type': 'segment.accepted',
                    'segment_id': segment.segment_id,
                    'text': segment.text,
                    'queue_size': ctx.queue.qsize(),
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
        from app.core.config import get_settings

        settings = get_settings()
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
            await self._enqueue_segments(ctx, segments)
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

    async def _send_json(self, ctx: SessionContext, payload: dict) -> None:
        async with ctx.send_lock:
            await ctx.websocket.send_json(payload)

    def _get_ctx(self, session_id: str) -> SessionContext:
        ctx = self.sessions.get(session_id)
        if ctx is None:
            raise KeyError(f'Live session "{session_id}" is not connected')
        return ctx