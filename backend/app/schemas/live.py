from pydantic import BaseModel, Field


class LiveOptions(BaseModel):
    dictionary_id: int | None = None
    voice_id: str | None = None
    lora_name: str | None = None
    language: str = 'ru'


class LiveEnqueueRequest(LiveOptions):
    session_id: str
    text: str = Field(min_length=1)


class LiveBufferAppendRequest(LiveEnqueueRequest):
    flush: bool = False


class LiveFlushRequest(BaseModel):
    session_id: str


class LivePreviewRequest(LiveOptions):
    text: str = Field(min_length=1)