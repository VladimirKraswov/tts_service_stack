from __future__ import annotations

import re
import time
from dataclasses import dataclass
from uuid import uuid4

from app.core.config import get_settings

settings = get_settings()


@dataclass(slots=True)
class BufferedSegment:
    segment_id: str
    text: str
    dictionary_id: int | None
    voice_id: str | None
    lora_name: str | None
    language: str


class LiveTextBuffer:
    def __init__(self) -> None:
        self.pending_text = ''
        self.dictionary_id: int | None = None
        self.voice_id: str | None = None
        self.lora_name: str | None = None
        self.language: str = 'ru'
        self.last_update_ts = time.monotonic()

    def update_options(
        self,
        dictionary_id: int | None,
        voice_id: str | None,
        lora_name: str | None,
        language: str | None,
    ) -> None:
        self.dictionary_id = dictionary_id
        self.voice_id = voice_id
        self.lora_name = lora_name
        self.language = language or 'ru'

    def append(
        self,
        text: str,
        *,
        dictionary_id: int | None,
        voice_id: str | None,
        lora_name: str | None,
        language: str | None,
        flush: bool = False,
    ) -> list[BufferedSegment]:
        self.update_options(dictionary_id, voice_id, lora_name, language)
        self.pending_text = self._join_text(self.pending_text, text)
        self.last_update_ts = time.monotonic()
        return self._extract_ready(force=flush)

    def flush(self) -> list[BufferedSegment]:
        self.last_update_ts = time.monotonic()
        return self._extract_ready(force=True)

    def clear(self) -> None:
        self.pending_text = ''
        self.last_update_ts = time.monotonic()

    def snapshot(self) -> dict[str, str | int]:
        return {
            'pending_text': self.pending_text,
            'pending_chars': len(self.pending_text),
        }

    def idle_flush_due(self) -> bool:
        if not self.pending_text.strip():
            return False
        elapsed = time.monotonic() - self.last_update_ts
        return elapsed >= (settings.live_buffer_idle_ms / 1000.0)

    def _extract_ready(self, *, force: bool) -> list[BufferedSegment]:
        text = self.pending_text.strip()
        if not text:
            self.pending_text = ''
            return []

        if force:
            raw_segments = self._chunk_text(text)
            self.pending_text = ''
            return [self._to_segment(item) for item in raw_segments]

        ready_segments, remainder = self._split_ready(text)
        self.pending_text = remainder
        return [self._to_segment(item) for item in ready_segments]

    def _to_segment(self, text: str) -> BufferedSegment:
        return BufferedSegment(
            segment_id=str(uuid4()),
            text=text,
            dictionary_id=self.dictionary_id,
            voice_id=self.voice_id,
            lora_name=self.lora_name,
            language=self.language,
        )

    def _split_ready(self, text: str) -> tuple[list[str], str]:
        ready: list[str] = []
        last_end = 0

        for match in re.finditer(r'.+?[.!?;:](?=\s|$)', text, flags=re.DOTALL):
            sentence = match.group(0).strip()
            if sentence:
                ready.extend(self._chunk_text(sentence))
            last_end = match.end()

        remainder = text[last_end:].strip()

        if not ready and len(text) >= settings.live_buffer_max_chars:
            head, tail = self._take_soft_chunk(text)
            ready.extend(self._chunk_text(head))
            remainder = tail

        elif ready and remainder and len(remainder) >= settings.live_buffer_max_chars:
            head, tail = self._take_soft_chunk(remainder)
            ready.extend(self._chunk_text(head))
            remainder = tail

        return ready, remainder

    def _chunk_text(self, text: str) -> list[str]:
        text = re.sub(r'\s+', ' ', text).strip()
        if not text:
            return []

        target = settings.live_buffer_target_chars
        max_len = settings.live_buffer_max_chars

        if len(text) <= max_len:
            return [text]

        chunks: list[str] = []
        rest = text
        while rest:
            if len(rest) <= max_len:
                chunks.append(rest.strip())
                break

            split_range = rest[:max_len]
            soft_pos = split_range.rfind(' ', 0, target + 1)
            if soft_pos < max(8, target // 2):
                soft_pos = split_range.rfind(' ')
            if soft_pos <= 0:
                soft_pos = max_len

            head = rest[:soft_pos].strip()
            rest = rest[soft_pos:].strip()

            if head:
                chunks.append(head)

        return chunks

    def _take_soft_chunk(self, text: str) -> tuple[str, str]:
        target = settings.live_buffer_target_chars
        max_len = settings.live_buffer_max_chars

        if len(text) <= max_len:
            return text, ''

        window = text[:max_len]
        split_pos = window.rfind(' ', 0, target + 1)
        if split_pos < max(8, target // 2):
            split_pos = window.rfind(' ')
        if split_pos <= 0:
            split_pos = max_len

        return text[:split_pos].strip(), text[split_pos:].strip()

    def _join_text(self, current: str, incoming: str) -> str:
        left = current.strip()
        right = incoming.strip()

        if not left:
            return right
        if not right:
            return left

        if left.endswith((' ', '\n')):
            return f'{left}{right}'.strip()

        if right.startswith((',', '.', '!', '?', ';', ':')):
            return f'{left}{right}'.strip()

        return f'{left} {right}'.strip()