from app.core.config import get_settings
from app.services.preview.base import PreviewEngine
from app.services.preview.mock import MockPreviewEngine
from app.services.preview.qwen import QwenPreviewEngine

_engine: PreviewEngine | None = None


def get_preview_engine() -> PreviewEngine:
    global _engine
    if _engine is not None:
        return _engine

    settings = get_settings()
    if settings.tts_backend == 'qwen':
        _engine = QwenPreviewEngine()
    else:
        _engine = MockPreviewEngine()
    return _engine