from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket
from redis.asyncio import Redis
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.buffer import RedisFifoBuffer
from app.services.preprocessor import TechnicalPreprocessor
from app.services.tts.base import SynthRequest, TTSEngine

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass(slots=True)
class SessionContext:
    session_id: str
    websocket: WebSocket
    task: asyncio.Task[None]


class LiveSessionManager:
    def __init__(self, redis: Redis, tts_engine: TTSEngine, preprocessor: TechnicalPreprocessor) -> None:
        self.redis = redis
        self.buffer = RedisFifoBuffer(redis)
        self.tts_engine = tts_engine
        self.preprocessor = preprocessor
        self.sessions: dict[str, SessionContext] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        await self.tts_engine.warmup()
        task = asyncio.create_task(self._consume_loop(session_id, websocket), name=f'live-session-{session_id}')
        self.sessions[session_id] = SessionContext(session_id=session_id, websocket=websocket, task=task)
        await websocket.send_json({'type': 'session.ready', 'session_id': session_id})

    async def disconnect(self, session_id: str) -> None:
        ctx = self.sessions.pop(session_id, None)
        if ctx is None:
            return
        ctx.task.cancel()
        try:
            await ctx.task
        except asyncio.CancelledError:
            pass

    async def enqueue(self, session_id: str, payload: dict[str, Any]) -> None:
        await self.buffer.enqueue(session_id, payload)

    async def _consume_loop(self, session_id: str, websocket: WebSocket) -> None:
        while True:
            payload = await self.buffer.consume(session_id=session_id, timeout=1)
            if payload is None:
                await asyncio.sleep(0)
                continue

            started_at = time.perf_counter()
            job_id = payload.get('job_id') or f'{session_id}-{int(started_at * 1000)}'
            with SessionLocal() as db:
                processed = self.preprocessor.process(
                    db=db,
                    text=payload['text'],
                    dictionary_id=payload.get('dictionary_id'),
                )
            await websocket.send_json({
                'type': 'job.accepted',
                'job_id': job_id,
                'processed_text': processed.processed_text,
                'chunks': len(processed.chunks),
            })
            first_audio_sent = False
            try:
                for chunk_index, chunk_text in enumerate(processed.chunks):
                    await websocket.send_json({
                        'type': 'chunk.ready',
                        'job_id': job_id,
                        'chunk_index': chunk_index,
                        'text': chunk_text,
                    })
                    async for audio in self.tts_engine.synthesize_stream(
                        SynthRequest(
                            text=chunk_text,
                            voice_id=payload.get('voice_id'),
                            lora_name=payload.get('lora_name'),
                            language=payload.get('language', 'ru'),
                        )
                    ):
                        if not first_audio_sent:
                            first_audio_sent = True
                            await websocket.send_json({
                                'type': 'metrics.first_audio',
                                'job_id': job_id,
                                'latency_ms': round((time.perf_counter() - started_at) * 1000, 2),
                            })
                        await websocket.send_json({
                            'type': 'audio.chunk',
                            'job_id': job_id,
                            'chunk_index': chunk_index,
                            'seq_no': audio.seq_no,
                            'text': audio.text,
                            'audio_b64': base64.b64encode(audio.wav_bytes).decode('ascii'),
                                'sample_rate': settings.audio_sample_rate,
                            'mime': 'audio/l16',
                            'is_last': audio.is_last,
                        })
                await websocket.send_json({
                    'type': 'job.done',
                    'job_id': job_id,
                    'total_ms': round((time.perf_counter() - started_at) * 1000, 2),
                })
            except Exception as e:
                logger.exception("Synthesis failed for session %s", session_id)
                await websocket.send_json({
                    'type': 'job.error',
                    'job_id': job_id,
                    'error': str(e),
                })
