from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class VoiceProfile(Base):
    __tablename__ = 'voice_profiles'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    backend: Mapped[str] = mapped_column(String(60), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default='voice', nullable=False)
