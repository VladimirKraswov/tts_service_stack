from app.core.config import get_settings
from app.services.live.base import LiveEngine
from app.services.live.cosyvoice2 import CosyVoice2LiveEngine
from app.services.live.mock import MockLiveEngine
from app.services.live.qwen import QwenLiveEngine
from app.services.live.qwen_realtime import QwenRealtimeLiveEngine

_engine: LiveEngine | None = None


def get_live_engine() -> LiveEngine:
    global _engine
    if _engine is not None:
        return _engine

    settings = get_settings()
    backend = settings.resolved_live_backend

    if backend == 'cosyvoice2':
        _engine = CosyVoice2LiveEngine()
    elif backend == 'qwen_realtime':
        _engine = QwenRealtimeLiveEngine()
    elif backend == 'qwen':
        _engine = QwenLiveEngine()
    elif backend == 'mock':
        _engine = MockLiveEngine()
    else:
        raise ValueError(f'Unsupported live backend: {backend}')

    return _engine