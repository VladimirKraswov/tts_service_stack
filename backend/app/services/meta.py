from app.core.config import get_settings
from app.services.live.factory import get_live_engine
from app.services.preview.factory import get_preview_engine


def get_meta() -> dict:
    settings = get_settings()
    preview_engine = get_preview_engine()
    live_engine = get_live_engine()

    return {
        'app_title': settings.app_title,
        'tts_backend': settings.tts_backend,
        'preview_backend': settings.effective_preview_backend,
        'live_backend': settings.effective_live_backend,
        'qwen_model_name': settings.qwen_model_name,
        'preview_engine_class': preview_engine.__class__.__name__,
        'live_engine_class': live_engine.__class__.__name__,
    }