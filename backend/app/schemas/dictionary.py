from pydantic import BaseModel, Field


class DictionaryEntryCreate(BaseModel):
    source_text: str = Field(min_length=1, max_length=255)
    spoken_text: str = Field(min_length=1, max_length=255)
    note: str | None = None


class DictionaryEntryRead(DictionaryEntryCreate):
    id: int

    model_config = {'from_attributes': True}


class DictionaryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=120)
    description: str | None = None
    is_default: bool = False


class DictionaryRead(DictionaryCreate):
    id: int
    entries: list[DictionaryEntryRead] = Field(default_factory=list)

    model_config = {'from_attributes': True}


class PronunciationPreviewRequest(BaseModel):
    text: str = Field(min_length=1)


class PronunciationPreviewResponse(BaseModel):
    original_text: str
    processed_text: str