from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.models.dictionary import Dictionary
from app.models.synthesis import SynthesisJob
from app.schemas.synthesis import SynthesisJobCreateResponse, SynthesisJobRead
from app.services.storage import save_upload
from app.services.synthesis_runner import SynthesisRunner
from app.services.text_extractor import SUPPORTED_TEXT_EXTENSIONS

router = APIRouter(prefix="/synthesis", tags=["synthesis"])
settings = get_settings()
runner = SynthesisRunner()


def _validate_text_upload(file: UploadFile) -> None:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_TEXT_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_TEXT_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Unsupported file format. Allowed: {allowed}")


def _resolve_default_dictionary_id(db: Session, preprocess_profile: str) -> int | None:
    if preprocess_profile == "literary":
        literary_dict = db.scalar(select(Dictionary).where(Dictionary.slug == "default-literary"))
        if literary_dict is not None:
            return literary_dict.id

    default_dict = db.scalar(select(Dictionary).where(Dictionary.is_default.is_(True)))
    return default_dict.id if default_dict is not None else None


@router.post("", response_model=SynthesisJobCreateResponse)
async def create_synthesis_job(
    file: UploadFile = File(...),
    voice_id: str | None = Form(None),
    lora_name: str | None = Form(None),
    language: str = Form("ru"),
    preprocess_profile: str = Form("literary"),
    reading_mode: str = Form("narration"),
    dictionary_id: int | None = Form(None),
    speaking_rate: str | None = Form(None),
    paragraph_pause_ms: int = Form(500),
    db: Session = Depends(get_db),
) -> SynthesisJobCreateResponse:
    _validate_text_upload(file)

    if preprocess_profile not in {"literary", "technical", "general"}:
        raise HTTPException(status_code=400, detail="preprocess_profile must be literary, technical or general")

    if reading_mode not in {"narration", "expressive", "dialogue", "technical"}:
        raise HTTPException(status_code=400, detail="reading_mode is invalid")

    if speaking_rate is not None and speaking_rate not in {"slow", "normal", "fast"}:
        raise HTTPException(status_code=400, detail="speaking_rate must be slow, normal or fast")

    if paragraph_pause_ms < 0 or paragraph_pause_ms > 5000:
        raise HTTPException(status_code=400, detail="paragraph_pause_ms must be between 0 and 5000")

    target_dir = settings.upload_dir / "synthesis"
    saved_path = save_upload(file, target_dir)

    effective_dictionary_id = dictionary_id
    if effective_dictionary_id is None:
        effective_dictionary_id = _resolve_default_dictionary_id(db, preprocess_profile)

    job = SynthesisJob(
        source_name=file.filename or "text.txt",
        source_path=str(saved_path),
        status="uploaded",
        stage="uploaded",
        progress=5,
        voice_id=voice_id,
        lora_name=lora_name,
        language=language,
        preprocess_profile=preprocess_profile,
        reading_mode=reading_mode,
        dictionary_id=effective_dictionary_id,
        speaking_rate=speaking_rate,
        paragraph_pause_ms=paragraph_pause_ms,
        log="Задача создана.",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    asyncio.create_task(runner.run_job(job.id))

    return SynthesisJobCreateResponse(
        id=job.id,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
    )


@router.get("", response_model=list[SynthesisJobRead])
def list_synthesis_jobs(db: Session = Depends(get_db)) -> list[SynthesisJob]:
    return list(db.scalars(select(SynthesisJob).order_by(SynthesisJob.id.desc())))


@router.get("/{job_id}", response_model=SynthesisJobRead)
def get_synthesis_job(job_id: int, db: Session = Depends(get_db)) -> SynthesisJob:
    job = db.get(SynthesisJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Synthesis job not found")
    return job


@router.get("/{job_id}/download")
def download_synthesis_mp3(job_id: int, db: Session = Depends(get_db)) -> FileResponse:
    job = db.get(SynthesisJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Synthesis job not found")

    if job.status != "completed" or not job.mp3_path:
        raise HTTPException(status_code=409, detail="MP3 is not ready yet")

    mp3_path = Path(job.mp3_path)
    if not mp3_path.exists():
        raise HTTPException(status_code=404, detail="MP3 file not found")

    return FileResponse(
        mp3_path,
        media_type="audio/mpeg",
        filename=f"synthesis-{job.id}.mp3",
    )