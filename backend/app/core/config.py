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

    # Legacy global backend. New code should prefer resolved_preview_backend / resolved_live_backend.
    tts_backend: str = Field(default='mock', alias='TTS_BACKEND')

    # Explicit split: preview and live can use different engines.
    preview_backend: str | None = Field(default=None, alias='PREVIEW_BACKEND')
    live_backend: str | None = Field(default=None, alias='LIVE_BACKEND')

    # Qwen preview/local backend
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

    # Legacy cloud realtime Qwen settings (kept for backward compatibility)
    qwen_realtime_ws_url: str | None = Field(default=None, alias='QWEN_REALTIME_WS_URL')
    qwen_realtime_api_key: str | None = Field(default=None, alias='QWEN_REALTIME_API_KEY')
    qwen_realtime_model: str = Field(default='qwen3-tts-flash-realtime', alias='QWEN_REALTIME_MODEL')
    qwen_realtime_mode: str = Field(default='commit', alias='QWEN_REALTIME_MODE')
    qwen_realtime_sample_rate: int = Field(default=24000, alias='QWEN_REALTIME_SAMPLE_RATE')
    qwen_realtime_format: str = Field(default='pcm', alias='QWEN_REALTIME_FORMAT')

    # CosyVoice2 local live backend
    cosyvoice_root: Path | None = Field(default=None, alias='COSYVOICE_ROOT')
    cosyvoice_model_dir: str = Field(default='pretrained_models/CosyVoice2-0.5B', alias='COSYVOICE_MODEL_DIR')
    cosyvoice_prompt_dir: Path | None = Field(default=None, alias='COSYVOICE_PROMPT_DIR')
    cosyvoice_default_prompt_wav: Path | None = Field(default=None, alias='COSYVOICE_DEFAULT_PROMPT_WAV')
    cosyvoice_default_prompt_text: str = Field(default='', alias='COSYVOICE_DEFAULT_PROMPT_TEXT')
    cosyvoice_stream: bool = Field(default=True, alias='COSYVOICE_STREAM')
    cosyvoice_text_frontend: bool = Field(default=True, alias='COSYVOICE_TEXT_FRONTEND')
    cosyvoice_speed: float = Field(default=1.0, alias='COSYVOICE_SPEED')
    cosyvoice_fp16: bool = Field(default=True, alias='COSYVOICE_FP16')
    cosyvoice_load_jit: bool = Field(default=False, alias='COSYVOICE_LOAD_JIT')
    cosyvoice_load_trt: bool = Field(default=False, alias='COSYVOICE_LOAD_TRT')
    cosyvoice_load_vllm: bool = Field(default=False, alias='COSYVOICE_LOAD_VLLM')

    audio_sample_rate: int = Field(default=24000, alias='AUDIO_SAMPLE_RATE')
    training_poll_seconds: int = Field(default=5, alias='TRAINING_POLL_SECONDS')

    live_buffer_idle_ms: int = Field(default=120, alias='LIVE_BUFFER_IDLE_MS')
    live_buffer_soft_flush_chars: int = Field(default=24, alias='LIVE_BUFFER_SOFT_FLUSH_CHARS')
    live_buffer_target_chars: int = Field(default=36, alias='LIVE_BUFFER_TARGET_CHARS')
    live_buffer_max_chars: int = Field(default=56, alias='LIVE_BUFFER_MAX_CHARS')
    live_pcm_chunk_ms: int = Field(default=40, alias='LIVE_PCM_CHUNK_MS')
    live_dictionary_cache_ttl_seconds: int = Field(default=10, alias='LIVE_DICTIONARY_CACHE_TTL_SECONDS')

    @property
    def resolved_preview_backend(self) -> str:
        if self.preview_backend:
            return self.preview_backend
        if self.tts_backend == 'qwen_realtime':
            # preview should stay local/offline-friendly
            return 'qwen'
        return self.tts_backend

    @property
    def resolved_live_backend(self) -> str:
        if self.live_backend:
            return self.live_backend
        return self.tts_backend

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

    @property
    def cosyvoice_prompt_dir_resolved(self) -> Path:
        return self.cosyvoice_prompt_dir or (self.data_dir / 'cosyvoice_prompts')


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.datasets_dir.mkdir(parents=True, exist_ok=True)
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    settings.cosyvoice_prompt_dir_resolved.mkdir(parents=True, exist_ok=True)
    return settings