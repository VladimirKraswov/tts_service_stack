from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SynthesisJob(Base):
    __tablename__ = "synthesis_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_path: Mapped[str] = mapped_column(String(500), nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    original_text_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    processed_text_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    wav_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mp3_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    voice_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lora_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="ru")
    preprocess_profile: Mapped[str] = mapped_column(String(32), nullable=False, default="literary")
    reading_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="narration")
    dictionary_id: Mapped[int | None] = mapped_column(ForeignKey("dictionaries.id"), nullable=True)

    speaking_rate: Mapped[str | None] = mapped_column(String(16), nullable=True)
    paragraph_pause_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=500)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    log: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)