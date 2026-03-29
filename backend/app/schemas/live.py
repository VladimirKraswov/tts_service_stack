from pydantic import BaseModel


class LiveEnqueueRequest(BaseModel):
    session_id: str
    text: str
    dictionary_id: int | None = None
    voice_id: str | None = None
    lora_name: str | None = None
    language: str = 'ru'


class LivePreviewRequest(BaseModel):
    text: str
    dictionary_id: int | None = None
    voice_id: str | None = None
    lora_name: str | None = None
    language: str = 'ru'
