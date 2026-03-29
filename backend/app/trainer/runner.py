from __future__ import annotations

import json
import logging
import time
from datetime import datetime

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.training import TrainingDataset, TrainingJob
from app.models.voice import VoiceProfile

configure_logging()
logger = logging.getLogger("trainer")
settings = get_settings()


def _append_log(job: TrainingJob, line: str) -> None:
    job.log = ((job.log or "").strip() + "\n" + line).strip()
    job.updated_at = datetime.utcnow()


def _process_job(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(TrainingJob, job_id)
        if job is None or job.status != "queued":
            return
        dataset = db.get(TrainingDataset, job.dataset_id)
        if dataset is None:
            job.status = "failed"
            _append_log(job, "Dataset not found.")
            db.commit()
            return

        artifact_dir = settings.artifacts_dir / f"job-{job.id}-{job.output_name}"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        job.status = "running"
        job.progress = 5
        _append_log(job, f"Started training for dataset #{dataset.id} using base model {job.base_model}.")
        db.commit()

        steps = [
            (20, "Validated dataset and generated manifest."),
            (45, "Prepared training recipe and hyperparameters."),
            (70, "Simulated fine-tuning epoch execution."),
            (90, "Exported LoRA / custom voice artifact metadata."),
        ]
        for progress, message in steps:
            time.sleep(2)
            job = db.get(TrainingJob, job_id)
            if job is None:
                return
            job.progress = progress
            _append_log(job, message)
            db.commit()

        recipe = {
            "job_id": job.id,
            "base_model": job.base_model,
            "dataset_path": dataset.file_path,
            "speaker_name": dataset.speaker_name,
            "language": dataset.language,
            "output_name": job.output_name,
            "notes": dataset.note,
            "next_step": "Replace trainer stub with real fine-tuning recipe for Qwen/CosyVoice.",
        }
        (artifact_dir / "recipe.json").write_text(json.dumps(recipe, ensure_ascii=False, indent=2), encoding="utf-8")
        (artifact_dir / "README.txt").write_text(
            "Training runner stub completed successfully. Integrate your real training pipeline here.\n",
            encoding="utf-8",
        )

        job = db.get(TrainingJob, job_id)
        if job is None:
            return
        job.status = "completed"
        job.progress = 100
        job.artifact_path = str(artifact_dir)
        _append_log(job, "Training completed. Artifact metadata generated.")
        db.add(
            VoiceProfile(
                name=f"ft-{job.output_name}-{job.id}",
                display_name=f"FT {job.output_name}",
                backend="qwen",
                model_name=str(artifact_dir),
                description=f"Fine-tuned voice exported from training job {job.id}",
                is_enabled=True,
                kind="voice",
            )
        )
        db.commit()


def main() -> None:
    init_db()
    logger.info("trainer started")
    while True:
        with SessionLocal() as db:
            queued_job = db.scalar(select(TrainingJob).where(TrainingJob.status == "queued").order_by(TrainingJob.id.asc()))
            job_id = queued_job.id if queued_job else None
        if job_id is not None:
            try:
                _process_job(job_id)
            except Exception as exc:  # pragma: no cover
                logger.exception("training job failed job_id=%s", job_id)
                with SessionLocal() as db:
                    job = db.get(TrainingJob, job_id)
                    if job is not None:
                        job.status = "failed"
                        _append_log(job, f"Unhandled error: {exc}")
                        db.commit()
        else:
            time.sleep(settings.training_poll_seconds)


if __name__ == "__main__":
    main()
