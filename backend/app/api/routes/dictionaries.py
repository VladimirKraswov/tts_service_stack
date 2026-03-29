from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.models.dictionary import Dictionary, DictionaryEntry
from app.schemas.dictionary import (
    DictionaryCreate,
    DictionaryEntryCreate,
    DictionaryRead,
    PronunciationPreviewRequest,
    PronunciationPreviewResponse,
)
from app.services.preprocessor import TechnicalPreprocessor

router = APIRouter(prefix='/dictionaries', tags=['dictionaries'])
preprocessor = TechnicalPreprocessor()


@router.get('', response_model=list[DictionaryRead])
def list_dictionaries(db: Session = Depends(get_db)) -> list[Dictionary]:
    return list(db.scalars(select(Dictionary).options(selectinload(Dictionary.entries)).order_by(Dictionary.id)))


@router.post('', response_model=DictionaryRead)
def create_dictionary(payload: DictionaryCreate, db: Session = Depends(get_db)) -> Dictionary:
    dictionary = Dictionary(**payload.model_dump())
    db.add(dictionary)
    db.commit()
    db.refresh(dictionary)
    return dictionary


@router.get('/{dictionary_id}', response_model=DictionaryRead)
def get_dictionary(dictionary_id: int, db: Session = Depends(get_db)) -> Dictionary:
    dictionary = db.scalar(select(Dictionary).options(selectinload(Dictionary.entries)).where(Dictionary.id == dictionary_id))
    if dictionary is None:
        raise HTTPException(status_code=404, detail='Dictionary not found')
    return dictionary


@router.post('/{dictionary_id}/entries', response_model=DictionaryRead)
def add_entry(dictionary_id: int, payload: DictionaryEntryCreate, db: Session = Depends(get_db)) -> Dictionary:
    dictionary = db.scalar(select(Dictionary).options(selectinload(Dictionary.entries)).where(Dictionary.id == dictionary_id))
    if dictionary is None:
        raise HTTPException(status_code=404, detail='Dictionary not found')
    entry = DictionaryEntry(dictionary_id=dictionary_id, **payload.model_dump())
    db.add(entry)
    db.commit()
    return db.scalar(select(Dictionary).options(selectinload(Dictionary.entries)).where(Dictionary.id == dictionary_id))


@router.delete('/{dictionary_id}/entries/{entry_id}', response_model=DictionaryRead)
def delete_entry(dictionary_id: int, entry_id: int, db: Session = Depends(get_db)) -> Dictionary:
    entry = db.get(DictionaryEntry, entry_id)
    if entry is None or entry.dictionary_id != dictionary_id:
        raise HTTPException(status_code=404, detail='Entry not found')
    db.delete(entry)
    db.commit()
    dictionary = db.scalar(select(Dictionary).options(selectinload(Dictionary.entries)).where(Dictionary.id == dictionary_id))
    if dictionary is None:
        raise HTTPException(status_code=404, detail='Dictionary not found')
    return dictionary


@router.post('/{dictionary_id}/preview', response_model=PronunciationPreviewResponse)
def preview_pronunciation(dictionary_id: int, payload: PronunciationPreviewRequest, db: Session = Depends(get_db)) -> PronunciationPreviewResponse:
    processed = preprocessor.process(db, payload.text, dictionary_id=dictionary_id)
    return PronunciationPreviewResponse(original_text=payload.text, processed_text=processed.processed_text)
