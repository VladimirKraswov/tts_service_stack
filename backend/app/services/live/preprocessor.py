from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.dictionary import Dictionary, DictionaryEntry

settings = get_settings()


@dataclass(slots=True)
class CachedDictionary:
    loaded_at: float
    entries: list[tuple[str, str, bool, int]]


class LiveDictionaryCache:
    def __init__(self) -> None:
        self._cache: dict[str, CachedDictionary] = {}

    def get_entries(self, db: Session, dictionary_id: int | None) -> list[tuple[str, str, bool, int]]:
        cache_key = f'dict:{dictionary_id or "default"}'
        now = time.monotonic()

        cached = self._cache.get(cache_key)
        if cached and (now - cached.loaded_at) < settings.live_dictionary_cache_ttl_seconds:
            return cached.entries

        dictionary = None
        if dictionary_id is not None:
            dictionary = db.get(Dictionary, dictionary_id)

        if dictionary is None:
            dictionary = db.scalar(select(Dictionary).where(Dictionary.is_default.is_(True)))

        if dictionary is None:
            entries: list[tuple[str, str, bool, int]] = []
        else:
            rows = db.scalars(
                select(DictionaryEntry).where(
                    DictionaryEntry.dictionary_id == dictionary.id,
                    DictionaryEntry.is_enabled.is_(True),
                )
            ).all()
            entries = sorted(
                [
                    (row.source_text, row.spoken_text, row.case_sensitive, row.priority)
                    for row in rows
                ],
                key=lambda item: (item[3], len(item[0])),
                reverse=True,
            )

        self._cache[cache_key] = CachedDictionary(loaded_at=now, entries=entries)
        return entries

    def clear(self) -> None:
        self._cache.clear()


class LiveTextPreprocessor:
    def __init__(self) -> None:
        self.dictionary_cache = LiveDictionaryCache()
        self.regex_replacements = [
            (r"\bAPI\b", "эй пи ай"),
            (r"\bCLI\b", "си эл ай"),
            (r"\bJSON\b", "джейсон"),
            (r"\bHTTP\b", "эйч ти ти пи"),
            (r"\bHTTPS\b", "эйч ти ти пи эс"),
            (r"\bSQL\b", "эс кью эл"),
            (r"\bRESTful\b", "рестфул"),
            (r"\bREST\b", "рест"),
            (r"\bUI/UX\b", "ю ай ю икс"),
            (r"\bCI/CD\b", "си ай си ди"),
            (r"\bCPU\b", "си пи ю"),
            (r"\bGPU\b", "джи пи ю"),
            (r"\buseEffect\b", "юз эффект"),
            (r"\buseState\b", "юз стейт"),
            (r"\b__init__\b", "андерскор андерскор инит андерскор андерскор"),
        ]

    def process(self, db: Session, text: str, dictionary_id: int | None = None) -> str:
        text = self._normalize(text)
        text = self._apply_regex(text)
        text = self._apply_dictionary(db, text, dictionary_id)
        return text.strip()

    def _normalize(self, text: str) -> str:
        text = unicodedata.normalize("NFKC", text)
        text = text.replace("\u00A0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\s*\n\s*", " ", text)
        return text.strip()

    def _apply_regex(self, text: str) -> str:
        for pattern, replacement in self.regex_replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def _apply_dictionary(self, db: Session, text: str, dictionary_id: int | None) -> str:
        entries = self.dictionary_cache.get_entries(db, dictionary_id)
        if not entries:
            return text

        for source_text, spoken_text, case_sensitive, _priority in entries:
            pattern = re.escape(source_text)
            if source_text and source_text[0].isalnum():
                pattern = r"\b" + pattern
            if source_text and source_text[-1].isalnum():
                pattern = pattern + r"\b"

            flags = 0 if case_sensitive else re.IGNORECASE
            text = re.compile(pattern, flags).sub(spoken_text, text)

        return text