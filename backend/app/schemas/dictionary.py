from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ImportConflictMode(str, Enum):
    CREATE_ONLY = 'create_only'
    MERGE = 'merge'
    REPLACE_EXISTING_ENTRIES = 'replace_existing_entries'


class DictionaryEntryCreate(BaseModel):
    source_text: str = Field(min_length=1, max_length=255)
    spoken_text: str = Field(min_length=1, max_length=255)
    note: str | None = None
    case_sensitive: bool = False
    is_enabled: bool = True
    priority: int = 0


class DictionaryEntryUpdate(BaseModel):
    source_text: str | None = Field(None, min_length=1, max_length=255)
    spoken_text: str | None = Field(None, min_length=1, max_length=255)
    note: str | None = None
    case_sensitive: bool | None = None
    is_enabled: bool | None = None
    priority: int | None = None


class DictionaryEntryRead(DictionaryEntryCreate):
    id: int
    dictionary_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DictionaryEntryPagination(BaseModel):
    items: list[DictionaryEntryRead]
    total: int
    page: int
    size: int
    pages: int


class DictionaryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=120)
    description: str | None = None
    is_default: bool = False
    domain: str = 'general'
    language: str = 'ru'
    is_system: bool = False
    is_editable: bool = True
    priority: int = 0


class DictionaryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    slug: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = None
    is_default: bool | None = None
    domain: str | None = None
    language: str | None = None
    is_system: bool | None = None
    is_editable: bool | None = None
    priority: int | None = None


class DictionaryRead(DictionaryCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DictionaryExport(BaseModel):
    version: int = 1
    name: str
    slug: str
    description: str | None = None
    is_default: bool = False
    domain: str = 'general'
    language: str = 'ru'
    entries: list[DictionaryEntryCreate]


class DictionaryImportResponse(BaseModel):
    dictionary_id: int
    entries_created: int
    entries_updated: int
    entries_deleted: int


class PronunciationPreviewRequest(BaseModel):
    text: str = Field(min_length=1)


class PronunciationPreviewResponse(BaseModel):
    original_text: str
    processed_text: str
