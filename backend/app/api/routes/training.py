from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.models.training import TrainingDataset, TrainingJob
from app.schemas.training import TrainingDatasetRead, TrainingJobCreate, TrainingJobRead
from app.services.storage import save_upload

router = APIRouter(prefix='/training', tags=['training'])
settings = get_settings()


@router.get('/datasets', response_model=list[TrainingDatasetRead])
def list_datasets(db: Session = Depends(get_db)) -> list[TrainingDataset]:
    return list(db.scalars(select(TrainingDataset).order_by(TrainingDataset.id.desc())))


@router.post('/datasets', response_model=TrainingDatasetRead)
def upload_dataset(
    name: str = Form(...),
    speaker_name: str = Form(...),
    language: str = Form('ru'),
    note: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> TrainingDataset:
    # Validation: only zip/tar/gz
    allowed_ext = ('.zip', '.tar', '.gz')
    if not file.filename or not file.filename.lower().endswith(allowed_ext):
        raise HTTPException(status_code=400, detail=f"Invalid file format. Allowed: {', '.join(allowed_ext)}")

    # Secure speaker name to prevent path traversal
    safe_speaker_name = "".join([c for c in speaker_name if c.isalnum() or c in (' ', '_', '-')]).strip().replace(' ', '_')
    if not safe_speaker_name:
        safe_speaker_name = "default_speaker"

    dataset_dir = settings.datasets_dir / safe_speaker_name
    saved_path = save_upload(file, dataset_dir)
    dataset = TrainingDataset(
        name=name,
        speaker_name=speaker_name,
        language=language,
        note=note,
        file_path=str(saved_path),
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


@router.get('/jobs', response_model=list[TrainingJobRead])
def list_jobs(db: Session = Depends(get_db)) -> list[TrainingJob]:
    return list(db.scalars(select(TrainingJob).order_by(TrainingJob.id.desc())))


@router.post('/jobs', response_model=TrainingJobRead)
def create_job(payload: TrainingJobCreate, db: Session = Depends(get_db)) -> TrainingJob:
    dataset = db.get(TrainingDataset, payload.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail='Dataset not found')
    job = TrainingJob(
        dataset_id=payload.dataset_id,
        base_model=payload.base_model,
        output_name=payload.output_name,
        status='queued',
        progress=0,
        log='Job created and queued.',
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
