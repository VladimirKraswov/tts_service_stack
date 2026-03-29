from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TrainingDataset(Base):
    __tablename__ = 'training_datasets'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    speaker_name: Mapped[str] = mapped_column(String(160), nullable=False)
    language: Mapped[str] = mapped_column(String(30), nullable=False, default='ru')
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class TrainingJob(Base):
    __tablename__ = 'training_jobs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('training_datasets.id'), nullable=False)
    base_model: Mapped[str] = mapped_column(String(255), nullable=False)
    output_name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default='queued', nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    log: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
