from datetime import datetime

from pydantic import BaseModel


class TrainingDatasetRead(BaseModel):
    id: int
    name: str
    speaker_name: str
    language: str
    file_path: str
    note: str | None
    created_at: datetime

    model_config = {'from_attributes': True}


class TrainingJobCreate(BaseModel):
    dataset_id: int
    base_model: str
    output_name: str


class TrainingJobRead(BaseModel):
    id: int
    dataset_id: int
    base_model: str
    output_name: str
    status: str
    progress: int
    log: str | None
    artifact_path: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {'from_attributes': True}
