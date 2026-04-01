from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.preprocessor import TechnicalPreprocessor


@dataclass(slots=True)
class BookProcessedPayload:
    original_text: str
    processed_text: str
    chunks: list[str]


_ROMAN_CHAPTERS = {
    "I": "первая",
    "II": "вторая",
    "III": "третья",
    "IV": "четвёртая",
    "V": "пятая",
    "VI": "шестая",
    "VII": "седьмая",
    "VIII": "восьмая",
    "IX": "девятая",
    "X": "десятая",
}


class LiteraryPreprocessor(TechnicalPreprocessor):
    def process(self, db: Session, text: str, dictionary_id: int | None = None) -> BookProcessedPayload:
        original_text = text

        normalized = self._normalize_literary(text)
        normalized = self._apply_literary_rules(normalized)
        normalized = self._apply_regex(normalized)
        normalized = self._apply_dictionary(db, normalized, dictionary_id)
        normalized = self._post_process(normalized)

        chunks = self._chunk_literary(normalized)
        processed_text = normalized.replace("<PARA_BREAK>", "\n\n").strip()

        return BookProcessedPayload(
            original_text=original_text,
            processed_text=processed_text,
            chunks=chunks,
        )

    def _normalize_literary(self, text: str) -> str:
        text = unicodedata.normalize("NFKC", text)
        text = text.replace("\u00A0", " ")
        text = text.replace("«", '"').replace("»", '"')
        text = text.replace("–", "—")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _apply_literary_rules(self, text: str) -> str:
        def chapter_repl(match: re.Match[str]) -> str:
            roman = match.group(1).upper()
            ordinal = _ROMAN_CHAPTERS.get(roman)
            if ordinal:
                return f"Глава {ordinal}"
            return match.group(0)

        text = re.sub(r"\bГлава\s+([IVX]+)\b", chapter_repl, text, flags=re.IGNORECASE)

        replacements: list[tuple[str, str]] = [
            (r"\bи\s+т\.\s*д\.", "и так далее"),
            (r"\bи\s+т\.\s*п\.", "и тому подобное"),
            (r"\bт\.\s*е\.", "то есть"),
            (r"\bт\.\s*к\.", "так как"),
            (r"\bт\.\s*д\.", "так далее"),
            (r"\bт\.\s*п\.", "тому подобное"),
            (r"\bгл\.", "глава"),
            (r"\bстр\.", "страница"),
            (r"\bрис\.", "рисунок"),
            (r"\bтабл\.", "таблица"),
            (r"\bим\.", "имени"),
            (r"№\s*(\d+)", r"номер \1"),
        ]

        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        text = re.sub(r"\b([А-ЯЁ])\.\s*([А-ЯЁ])\.\s*([А-ЯЁ][а-яё]+)\b", r"\1 \2 \3", text)
        text = re.sub(r"\b([А-ЯЁ])\.\s*([А-ЯЁ][а-яё]+)\b", r"\1 \2", text)

        text = re.sub(r"\n\s*\n", " <PARA_BREAK> ", text)
        text = re.sub(r"\s*—\s*", " — ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _chunk_literary(self, text: str) -> list[str]:
        paragraphs = [part.strip() for part in text.split("<PARA_BREAK>") if part.strip()]
        if not paragraphs:
            return [text.replace("<PARA_BREAK>", "").strip()]

        chunks: list[str] = []
        max_len = 320
        target = 260

        for paragraph in paragraphs:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", paragraph) if s.strip()]
            if not sentences:
                sentences = [paragraph]

            buffer = ""
            for sentence in sentences:
                candidate = f"{buffer} {sentence}".strip() if buffer else sentence
                if len(candidate) <= target:
                    buffer = candidate
                else:
                    if buffer:
                        chunks.append(buffer)
                    buffer = sentence

            if buffer:
                chunks.append(buffer)

        final_chunks: list[str] = []
        for chunk in chunks:
            if len(chunk) <= max_len:
                final_chunks.append(chunk)
                continue

            words = chunk.split()
            current: list[str] = []
            for word in words:
                candidate = " ".join(current + [word]).strip()
                if current and len(candidate) > max_len:
                    final_chunks.append(" ".join(current))
                    current = [word]
                else:
                    current.append(word)

            if current:
                final_chunks.append(" ".join(current))

        if len(final_chunks) >= 2 and len(final_chunks[-1]) < 50:
            final_chunks[-2] = f"{final_chunks[-2]} {final_chunks[-1]}".strip()
            final_chunks.pop()

        return [chunk.replace("<PARA_BREAK>", "").strip() for chunk in final_chunks if chunk.strip()]