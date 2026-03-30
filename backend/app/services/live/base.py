from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Awaitable, Callable


@dataclass(slots=True)
class LiveSynthesisRequest:
    text: str
    voice_id: str | None = None
    lora_name: str | None = None
    language: str = 'ru'


@dataclass(slots=True)
class LiveAudioChunk:
    pcm_bytes: bytes
    seq_no: int
    text: str
    sample_rate: int
    mime: str = 'audio/l16'
    is_last: bool = False


class LiveStreamSession(ABC):
    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send_text(self, text: str, request: LiveSynthesisRequest) -> None:
        raise NotImplementedError

    @abstractmethod
    async def flush(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def clear(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def audio_chunks(self) -> AsyncIterator[LiveAudioChunk]:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError


@dataclass(slots=True)
class _ChunkEvent:
    chunk: LiveAudioChunk


@dataclass(slots=True)
class _ErrorEvent:
    message: str


@dataclass(slots=True)
class _ClosedEvent:
    pass


class BufferedLiveStreamSession(LiveStreamSession):
    """
    Generic adapter for non-realtime engines.

    It buffers text fragments received from send_text() and only synthesizes them
    when flush() is called. Generated audio is pushed into an internal async queue
    and exposed through audio_chunks().
    """

    def __init__(
        self,
        synthesize_fn: Callable[[LiveSynthesisRequest], AsyncIterator[LiveAudioChunk]],
    ) -> None:
        self._synthesize_fn = synthesize_fn
        self._request_queue: asyncio.Queue[LiveSynthesisRequest | None] = asyncio.Queue()
        self._event_queue: asyncio.Queue[_ChunkEvent | _ErrorEvent | _ClosedEvent] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None
        self._state_lock = asyncio.Lock()
        self._closed = False

        self._pending_text = ''
        self._pending_voice_id: str | None = None
        self._pending_lora_name: str | None = None
        self._pending_language: str = 'ru'

    async def start(self) -> None:
        if self._worker_task is not None:
            return
        self._worker_task = asyncio.create_task(self._worker_loop(), name='buffered-live-stream-session')

    async def send_text(self, text: str, request: LiveSynthesisRequest) -> None:
        if self._closed:
            raise RuntimeError('Live stream session is closed')
        if not text.strip():
            return

        await self.start()

        async with self._state_lock:
            self._pending_text = self._join_text(self._pending_text, text)
            self._pending_voice_id = request.voice_id
            self._pending_lora_name = request.lora_name
            self._pending_language = request.language or 'ru'

    async def flush(self) -> None:
        if self._closed:
            return

        await self.start()

        async with self._state_lock:
            text = self._pending_text.strip()
            if not text:
                return

            request = LiveSynthesisRequest(
                text=text,
                voice_id=self._pending_voice_id,
                lora_name=self._pending_lora_name,
                language=self._pending_language,
            )

            self._pending_text = ''

        await self._request_queue.put(request)

    async def clear(self) -> None:
        async with self._state_lock:
            self._pending_text = ''

        while True:
            try:
                item = self._request_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            else:
                self._request_queue.task_done()
                if item is None:
                    await self._request_queue.put(None)
                    break

    async def audio_chunks(self) -> AsyncIterator[LiveAudioChunk]:
        while True:
            event = await self._event_queue.get()

            if isinstance(event, _ChunkEvent):
                yield event.chunk
                continue

            if isinstance(event, _ErrorEvent):
                raise RuntimeError(event.message)

            if isinstance(event, _ClosedEvent):
                return

    async def close(self) -> None:
        if self._closed:
            return

        self._closed = True

        async with self._state_lock:
            self._pending_text = ''

        await self._request_queue.put(None)

        if self._worker_task is not None:
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        await self._event_queue.put(_ClosedEvent())

    async def _worker_loop(self) -> None:
        while True:
            request = await self._request_queue.get()
            try:
                if request is None:
                    return

                try:
                    async for chunk in self._synthesize_fn(request):
                        await self._event_queue.put(_ChunkEvent(chunk))
                except Exception as exc:
                    await self._event_queue.put(_ErrorEvent(str(exc)))
            finally:
                self._request_queue.task_done()

    @staticmethod
    def _join_text(current: str, incoming: str) -> str:
        left = current.strip()
        right = incoming.strip()

        if not left:
            return right
        if not right:
            return left
        if right.startswith((',', '.', '!', '?', ';', ':')):
            return f'{left}{right}'.strip()
        return f'{left} {right}'.strip()


class LiveEngine(ABC):
    @abstractmethod
    async def warmup(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def open_session(self) -> LiveStreamSession:
        raise NotImplementedError

    @abstractmethod
    async def synthesize_segment(self, request: LiveSynthesisRequest) -> AsyncIterator[LiveAudioChunk]:
        raise NotImplementedError