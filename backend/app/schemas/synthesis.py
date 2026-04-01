from datetime import datetime

from pydantic import BaseModel


class SynthesisJobCreateResponse(BaseModel):
    id: int
    status: str
    stage: str
    progress: int


class SynthesisJobRead(BaseModel):
    id: int
    source_name: str
    status: str
    stage: str
    progress: int

    voice_id: str | None
    lora_name: str | None
    language: str
    preprocess_profile: str
    reading_mode: str
    dictionary_id: int | None
    speaking_rate: str | None
    paragraph_pause_ms: int

    original_text_path: str | None
    processed_text_path: str | None
    wav_path: str | None
    mp3_path: str | None

    error_message: str | None
    log: str | None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}