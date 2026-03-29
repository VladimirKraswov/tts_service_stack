from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dictionary import Dictionary


@dataclass(slots=True)
class ProcessedPayload:
    original_text: str
    processed_text: str
    chunks: list[str]


class TechnicalPreprocessor:
    def __init__(self) -> None:
        self.regex_replacements = [
            (r"\bAPI\b", "эй пи ай"),
            (r"\bCLI\b", "си эл ай"),
            (r"\bJSON\b", "джейсон"),
            (r"\bHTTP\b", "эйч ти ти пи"),
            (r"\bHTTPS\b", "эйч ти ти пи эс"),
            (r"\bSQL\b", "эс кью эл"),
            (r"\b(REST|RESTful)\b", "рест"),
            (r"\bCI/CD\b", "си ай си ди"),
            (r"\bv(\d+)\.(\d+)\.(\d+)\b", r"версия \1.\2.\3"),
            (r"\bUI/UX\b", "ю ай ю икс"),
        ]

    def process(self, db: Session, text: str, dictionary_id: int | None = None) -> ProcessedPayload:
        normalized = self._normalize(text)
        normalized = self._rewrite_code(normalized)
        normalized = self._apply_regex(normalized)
        normalized = self._apply_dictionary(db, normalized, dictionary_id)
        chunks = self._chunk(normalized)
        return ProcessedPayload(original_text=text, processed_text=normalized, chunks=chunks)

    def _normalize(self, text: str) -> str:
        text = unicodedata.normalize("NFKC", text)
        text = text.replace("\u00A0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _rewrite_code(self, text: str) -> str:
        def code_fence_repl(match: re.Match[str]) -> str:
            lang = match.group(1) or "code"
            body = match.group(2).strip()
            return f" Блок кода {lang}. {self._speak_code(body)}. Конец блока кода. "

        text = re.sub(r"```([a-zA-Z0-9_+-]*)\n(.*?)```", code_fence_repl, text, flags=re.DOTALL)
        text = re.sub(r"`([^`]+)`", lambda m: self._speak_code(m.group(1)), text)
        return text

    def _speak_code(self, code: str) -> str:
        replacements = {
            "_": " андерскор ",
            "/": " слэш ",
            ".": " точка ",
            ":": " двоеточие ",
            ";": " точка с запятой ",
            "(": " открывающая скобка ",
            ")": " закрывающая скобка ",
            "{": " открывающая фигурная скобка ",
            "}": " закрывающая фигурная скобка ",
            "[": " открывающая квадратная скобка ",
            "]": " закрывающая квадратная скобка ",
            "==": " равно равно ",
            "!=": " не равно ",
            "=>": " стрелка ",
            "->": " стрелка ",
        }
        for src, dst in replacements.items():
            code = code.replace(src, dst)
        code = re.sub(r"([a-z])([A-Z])", r"\1 \2", code)
        return re.sub(r"\s+", " ", code).strip()

    def _apply_regex(self, text: str) -> str:
        for pattern, replacement in self.regex_replacements:
            text = re.sub(pattern, replacement, text)
        return text

    def _apply_dictionary(self, db: Session, text: str, dictionary_id: int | None) -> str:
        dictionary = None
        if dictionary_id is not None:
            dictionary = db.get(Dictionary, dictionary_id)
        if dictionary is None:
            dictionary = db.scalar(select(Dictionary).where(Dictionary.is_default.is_(True)))
        if dictionary is None or not dictionary.entries:
            return text

        # Sort by length descending to match longer phrases first
        entries = sorted(dictionary.entries, key=lambda entry: len(entry.source_text), reverse=True)
        for entry in entries:
            # Using \b word boundaries and IGNORECASE to be more robust
            # We escape the source text but wrap it in \b if it's alphanumeric
            pattern = re.escape(entry.source_text)
            if entry.source_text[0].isalnum():
                pattern = r"\b" + pattern
            if entry.source_text[-1].isalnum():
                pattern = pattern + r"\b"

            text = re.compile(pattern, re.IGNORECASE).sub(entry.spoken_text, text)
        return text

    def _chunk(self, text: str) -> list[str]:
        parts = [part.strip() for part in re.split(r"(?<=[.!?;:\n])\s+", text) if part.strip()]
        if not parts:
            return [text]
        chunks: list[str] = []
        buffer = ""
        target = 140
        max_len = 220
        for part in parts:
            if not buffer:
                buffer = part
                continue
            candidate = f"{buffer} {part}".strip()
            if len(candidate) <= target:
                buffer = candidate
            else:
                chunks.append(buffer)
                buffer = part
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
        return final_chunks
