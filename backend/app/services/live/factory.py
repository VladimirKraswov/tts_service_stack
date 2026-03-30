from app.core.config import get_settings
from app.services.live.base import LiveEngine
from app.services.live.cosyvoice2 import CosyVoice2LiveEngine
from app.services.live.mock import MockLiveEngine
from app.services.live.qwen import QwenLiveEngine

_engine: LiveEngine | None = None


def get_live_engine() -> LiveEngine:
    global _engine
    if _engine is not None:
        return _engine

    settings = get_settings()
    backend = settings.effective_live_backend

    if backend in {'cosyvoice2', 'cosyvoice'}:
        _engine = CosyVoice2LiveEngine()
    elif backend == 'qwen':
        _engine = QwenLiveEngine()
    else:
        _engine = MockLiveEngine()

    return _engine