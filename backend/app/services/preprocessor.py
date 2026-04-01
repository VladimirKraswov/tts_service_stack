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
        # Standard technical replacements
        self.tech_replacements = [
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
            (r"\bGPU\b", "джи пи ю"),
            (r"\bCPU\b", "си пи ю"),
            (r"\bWebSocket\b", "веб сокет"),
            (r"\bFastAPI\b", "фаст эй пи ай"),
            (r"\bPostgreSQL\b", "постгрес"),
            (r"\bRedis\b", "редис"),
            (r"\bDocker\b", "докер"),
            (r"\bReact\b", "ре акт"),
            (r"\bTypeScript\b", "тайп скрипт"),
            (r"\bJavaScript\b", "джава скрипт"),
            (r"\bPython\b", "пайтон"),
            (r"\bGolang\b", "гоу лэнг"),
            (r"\bJWT\b", "джи дабл ю ти"),
            (r"\bOAuth\b", "о аус"),
            (r"\bnginx\b", "энджиикс"),
        ]

        # General/Literary replacements
        self.literary_replacements = [
            (r"\bт\.е\.", "то есть"),
            (r"\bт\.к\.", "так как"),
            (r"\bт\.д\.", "так далее"),
            (r"\bт\.п\.", "тому подобное"),
            (r"\bи т\.д\.", "и так далее"),
            (r"\bи т\.п\.", "и тому подобное"),
            (r"\bдр\.", "другие"),
            (r"\bстр\.", "страница"),
            (r"\bгл\.", "глава"),
            (r"\bрис\.", "рисунок"),
            (r"\bтабл\.", "таблица"),
            (r"\bкв\.", "квартира"),
            (r"\bд\.", "дом"),
            (r"\bул\.", "улица"),
            (r"\bпросп\.", "проспект"),
            (r"\bпер\.", "переулок"),
            (r"\bпос\.", "посёлок"),
            (r"\bобл\.", "область"),
            (r"\bим\.", "имени"),
            (r"\bгг\.", "годы"),
            (r"\bг\.", "город"),
            (r"№", "номер"),
        ]

    def process(
        self,
        db: Session,
        text: str,
        dictionary_id: int | None = None,
        profile: str = "general",
    ) -> ProcessedPayload:
        # Stage 1: Normalize
        text = self._normalize(text)

        # Stage 2: Structural cleanup (code blocks, etc)
        text = self._structural_cleanup(text, profile)

        # Stage 3: Profile-specific rules
        text = self._apply_profile_rules(text, profile)

        # Stage 4: Dictionary application
        text = self._apply_dictionary(db, text, dictionary_id)

        # Stage 5: Post-processing cleanup
        text = self._post_process(text)

        # Stage 6: Chunking
        chunks = self._chunk(text, profile)

        return ProcessedPayload(original_text=text, processed_text=text, chunks=chunks)

    def _normalize(self, text: str) -> str:
        text = unicodedata.normalize("NFKC", text)
        text = text.replace("\u00A0", " ")
        # Normalize quotes and dashes
        text = text.replace("«", "\"").replace("»", "\"").replace("„", "\"").replace("“", "\"")
        text = text.replace("—", " - ").replace("–", " - ").replace("−", " - ")

        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _structural_cleanup(self, text: str, profile: str) -> str:
        if profile == "technical":
            text = self._rewrite_code(text)

        # Dialogue handling: replace leading dash with something more TTS friendly if needed
        # Or just ensure it has space
        text = re.sub(r"^(\s*)-\s+", r"\1— ", text, flags=re.MULTILINE)

        return text

    def _rewrite_code(self, text: str) -> str:
        def code_fence_repl(match: re.Match[str]) -> str:
            lang = match.group(1) or "code"
            body = match.group(2).strip()
            return f" Блок кода {lang}. {self._speak_code(body)}. Конец блока кода. "

        text = re.sub(r"```([a-zA-Z0-9_+-]*)\n(.*?)```", code_fence_repl, text, flags=re.DOTALL)
        text = re.sub(r"`([^`]+)`", lambda m: f" {self._speak_code(m.group(1))} ", text)
        return text

    def _speak_code(self, code: str) -> str:
        replacements = {
            "==": " равно равно ",
            "!=": " не равно ",
            "=>": " стрелка ",
            "->": " стрелка ",
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
        }
        for src, dst in replacements.items():
            code = code.replace(src, dst)
        code = re.sub(r"([a-z])([A-Z])", r"\1 \2", code)
        return re.sub(r"\s+", " ", code).strip()

    def _apply_profile_rules(self, text: str, profile: str) -> str:
        # Generic rules (shared across profiles, mostly common abbreviations)
        for pattern, replacement in self.literary_replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        if profile == "literary":
            text = self._apply_literary_rules(text)
        elif profile == "technical":
            text = self._apply_technical_rules(text)
        elif profile == "general":
            text = self._apply_general_rules(text)

        return text

    def _apply_literary_rules(self, text: str) -> str:
        # Handle Chapter headings: Глава I -> Глава первая
        def replace_chapter(match: re.Match[str]) -> str:
            prefix = match.group(1)
            num_roman = match.group(2).upper()
            roman_to_ru = {
                "I": "первая", "II": "вторая", "III": "третья", "IV": "четвертая",
                "V": "пятая", "VI": "шестая", "VII": "седьмая", "VIII": "восьмая",
                "IX": "девятая", "X": "десятая",
            }
            return f"{prefix} {roman_to_ru.get(num_roman, num_roman)}"

        text = re.sub(r"\b(Глава|Часть)\s+([IVXLCDM]+)\b", replace_chapter, text, flags=re.IGNORECASE)

        # Handle initials: А. С. Пушкин -> А.С. Пушкин (keeping it together)
        text = re.sub(r"\b([А-Я])\.\s+([А-Я])\.\s+([А-Я][а-я]+)", r"\1. \2. \3", text)

        return text

    def _apply_technical_rules(self, text: str) -> str:
        # Apply tech replacements first
        for pattern, replacement in self.tech_replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        # Handle paths
        text = re.sub(r"(/[a-zA-Z0-9._-]+)+", lambda m: m.group(0).replace("/", " слэш "), text)

        return text

    def _apply_general_rules(self, text: str) -> str:
        # Units and money
        units = [
            (r"\bкг\b", "килограмм"),
            (r"\bсм\b", "сантиметр"),
            (r"\bмм\b", "миллиметр"),
            (r"\bкм\b", "километр"),
            (r"\bмс\b", "миллисекунда"),
            (r"\bс\b", "секунда"),
            (r"\bмин\b", "минута"),
            (r"\bч\b", "час"),
            (r"\bруб\.", "рубль"),
            (r"₽", "рубль"),
            (r"%", "процент"),
        ]
        for pattern, replacement in units:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        return text

    def _apply_dictionary(self, db: Session, text: str, dictionary_id: int | None) -> str:
        dictionary = None
        if dictionary_id is not None:
            dictionary = db.get(Dictionary, dictionary_id)
        if dictionary is None:
            dictionary = db.scalar(select(Dictionary).where(Dictionary.is_default.is_(True)))

        if dictionary is None or not dictionary.entries:
            return text

        # Sort by priority then by length descending
        entries = sorted(
            dictionary.entries,
            key=lambda e: (e.priority, len(e.source_text)),
            reverse=True
        )

        for entry in entries:
            if not entry.is_enabled:
                continue

            pattern = re.escape(entry.source_text)
            if entry.source_text and entry.source_text[0].isalnum():
                pattern = r"\b" + pattern
            if entry.source_text and entry.source_text[-1].isalnum():
                pattern = pattern + r"\b"

            flags = 0 if entry.case_sensitive else re.IGNORECASE
            text = re.compile(pattern, flags).sub(entry.spoken_text, text)
        return text

    def _post_process(self, text: str) -> str:
        # Cleanup extra spaces
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

    def _chunk(self, text: str, profile: str) -> list[str]:
        # Improved chunking logic: respect paragraphs first
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        target = 180 if profile == "technical" else 250
        max_len = 260 if profile == "technical" else 400

        all_chunks: list[str] = []

        for paragraph in paragraphs:
            segments = [s.strip() for s in re.split(r"(?<=[.!?;])\s+(?=[А-ЯA-Z\"—])", paragraph) if s.strip()]
            if not segments:
                segments = [paragraph]

            buffer = ""
            for segment in segments:
                if not buffer:
                    buffer = segment
                    continue

                candidate = f"{buffer} {segment}".strip()
                if len(candidate) <= target:
                    buffer = candidate
                else:
                    all_chunks.append(buffer)
                    buffer = segment

            if buffer:
                all_chunks.append(buffer)

        # Final safety split for oversized chunks
        final_chunks: list[str] = []
        for chunk in all_chunks:
            if len(chunk) <= max_len:
                final_chunks.append(chunk)
                continue

            # Split by words if still too long
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

        return [chunk for chunk in final_chunks if chunk]
