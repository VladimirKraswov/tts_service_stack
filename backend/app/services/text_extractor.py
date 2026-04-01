from __future__ import annotations

from pathlib import Path

SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md"}


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_TEXT_EXTENSIONS:
        raise ValueError(
            f"Unsupported text format: {suffix}. Allowed: {', '.join(sorted(SUPPORTED_TEXT_EXTENSIONS))}"
        )

    for encoding in ("utf-8", "utf-8-sig", "cp1251", "koi8-r"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError(f"Could not decode text file: {path.name}")