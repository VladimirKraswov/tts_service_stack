from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_title: str = Field(default='TTS Admin Stack', alias='APP_TITLE')
    app_host: str = Field(default='0.0.0.0', alias='APP_HOST')
    app_port: int = Field(default=8000, alias='APP_PORT')
    api_prefix: str = Field(default='/api/v1', alias='API_PREFIX')
    frontend_origin: str = Field(default='http://localhost:8080', alias='FRONTEND_ORIGIN')

    database_url: str = Field(
        default='postgresql+psycopg://tts_admin:tts_admin_change_me@postgres:5432/tts_admin',
        alias='DATABASE_URL',
    )
    redis_url: str = Field(default='redis://redis:6379/0', alias='REDIS_URL')
    data_dir: Path = Field(default=Path('/data'), alias='DATA_DIR')

    tts_backend: str = Field(default='mock', alias='TTS_BACKEND')
    qwen_model_name: str = Field(default='Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice', alias='QWEN_MODEL_NAME')
    qwen_device: str = Field(default='cuda:0', alias='QWEN_DEVICE')
    qwen_dtype: str = Field(default='bfloat16', alias='QWEN_DTYPE')
    qwen_attn_implementation: str = Field(default='sdpa', alias='QWEN_ATTN_IMPLEMENTATION')
    qwen_compile: bool = Field(default=False, alias='QWEN_COMPILE')
    qwen_max_concurrent: int = Field(default=2, alias='QWEN_MAX_CONCURRENT')
    qwen_preview_style: str = Field(
        default='Четко, спокойно, как технический диктор.',
        alias='QWEN_PREVIEW_STYLE',
    )

    audio_sample_rate: int = Field(default=24000, alias='AUDIO_SAMPLE_RATE')
    training_poll_seconds: int = Field(default=5, alias='TRAINING_POLL_SECONDS')

    live_buffer_idle_ms: int = Field(default=280, alias='LIVE_BUFFER_IDLE_MS')
    live_buffer_target_chars: int = Field(default=48, alias='LIVE_BUFFER_TARGET_CHARS')
    live_buffer_max_chars: int = Field(default=72, alias='LIVE_BUFFER_MAX_CHARS')
    live_pcm_chunk_ms: int = Field(default=60, alias='LIVE_PCM_CHUNK_MS')

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / 'uploads'

    @property
    def datasets_dir(self) -> Path:
        return self.data_dir / 'datasets'

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / 'artifacts'

    @property
    def models_dir(self) -> Path:
        return self.data_dir / 'models'


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.datasets_dir.mkdir(parents=True, exist_ok=True)
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    return settings