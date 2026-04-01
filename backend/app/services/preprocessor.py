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


_ROMAN_ORDINALS = {
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


class TechnicalPreprocessor:
    def __init__(self) -> None:
        self.shared_replacements: list[tuple[str, str]] = [
            (r"\bи\s+т\.\s*д\.", "и так далее"),
            (r"\bи\s+т\.\s*п\.", "и тому подобное"),
            (r"\bт\.\s*е\.", "то есть"),
            (r"\bт\.\s*к\.", "так как"),
            (r"\bт\.\s*д\.", "так далее"),
            (r"\bт\.\s*п\.", "тому подобное"),
            (r"№\s*(\d+)", r"номер \1"),
        ]

        self.tech_replacements: list[tuple[str, str]] = [
            (r"\bAPI\b", "эй пи ай"),
            (r"\bCLI\b", "си эл ай"),
            (r"\bJSON\b", "джейсон"),
            (r"\bHTTP\b", "эйч ти ти пи"),
            (r"\bHTTPS\b", "эйч ти ти пи эс"),
            (r"\bSQL\b", "эс кью эл"),
            (r"\bRESTful\b", "рестфул"),
            (r"\bREST\b", "рест"),
            (r"\bCI/CD\b", "си ай си ди"),
            (r"\bUI/UX\b", "ю ай ю икс"),
            (r"\bGPU\b", "джи пи ю"),
            (r"\bCPU\b", "си пи ю"),
            (r"\bv(\d+)\.(\d+)\.(\d+)\b", r"версия \1.\2.\3"),
            (r"\bWebSocket\b", "веб сокет"),
            (r"\bFastAPI\b", "фаст эй пи ай"),
            (r"\bPostgreSQL\b", "постгрес кью эл"),
            (r"\bRedis\b", "редис"),
            (r"\bDocker Compose\b", "докер компоуз"),
            (r"\bDocker\b", "докер"),
            (r"\bReact\b", "реакт"),
            (r"\bTypeScript\b", "тайп скрипт"),
            (r"\bJavaScript\b", "джава скрипт"),
            (r"\bPython\b", "пайтон"),
            (r"\bGolang\b", "гоу лэнг"),
            (r"\bJWT\b", "джей дабл ю ти"),
            (r"\bOAuth\b", "оу аут"),
            (r"\bnginx\b", "энджин икс"),
        ]

        self.general_numeric_replacements: list[tuple[str, str]] = [
            (r"(?<=\d)\s*кг\b", " килограмм"),
            (r"(?<=\d)\s*г\b", " грамм"),
            (r"(?<=\d)\s*см\b", " сантиметр"),
            (r"(?<=\d)\s*мм\b", " миллиметр"),
            (r"(?<=\d)\s*км\b", " километр"),
            (r"(?<=\d)\s*м\b", " метр"),
            (r"(?<=\d)\s*мс\b", " миллисекунд"),
            (r"(?<=\d)\s*с\b", " секунд"),
            (r"(?<=\d)\s*мин\b", " минут"),
            (r"(?<=\d)\s*ч\b", " часов"),
            (r"(?<=\d)\s*руб\.(?=\s|$)", " рублей"),
            (r"(?<=\d)\s*коп\.(?=\s|$)", " копеек"),
            (r"(?<=\d)\s*₽", " рублей"),
            (r"(?<=\d)\s*%", " процентов"),
            (r"(?<=\d)\s*млн\b", " миллионов"),
            (r"(?<=\d)\s*млрд\b", " миллиардов"),
            (r"(?<=\d)\s*тыс\.(?=\s|$)", " тысяч"),
        ]

    def process(
        self,
        db: Session,
        text: str,
        dictionary_id: int | None = None,
        profile: str = "general",
    ) -> ProcessedPayload:
        original_text = text

        normalized = self._normalize(text)
        normalized = self._structural_cleanup(normalized, profile)
        normalized = self._apply_profile_rules(normalized, profile)
        normalized = self._apply_dictionary(db, normalized, dictionary_id)
        normalized = self._post_process(normalized)
        chunks = self._chunk(normalized, profile)

        return ProcessedPayload(
            original_text=original_text,
            processed_text=normalized,
            chunks=chunks,
        )

    def _normalize(self, text: str) -> str:
        text = unicodedata.normalize("NFKC", text)
        text = text.replace("\u00A0", " ")
        text = text.replace("«", '"').replace("»", '"').replace("„", '"').replace("“", '"').replace("”", '"')
        text = text.replace("–", "—").replace("−", "-")

        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _structural_cleanup(self, text: str, profile: str) -> str:
        if profile == "technical":
            text = self._rewrite_code(text)

        text = re.sub(r"(^|\n)-\s+", r"\1— ", text)
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
        code = re.sub(r"\s+", " ", code)
        return code.strip()

    def _apply_regex(self, text: str) -> str:
        return self._apply_shared_rules(text)

    def _apply_shared_rules(self, text: str) -> str:
        for pattern, replacement in self.shared_replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def _apply_profile_rules(self, text: str, profile: str) -> str:
        text = self._apply_shared_rules(text)

        if profile == "literary":
            return self._apply_literary_rules(text)
        if profile == "technical":
            return self._apply_technical_rules(text)
        return self._apply_general_rules(text)

    def _apply_literary_rules(self, text: str) -> str:
        def replace_heading(match: re.Match[str]) -> str:
            prefix = match.group(1)
            roman = match.group(2).upper()
            return f"{prefix} {_ROMAN_ORDINALS.get(roman, roman)}"

        text = re.sub(r"\b(Глава|Часть)\s+([IVX]+)\b", replace_heading, text, flags=re.IGNORECASE)

        text = re.sub(r"\b([А-ЯЁ])\.\s*([А-ЯЁ])\.\s*([А-ЯЁ][а-яё]+)\b", r"\1 \2 \3", text)
        text = re.sub(r"\b([А-ЯЁ])\.\s*([А-ЯЁ][а-яё]+)\b", r"\1 \2", text)

        text = re.sub(r"\s*—\s*", " — ", text)
        return text

    def _apply_technical_rules(self, text: str) -> str:
        text = re.sub(r"(?<!\w)(/[A-Za-z0-9._-]+)+", self._speak_path, text)

        for pattern, replacement in self.tech_replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        return text

    def _speak_path(self, match: re.Match[str]) -> str:
        path = match.group(0)
        parts = [part for part in path.split("/") if part]
        if not parts:
            return "слэш"

        spoken: list[str] = []
        for part in parts:
            spoken.append("слэш")
            spoken.append(part)
        return " ".join(spoken)

    def _apply_general_rules(self, text: str) -> str:
        for pattern, replacement in self.general_numeric_replacements:
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

        entries = sorted(
            dictionary.entries,
            key=lambda entry: (entry.priority, len(entry.source_text)),
            reverse=True,
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
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        return text.strip()

    def _chunk(self, text: str, profile: str) -> list[str]:
        paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
        if not paragraphs:
            return [text.strip()] if text.strip() else []

        if profile == "technical":
            target = 180
            max_len = 260
        elif profile == "literary":
            target = 260
            max_len = 380
        else:
            target = 220
            max_len = 340

        chunks: list[str] = []

        for paragraph in paragraphs:
            sentences = [
                part.strip()
                for part in re.split(r"(?<=[.!?…])\s+(?=[A-ZА-ЯЁ\"(—])", paragraph)
                if part.strip()
            ]
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

        if len(final_chunks) >= 2 and len(final_chunks[-1]) < 40:
            final_chunks[-2] = f"{final_chunks[-2]} {final_chunks[-1]}".strip()
            final_chunks.pop()

        return [chunk for chunk in final_chunks if chunk]