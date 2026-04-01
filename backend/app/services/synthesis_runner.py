from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.synthesis import SynthesisJob
from app.services.audio import concat_wav_segments, wav_to_mp3
from app.services.book_preprocessor import LiteraryPreprocessor
from app.services.preview.base import PreviewRequest
from app.services.preview.factory import get_preview_engine
from app.services.preprocessor import TechnicalPreprocessor
from app.services.text_extractor import extract_text

settings = get_settings()


def _append_log(job: SynthesisJob, line: str) -> None:
    job.log = ((job.log or "").strip() + "\n" + line).strip()
    job.updated_at = datetime.utcnow()


class SynthesisRunner:
    def __init__(self) -> None:
        self.preview_engine = get_preview_engine()
        self.tech_preprocessor = TechnicalPreprocessor()
        self.literary_preprocessor = LiteraryPreprocessor()

    async def run_job(self, job_id: int) -> None:
        await self.preview_engine.warmup()

        with SessionLocal() as db:
            job = db.get(SynthesisJob, job_id)
            if job is None:
                return

            try:
                job.status = "running"
                job.stage = "uploaded"
                job.progress = 10
                _append_log(job, "Файл загружен.")
                db.commit()

                source_path = Path(job.source_path)
                original_text = extract_text(source_path)

                job_dir = settings.artifacts_dir / f"synthesis-{job.id}"
                job_dir.mkdir(parents=True, exist_ok=True)

                original_text_path = job_dir / "original.txt"
                processed_text_path = job_dir / "processed.txt"
                wav_path = job_dir / "result.wav"
                mp3_path = job_dir / "result.mp3"

                original_text_path.write_text(original_text, encoding="utf-8")
                job.original_text_path = str(original_text_path)

                job.stage = "preprocessing"
                job.progress = 20
                _append_log(job, "Начата обработка текста.")
                db.commit()

                preprocessor = self.literary_preprocessor if job.preprocess_profile == "literary" else self.tech_preprocessor
                processed = preprocessor.process(db, original_text, dictionary_id=job.dictionary_id)

                processed_text_path.write_text(processed.processed_text, encoding="utf-8")
                job.processed_text_path = str(processed_text_path)
                job.progress = 35
                _append_log(job, "Обработка текста завершена.")
                db.commit()

                chunks = processed.chunks or [processed.processed_text]
                total_chunks = len(chunks)

                job.stage = "synthesizing"
                job.progress = 45
                _append_log(job, f"Начат синтез речи. Частей: {total_chunks}.")
                db.commit()

                wav_segments: list[bytes] = []
                log_step = max(1, total_chunks // 10)

                for idx, chunk in enumerate(chunks, start=1):
                    wav_bytes = await self.preview_engine.synthesize(
                        PreviewRequest(
                            text=chunk,
                            voice_id=job.voice_id,
                            lora_name=job.lora_name,
                            language=job.language,
                            reading_mode=job.reading_mode,
                            speaking_rate=job.speaking_rate,
                            paragraph_pause_ms=job.paragraph_pause_ms,
                        )
                    )
                    wav_segments.append(wav_bytes)

                    progress = 45 + int((idx / total_chunks) * 35)
                    job.progress = min(progress, 80)
                    if idx == 1 or idx == total_chunks or idx % log_step == 0:
                        _append_log(job, f"Синтезирована часть {idx}/{total_chunks}.")
                    db.commit()

                concat_wav_segments(
                    wav_segments,
                    output_path=wav_path,
                    pause_ms=job.paragraph_pause_ms,
                )
                job.wav_path = str(wav_path)

                job.stage = "encoding_mp3"
                job.progress = 90
                _append_log(job, "Начата конвертация в MP3.")
                db.commit()

                wav_to_mp3(wav_path, mp3_path)
                job.mp3_path = str(mp3_path)

                job.stage = "completed"
                job.status = "completed"
                job.progress = 100
                _append_log(job, "MP3 готов к загрузке.")
                db.commit()

            except Exception as exc:
                job = db.get(SynthesisJob, job_id)
                if job is not None:
                    job.status = "failed"
                    job.stage = "failed"
                    job.error_message = str(exc)
                    _append_log(job, f"Ошибка: {exc}")
                    db.commit()