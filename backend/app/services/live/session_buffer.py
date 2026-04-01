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
    preprocess_profile: str


class LiveTextBuffer:
    def __init__(self) -> None:
        self.pending_text = ''
        self.dictionary_id: int | None = None
        self.voice_id: str | None = None
        self.lora_name: str | None = None
        self.language: str = 'ru'
        self.preprocess_profile: str = 'general'
        self.last_update_ts = time.monotonic()

    def update_options(
        self,
        dictionary_id: int | None,
        voice_id: str | None,
        lora_name: str | None,
        language: str | None,
        preprocess_profile: str | None,
    ) -> None:
        self.dictionary_id = dictionary_id
        self.voice_id = voice_id
        self.lora_name = lora_name
        self.language = language or 'ru'
        self.preprocess_profile = preprocess_profile or 'general'

    def append(
        self,
        text: str,
        *,
        dictionary_id: int | None,
        voice_id: str | None,
        lora_name: str | None,
        language: str | None,
        preprocess_profile: str | None,
        flush: bool = False,
    ) -> list[BufferedSegment]:
        self.update_options(dictionary_id, voice_id, lora_name, language, preprocess_profile)
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
        return (time.monotonic() - self.last_update_ts) >= (settings.live_buffer_idle_ms / 1000.0)

    def _extract_ready(self, *, force: bool) -> list[BufferedSegment]:
        text = re.sub(r'\s+', ' ', self.pending_text).strip()
        if not text:
            self.pending_text = ''
            return []

        if force:
            ready = self._chunk_text(text)
            self.pending_text = ''
            return [self._to_segment(item) for item in ready]

        ready, remainder = self._split_ready(text)
        self.pending_text = remainder
        return [self._to_segment(item) for item in ready]

    def _split_ready(self, text: str) -> tuple[list[str], str]:
        ready: list[str] = []
        remainder = text
        min_len = settings.live_buffer_min_chars

        while remainder:
            hard_match = re.match(r'^(.*?[.!?])(\s+|$)', remainder, flags=re.DOTALL)
            if hard_match:
                segment = hard_match.group(1).strip()
                tail = remainder[hard_match.end():].strip()

                if len(segment) >= min_len or not tail:
                    ready.extend(self._chunk_text(segment))
                    remainder = tail
                    continue

            split_pos = self._find_soft_split(remainder)
            if split_pos is not None:
                head = remainder[:split_pos].strip()
                tail = remainder[split_pos:].strip()
                if head:
                    ready.extend(self._chunk_text(head))
                    remainder = tail
                    continue

            if len(remainder) >= settings.live_buffer_max_chars:
                head, tail = self._take_force_chunk(remainder)
                if head:
                    ready.extend(self._chunk_text(head))
                remainder = tail
                continue

            break

        return ready, remainder

    def _chunk_text(self, text: str) -> list[str]:
        text = re.sub(r'\s+', ' ', text).strip()
        if not text:
            return []

        max_len = settings.live_buffer_max_chars
        min_len = settings.live_buffer_min_chars

        if len(text) <= max_len:
            return [text]

        chunks: list[str] = []
        rest = text
        while rest:
            if len(rest) <= max_len:
                chunks.append(rest.strip())
                break

            head, tail = self._take_force_chunk(rest)
            if not head:
                break

            chunks.append(head)
            rest = tail

        if len(chunks) >= 2 and len(chunks[-1]) < min_len:
            chunks[-2] = f'{chunks[-2]} {chunks[-1]}'.strip()
            chunks.pop()

        return [chunk for chunk in chunks if chunk]

    def _find_soft_split(self, text: str) -> int | None:
        if len(text) < settings.live_buffer_soft_flush_chars:
            return None

        window = text[: min(len(text), settings.live_buffer_max_chars)]
        min_len = min(settings.live_buffer_min_chars, len(window))
        target = min(settings.live_buffer_target_chars, len(window))

        punctuation_candidates: list[int] = []
        for match in re.finditer(r'[,:;)\]]\s+', window):
            split_pos = match.end()
            if min_len <= split_pos <= len(window):
                punctuation_candidates.append(split_pos)

        sentence_candidates: list[int] = []
        for match in re.finditer(r'[.!?]\s+', window):
            split_pos = match.end()
            if min_len <= split_pos <= len(window):
                sentence_candidates.append(split_pos)

        if sentence_candidates:
            return min(sentence_candidates, key=lambda pos: abs(pos - target))

        if punctuation_candidates:
            return min(punctuation_candidates, key=lambda pos: abs(pos - target))

        space_candidates: list[int] = []
        for match in re.finditer(r'\s+', window):
            split_pos = match.start()
            if min_len <= split_pos <= len(window):
                space_candidates.append(split_pos)

        if space_candidates:
            return min(space_candidates, key=lambda pos: abs(pos - target))

        return None

    def _take_force_chunk(self, text: str) -> tuple[str, str]:
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) <= settings.live_buffer_max_chars:
            return text, ''

        window = text[: settings.live_buffer_max_chars]
        min_len = min(settings.live_buffer_min_chars, len(window))
        target = min(settings.live_buffer_target_chars, len(window))

        space_candidates = [
            match.start()
            for match in re.finditer(r'\s+', window)
            if min_len <= match.start() <= len(window)
        ]

        if space_candidates:
            split_pos = min(space_candidates, key=lambda pos: abs(pos - target))
        else:
            split_pos = settings.live_buffer_max_chars

        head = text[:split_pos].strip()
        tail = text[split_pos:].strip()

        if not head:
            head = text[: settings.live_buffer_max_chars].strip()
            tail = text[settings.live_buffer_max_chars :].strip()

        return head, tail

    def _to_segment(self, text: str) -> BufferedSegment:
        return BufferedSegment(
            segment_id=str(uuid4()),
            text=text,
            dictionary_id=self.dictionary_id,
            voice_id=self.voice_id,
            lora_name=self.lora_name,
            language=self.language,
            preprocess_profile=self.preprocess_profile,
        )

    def _join_text(self, current: str, incoming: str) -> str:
        left = current.strip()
        right = incoming.strip()

        if not left:
            return right
        if not right:
            return left
        if right.startswith((',', '.', '!', '?', ';', ':')):
            return f'{left}{right}'.strip()
        return f'{left} {right}'.strip()
