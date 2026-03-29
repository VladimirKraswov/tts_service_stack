from app.core.config import get_settings
from app.services.tts.base import TTSEngine
from app.services.tts.mock import MockTTSEngine
from app.services.tts.qwen import QwenTTSEngine


_engine: TTSEngine | None = None


def get_tts_engine() -> TTSEngine:
    global _engine
    if _engine is not None:
        return _engine
    settings = get_settings()
    if settings.tts_backend == 'qwen':
        _engine = QwenTTSEngine()
    else:
        _engine = MockTTSEngine()
    return _engine
