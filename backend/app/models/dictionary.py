from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Dictionary(Base):
    __tablename__ = 'dictionaries'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    entries: Mapped[list['DictionaryEntry']] = relationship(back_populates='dictionary', cascade='all, delete-orphan')


class DictionaryEntry(Base):
    __tablename__ = 'dictionary_entries'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dictionary_id: Mapped[int] = mapped_column(ForeignKey('dictionaries.id', ondelete='CASCADE'), nullable=False)
    source_text: Mapped[str] = mapped_column(String(255), nullable=False)
    spoken_text: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    dictionary: Mapped['Dictionary'] = relationship(back_populates='entries')
