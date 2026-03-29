from app.core.config import get_settings
from app.services.tts.factory import get_tts_engine


def get_meta() -> dict:
    settings = get_settings()
    engine = get_tts_engine()
    return {
        'app_title': settings.app_title,
        'tts_backend': settings.tts_backend,
        'qwen_model_name': settings.qwen_model_name,
        'engine_class': engine.__class__.__name__,
    }
